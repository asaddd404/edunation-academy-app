"""Regression tests for the issues found in the scoring/progress audit.

Each test pins down one concrete way the app could be gamed or could show a
student the wrong thing, so that the fix cannot quietly regress.
"""

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.core.progress import section_test_unlocked
from app.core.question_scoring import grade_matching, match_answer_token
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category, teacher_categories
from app.models.ent_question import EntMatchPair, EntQuestion, EntQuestionType
from app.models.ent_simulation import EntSimulation, EntSimulationQuestion, EntSimulationStatus
from app.models.ent_subject import EntSubject
from app.models.homework import HomeworkStatusEnum, HomeworkSubmission
from app.models.lesson import Lesson
from app.models.section import Section
from app.models.student_rating import StudentRating
from app.models.user import RoleEnum
from app.security import create_video_ticket
from tests.test_refresh_cookie import ORIGIN_HEADER, PASSWORD, REFRESH_COOKIE_NAME, _login


# --- matching questions ----------------------------------------------------

def _matching_question(question_id: int = 7):
    pairs = [SimpleNamespace(id=pid) for pid in (11, 12, 13)]
    return SimpleNamespace(id=question_id, qtype=EntQuestionType.matching, max_score=2, match_pairs=pairs)


def test_matching_identity_mapping_no_longer_scores():
    """The old exploit: answer every prompt with its own id."""
    question = _matching_question()
    identity = {str(p.id): p.id for p in question.match_pairs}
    assert grade_matching(question, {"pairs": identity}) == 0


def test_matching_correct_tokens_score_full_and_partial():
    question = _matching_question()
    tokens = {str(p.id): match_answer_token(question.id, p.id) for p in question.match_pairs}
    assert grade_matching(question, {"pairs": tokens}) == 2

    partial = dict(tokens)
    partial["12"] = match_answer_token(question.id, 13)
    partial["13"] = match_answer_token(question.id, 12)
    assert grade_matching(question, {"pairs": partial}) == 1


def test_matching_token_is_bound_to_its_question():
    """A token copied from another question with the same pair id is wrong."""
    question = _matching_question(question_id=7)
    foreign = {str(p.id): match_answer_token(8, p.id) for p in question.match_pairs}
    assert grade_matching(question, {"pairs": foreign}) == 0


async def _enrolled_student(db_session, make_user, slug: str):
    student = await make_user(RoleEnum.student)
    category = Category(name=slug, slug=slug, is_active=True)
    db_session.add(category)
    await db_session.flush()
    db_session.add(Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved))
    await db_session.commit()
    return student, category


_subject_counter = itertools.count(1)


async def _matching_simulation(db_session, student, *, expires_at=None):
    subject = EntSubject(name="Химия", slug=f"chem-{next(_subject_counter)}", is_active=True)
    db_session.add(subject)
    await db_session.flush()
    question = EntQuestion(subject_id=subject.id, qtype=EntQuestionType.matching, text="Сопоставьте", max_score=2)
    question.match_pairs = [
        EntMatchPair(prompt_text="H2O", answer_text="вода", order_index=0),
        EntMatchPair(prompt_text="NaCl", answer_text="соль", order_index=1),
    ]
    db_session.add(question)
    await db_session.flush()
    simulation = EntSimulation(
        student_id=student.id,
        is_timed=expires_at is not None,
        duration_minutes=60 if expires_at is not None else None,
        expires_at=expires_at,
        status=EntSimulationStatus.in_progress,
    )
    db_session.add(simulation)
    await db_session.flush()
    db_session.add(EntSimulationQuestion(simulation_id=simulation.id, question_id=question.id, order_index=0))
    await db_session.commit()
    return simulation, question


async def test_ent_matching_answers_do_not_reuse_prompt_ids(client, db_session, make_user, login_as):
    student, _ = await _enrolled_student(db_session, make_user, "ent-ids")
    simulation, _ = await _matching_simulation(db_session, student)
    login_as(student)

    response = await client.get(f"/api/v1/ent/simulations/{simulation.id}")
    assert response.status_code == 200
    question = response.json()["questions"][0]
    prompt_ids = {p["id"] for p in question["match_prompts"]}
    answer_ids = {a["id"] for a in question["match_answers"]}
    assert not prompt_ids & answer_ids
    assert all(isinstance(a, str) for a in answer_ids)


# --- ЕНТ submission --------------------------------------------------------

