"""Two rules that protect a student's account and an exam's integrity.

Changing the phone number -- the login -- needs the current password, so an
open session alone cannot take the account. A timed ЕНТ attempt has a hard
cutoff: past the deadline (plus a short grace for the auto-submit's round
trip) answers are not accepted, and an abandoned attempt is closed.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.api.v1.ent import SUBMIT_GRACE
from app.models.ent_simulation import EntSimulation, EntSimulationQuestion, EntSimulationStatus
from app.models.user import RoleEnum, User
from app.security import hash_password
from tests.test_course_tests_and_xp import _open_ent_simulation

PASSWORD = "Passw0rd!x"


async def _user_with_password(db_session, make_user, role=RoleEnum.student) -> User:
    user = await make_user(role)
    user.password_hash = hash_password(PASSWORD)
    await db_session.commit()
    return user


async def _stored_phone(db_session, user: User) -> str:
    return await db_session.scalar(
        select(User.phone).where(User.id == user.id).execution_options(populate_existing=True)
    )


# --- phone change -------------------------------------------------------------


async def test_phone_change_without_password_is_refused(client, db_session, make_user, login_as):
    user = await _user_with_password(db_session, make_user)
    login_as(user)

    response = await client.patch("/api/v1/me", json={"phone": "+77071112233"})

    assert response.status_code == 400
    assert "текущий пароль" in response.json()["detail"]
    assert await _stored_phone(db_session, user) == user.phone


async def test_phone_change_with_wrong_password_is_refused(client, db_session, make_user, login_as):
    user = await _user_with_password(db_session, make_user)
    login_as(user)

    response = await client.patch("/api/v1/me", json={"phone": "+77071112233", "current_password": "wrong-one"})

    assert response.status_code == 400
    assert await _stored_phone(db_session, user) == user.phone


async def test_phone_change_with_password_works_and_is_the_new_login(client, db_session, make_user, login_as):
    user = await _user_with_password(db_session, make_user)
    login_as(user)

    response = await client.patch("/api/v1/me", json={"phone": "+7 707 111 22 44", "current_password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["phone"] == "+77071112244"
    login = await client.post("/api/v1/auth/login", json={"phone": "+77071112244", "password": PASSWORD})
    assert login.status_code == 200


async def test_name_change_and_unchanged_phone_need_no_password(client, db_session, make_user, login_as):
    user = await _user_with_password(db_session, make_user)
    login_as(user)

    response = await client.patch("/api/v1/me", json={"first_name": "Новое", "phone": user.phone})

    assert response.status_code == 200
    assert response.json()["first_name"] == "Новое"


async def test_taken_phone_is_not_revealed_without_the_password(client, db_session, make_user, login_as):
    """A borrowed session must not be able to probe which numbers exist:
    without the password the answer is the same for a free number and a
    taken one."""
    owner = await _user_with_password(db_session, make_user)
    other = await make_user(RoleEnum.student)
    login_as(owner)

    taken = await client.patch("/api/v1/me", json={"phone": other.phone, "current_password": "wrong-one"})
    free = await client.patch("/api/v1/me", json={"phone": "+77079998877", "current_password": "wrong-one"})

    assert taken.status_code == free.status_code == 400
    with_password = await client.patch("/api/v1/me", json={"phone": other.phone, "current_password": PASSWORD})
    assert with_password.status_code == 409


async def test_phone_change_attempts_are_rate_limited(client, db_session, make_user, login_as):
    user = await _user_with_password(db_session, make_user)
    login_as(user)

    codes = [
        (await client.patch("/api/v1/me", json={"phone": "+77071110000", "current_password": f"guess-{n}"})).status_code
        for n in range(11)
    ]

    assert codes[:10] == [400] * 10
    assert codes[10] == 429


# --- ЕНТ hard cutoff ---------------------------------------------------------


async def _make_timed(db_session, simulation: EntSimulation, expired_seconds_ago: float) -> None:
    now = datetime.now(timezone.utc)
    simulation.is_timed = True
    simulation.duration_minutes = 60
    simulation.started_at = now - timedelta(minutes=60, seconds=expired_seconds_ago)
    simulation.expires_at = now - timedelta(seconds=expired_seconds_ago)
    await db_session.commit()


async def _correct_answer(client, simulation_id: int, question) -> dict:
    exam = (await client.get(f"/api/v1/ent/simulations/{simulation_id}")).json()
    tokens = {a["text"]: a["id"] for a in exam["questions"][0]["match_answers"]}
    return {"question_id": question.id, "pairs": {str(p.id): tokens[p.answer_text] for p in question.match_pairs}}


async def test_answers_after_the_cutoff_do_not_count(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    simulation, question = await _open_ent_simulation(db_session, student)
    login_as(student)
    answer = await _correct_answer(client, simulation.id, question)
    await _make_timed(db_session, simulation, expired_seconds_ago=SUBMIT_GRACE.total_seconds() + 60)

    response = await client.post(f"/api/v1/ent/simulations/{simulation.id}/submit", json={"answers": [answer]})

    assert response.status_code == 200
    body = response.json()
    assert body["total_score"] == 0
    assert body["time_expired"] is True
    assert body["answers"][0]["given_answer"] is None


async def test_answers_within_the_grace_still_count(client, db_session, make_user, login_as):
    """The client auto-submits at 00:00; its request lands a moment later."""
    student = await make_user(RoleEnum.student)
    simulation, question = await _open_ent_simulation(db_session, student)
    login_as(student)
    answer = await _correct_answer(client, simulation.id, question)
    await _make_timed(db_session, simulation, expired_seconds_ago=5)

    response = await client.post(f"/api/v1/ent/simulations/{simulation.id}/submit", json={"answers": [answer]})

    assert response.status_code == 200
    assert response.json()["total_score"] == 2
    # Over time, so no timed bonus: XP equals the base score.
    assert response.json()["time_expired"] is True and response.json()["xp_earned"] == 2


async def test_reopening_an_expired_attempt_closes_it(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    simulation, _ = await _open_ent_simulation(db_session, student)
    login_as(student)
    await _make_timed(db_session, simulation, expired_seconds_ago=SUBMIT_GRACE.total_seconds() + 60)

    reopened = await client.get(f"/api/v1/ent/simulations/{simulation.id}")

    assert reopened.status_code == 409
    result = await client.get(f"/api/v1/ent/simulations/{simulation.id}/result")
    assert result.status_code == 200 and result.json()["total_score"] == 0


async def test_abandoned_attempts_do_not_block_a_new_one(client, db_session, make_user, login_as):
    """Five tabs closed mid-exam used to fill MAX_UNFINISHED_SIMULATIONS for
    good: they stayed in_progress forever."""
    student = await make_user(RoleEnum.student)
    simulation, question = await _open_ent_simulation(db_session, student)
    login_as(student)
    for _ in range(5):
        stale = EntSimulation(student_id=student.id, is_timed=False)
        db_session.add(stale)
        await db_session.flush()
        db_session.add(EntSimulationQuestion(simulation_id=stale.id, question_id=question.id, order_index=0))
        await _make_timed(db_session, stale, expired_seconds_ago=3600)
    await _make_timed(db_session, simulation, expired_seconds_ago=3600)

    response = await client.post(
        "/api/v1/ent/simulations",
        json={"subject_ids": [question.subject_id], "questions_per_subject": 1, "is_timed": False},
    )

    assert response.status_code == 201, response.text
    statuses = (
        await db_session.scalars(
            select(EntSimulation.status)
            .where(EntSimulation.student_id == student.id, EntSimulation.id != response.json()["id"])
            .execution_options(populate_existing=True)
        )
    ).all()
    assert set(statuses) == {EntSimulationStatus.submitted}
