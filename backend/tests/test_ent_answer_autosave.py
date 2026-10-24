"""ЕНТ answers are saved as the student works, not only at submit.

Before this, answers lived only in the page: a reload or a dropped
connection wiped them, and an attempt closed by the server after time ran
out (tab closed, no network at 00:00) was graded as blank.
"""

from app.api.v1.ent import SUBMIT_GRACE
from app.models.user import RoleEnum
from tests.test_account_and_exam_rules import _correct_answer, _make_timed
from tests.test_course_tests_and_xp import _open_ent_simulation


async def _setup(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    simulation, question = await _open_ent_simulation(db_session, student)
    login_as(student)
    return simulation, question, await _correct_answer(client, simulation.id, question)


def _save(client, simulation_id, answers):
    return client.put(f"/api/v1/ent/simulations/{simulation_id}/answers", json={"answers": answers})


async def test_saved_answers_come_back_on_reload(client, db_session, make_user, login_as):
    simulation, _, answer = await _setup(client, db_session, make_user, login_as)

    assert (await _save(client, simulation.id, [answer])).status_code == 200

    exam = (await client.get(f"/api/v1/ent/simulations/{simulation.id}")).json()
    assert exam["saved_answers"] == [{**answer, "choice_id": None, "choice_ids": None, "text": None}]


async def test_submit_grades_saved_answers_the_client_did_not_resend(client, db_session, make_user, login_as):
    simulation, _, answer = await _setup(client, db_session, make_user, login_as)
    await _save(client, simulation.id, [answer])

    result = await client.post(f"/api/v1/ent/simulations/{simulation.id}/submit", json={"answers": []})

    assert result.status_code == 200 and result.json()["total_score"] == 2


async def test_the_submitted_answer_overrides_the_saved_one(client, db_session, make_user, login_as):
    simulation, question, answer = await _setup(client, db_session, make_user, login_as)
    await _save(client, simulation.id, [answer])
    wrong = {"question_id": question.id, "pairs": {k: "nope" for k in answer["pairs"]}}

    result = await client.post(f"/api/v1/ent/simulations/{simulation.id}/submit", json={"answers": [wrong]})

    assert result.json()["total_score"] == 0


async def test_an_empty_answer_clears_the_saved_one(client, db_session, make_user, login_as):
    simulation, question, answer = await _setup(client, db_session, make_user, login_as)
    await _save(client, simulation.id, [answer])

    await _save(client, simulation.id, [{"question_id": question.id}])

    exam = (await client.get(f"/api/v1/ent/simulations/{simulation.id}")).json()
    assert exam["saved_answers"] == []


async def test_an_attempt_closed_after_time_ran_out_is_graded_on_saved_answers(client, db_session, make_user, login_as):
    """The tab was closed (or the network was down) at 00:00; what had been
    saved before the deadline still counts."""
    simulation, _, answer = await _setup(client, db_session, make_user, login_as)
    await _save(client, simulation.id, [answer])
    await _make_timed(db_session, simulation, expired_seconds_ago=SUBMIT_GRACE.total_seconds() + 60)

    assert (await client.get(f"/api/v1/ent/simulations/{simulation.id}")).status_code == 409
    result = (await client.get(f"/api/v1/ent/simulations/{simulation.id}/result")).json()
    assert result["total_score"] == 2 and result["time_expired"] is True


async def test_a_late_submit_counts_what_was_saved_in_time_but_not_the_late_answers(client, db_session, make_user, login_as):
    simulation, question, answer = await _setup(client, db_session, make_user, login_as)
    await _save(client, simulation.id, [answer])
    await _make_timed(db_session, simulation, expired_seconds_ago=SUBMIT_GRACE.total_seconds() + 60)
    late_wrong = {"question_id": question.id, "pairs": {k: "nope" for k in answer["pairs"]}}

    result = await client.post(f"/api/v1/ent/simulations/{simulation.id}/submit", json={"answers": [late_wrong]})

    assert result.json()["total_score"] == 2


async def test_saving_after_the_cutoff_is_refused(client, db_session, make_user, login_as):
    simulation, _, answer = await _setup(client, db_session, make_user, login_as)
    await _make_timed(db_session, simulation, expired_seconds_ago=SUBMIT_GRACE.total_seconds() + 60)

    assert (await _save(client, simulation.id, [answer])).status_code == 409


async def test_saving_after_submit_is_refused(client, db_session, make_user, login_as):
    simulation, _, answer = await _setup(client, db_session, make_user, login_as)
    await client.post(f"/api/v1/ent/simulations/{simulation.id}/submit", json={"answers": []})

    assert (await _save(client, simulation.id, [answer])).status_code == 409


async def test_answers_for_questions_outside_the_attempt_are_refused(client, db_session, make_user, login_as):
    simulation, _, answer = await _setup(client, db_session, make_user, login_as)

    response = await _save(client, simulation.id, [{**answer, "question_id": 999_999}])

    assert response.status_code == 422


async def test_another_students_attempt_cannot_be_written(client, db_session, make_user, login_as):
    simulation, _, answer = await _setup(client, db_session, make_user, login_as)
    login_as(await make_user(RoleEnum.student))

    assert (await _save(client, simulation.id, [answer])).status_code in (403, 404)