async def test_ent_second_submit_is_refused_and_xp_granted_once(client, db_session, make_user, login_as):
    student, _ = await _enrolled_student(db_session, make_user, "ent-twice")
    simulation, question = await _matching_simulation(db_session, student)
    login_as(student)

    pairs = {str(p.id): match_answer_token(question.id, p.id) for p in question.match_pairs}
    body = {"answers": [{"question_id": question.id, "pairs": pairs}]}
    first = await client.post(f"/api/v1/ent/simulations/{simulation.id}/submit", json=body)
    second = await client.post(f"/api/v1/ent/simulations/{simulation.id}/submit", json=body)

    assert first.status_code == 200
    assert first.json()["total_score"] == 2
    assert second.status_code == 409
    rating = await db_session.get(StudentRating, student.id, populate_existing=True)
    assert rating.simulations_completed == 1
    assert rating.total_xp == 2


async def test_ent_submit_past_deadline_earns_nothing(client, db_session, make_user, login_as):
    student, _ = await _enrolled_student(db_session, make_user, "ent-late")
    simulation, question = await _matching_simulation(
        db_session, student, expires_at=datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    login_as(student)

    pairs = {str(p.id): match_answer_token(question.id, p.id) for p in question.match_pairs}
    response = await client.post(
        f"/api/v1/ent/simulations/{simulation.id}/submit",
        json={"answers": [{"question_id": question.id, "pairs": pairs}]},
    )

    assert response.status_code == 200
    assert response.json()["time_expired"] is True
    assert response.json()["total_score"] == 2  # still graded for review
    assert response.json()["xp_earned"] == 0
    assert await db_session.get(StudentRating, student.id) is None


# --- sessions --------------------------------------------------------------

async def test_parallel_tab_refresh_does_not_clear_the_new_cookie(client, make_password_user):
    """Tab B arrives with the token tab A just rotated: it must not delete the
    cookie A was given, and it must not get a session of its own either."""
    user = await make_password_user(PASSWORD)
    await _login(client, user)
    shared = client.cookies[REFRESH_COOKIE_NAME]

    assert (await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)).status_code == 200

    client.cookies.set(REFRESH_COOKIE_NAME, shared)
    late = await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)
    assert late.status_code == 401
    assert late.headers.get("x-refresh-rotated") == "1"
    assert "set-cookie" not in late.headers


async def test_video_ticket_is_not_accepted_as_a_session(client, make_user):
    await make_user(RoleEnum.student)
    ticket = create_video_ticket(lesson_id=1)
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ticket}"})
    assert response.status_code == 401


async def test_changing_phone_requires_the_password(client, make_password_user):
    user = await make_password_user(PASSWORD)
    token = (await _login(client, user)).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    refused = await client.patch("/api/v1/me", json={"phone": "+77779990011"}, headers=headers)
    assert refused.status_code == 400

    accepted = await client.patch(
        "/api/v1/me", json={"phone": "+77779990011", "current_password": PASSWORD}, headers=headers
    )
    assert accepted.status_code == 200
    assert accepted.json()["phone"] == "+77779990011"


# --- catalog and applications ----------------------------------------------

async def test_approved_status_wins_over_an_older_rejection(client, db_session, make_user, login_as):
    student, category = await _enrolled_student(db_session, make_user, "status-order")
    db_session.add(Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.rejected))
    await db_session.commit()
    login_as(student)

    listing = await client.get("/api/v1/categories")
    detail = await client.get(f"/api/v1/categories/{category.id}")

    item = next(c for c in listing.json()["items"] if c["id"] == category.id)
    assert item["my_application_status"] == "approved"
    assert detail.json()["my_application_status"] == "approved"


async def test_cannot_reapply_to_a_course_already_approved(client, db_session, make_user, login_as):
    student, category = await _enrolled_student(db_session, make_user, "reapply")
    login_as(student)

    response = await client.post("/api/v1/applications", json={"category_id": category.id})

    assert response.status_code == 409
    count = len((await db_session.scalars(select(Application).where(Application.student_id == student.id))).all())
    assert count == 1


async def test_deactivated_course_closes_its_content(client, db_session, make_user, login_as):
    student, category = await _enrolled_student(db_session, make_user, "deactivated")
    category.is_active = False
    await db_session.commit()
    login_as(student)

    assert (await client.get(f"/api/v1/categories/{category.id}/sections")).status_code == 403
    assert (await client.get(f"/api/v1/categories/{category.id}")).status_code == 404


# --- progress --------------------------------------------------------------

def test_section_test_rule():
    assert section_test_unlocked([1, 2], [], {1, 2})
    assert not section_test_unlocked([1, 2], [], {1})
    # A section with no lessons waits for everything before it ...
    assert not section_test_unlocked([], [1, 2], {1})
    assert section_test_unlocked([], [1, 2], {1, 2})
    # ... and the very first such section is open.
    assert section_test_unlocked([], [], set())


# --- homework --------------------------------------------------------------

async def test_accepted_homework_cannot_be_overwritten(client, db_session, make_user, login_as):
    student, category = await _enrolled_student(db_session, make_user, "hw-accepted")
    section = Section(category_id=category.id, title="Раздел", order_index=0)
    db_session.add(section)
    await db_session.flush()
    lesson = Lesson(section_id=section.id, title="Урок", order_index=0)
    db_session.add(lesson)
    await db_session.flush()
    db_session.add(
        HomeworkSubmission(
            lesson_id=lesson.id,
            student_id=student.id,
            text_answer="готово",
            status=HomeworkStatusEnum.accepted,
            teacher_feedback="Отлично",
        )
    )
    await db_session.commit()
    login_as(student)

    response = await client.post(f"/api/v1/lessons/{lesson.id}/homework", data={"text_answer": "другое"})

    assert response.status_code == 409
    submission = await db_session.scalar(
        select(HomeworkSubmission)
        .where(HomeworkSubmission.lesson_id == lesson.id)
        .execution_options(populate_existing=True)
    )
    assert submission.status == HomeworkStatusEnum.accepted
    assert submission.teacher_feedback == "Отлично"


# --- lesson images ---------------------------------------------------------

async def test_deleting_a_lesson_keeps_an_image_another_lesson_uses(
    client, db_session, make_user, login_as, tmp_path, monkeypatch
):
    import json

    from app.core import storage

    monkeypatch.setattr(storage, "UPLOAD_ROOT", tmp_path)
    image = tmp_path / "lesson-content" / "shared.png"
    image.parent.mkdir()
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    doc = json.dumps({"type": "doc", "content": [{"type": "image", "attrs": {"src": "lesson-content/shared.png"}}]})

    teacher = await make_user(RoleEnum.teacher)
    other = await make_user(RoleEnum.teacher)
    mine = Category(name="Мой", slug="img-mine", is_active=True)
    theirs = Category(name="Чужой", slug="img-theirs", is_active=True)
    db_session.add_all([mine, theirs])
    await db_session.flush()
    await db_session.execute(teacher_categories.insert().values(teacher_id=teacher.id, category_id=mine.id))
    await db_session.execute(teacher_categories.insert().values(teacher_id=other.id, category_id=theirs.id))
    sections = [Section(category_id=mine.id, title="A", order_index=0), Section(category_id=theirs.id, title="B", order_index=0)]
    db_session.add_all(sections)
    await db_session.flush()
    my_lesson = Lesson(section_id=sections[0].id, title="Копия", order_index=0, description=doc)
    their_lesson = Lesson(section_id=sections[1].id, title="Оригинал", order_index=0, description=doc)
    db_session.add_all([my_lesson, their_lesson])
    await db_session.commit()
    login_as(teacher)

    assert (await client.delete(f"/api/v1/teacher/lessons/{my_lesson.id}")).status_code == 204
    assert image.exists()

    login_as(other)
    assert (await client.delete(f"/api/v1/teacher/lessons/{their_lesson.id}")).status_code == 204
    assert not image.exists()


async def test_second_attempt_adds_to_the_existing_rating(client, db_session, make_user, login_as):
    """The increment for an existing rating row now runs in SQL; check it
    still adds XP up and keeps the best score."""
    student, _ = await _enrolled_student(db_session, make_user, "ent-two-attempts")
    first, question = await _matching_simulation(db_session, student)
    second, second_question = await _matching_simulation(db_session, student)
    login_as(student)

    full = {str(p.id): match_answer_token(question.id, p.id) for p in question.match_pairs}
    one_right = {
        str(second_question.match_pairs[0].id): match_answer_token(second_question.id, second_question.match_pairs[0].id)
    }
    await client.post(f"/api/v1/ent/simulations/{first.id}/submit", json={"answers": [{"question_id": question.id, "pairs": full}]})
    await client.post(
        f"/api/v1/ent/simulations/{second.id}/submit",
        json={"answers": [{"question_id": second_question.id, "pairs": one_right}]},
    )

    rating = await db_session.get(StudentRating, student.id, populate_existing=True)
    assert rating.simulations_completed == 2
    assert rating.total_xp == 3
    assert rating.best_score == 2
