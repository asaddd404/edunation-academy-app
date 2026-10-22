"""Course tests as sessions, opaque matching ids, and the XP ledger.

Each security test asserts what the attacker would actually try -- reading
the key off the payload, submitting twice at once, retaking for XP -- and
then the state left in the database, not only the status code.
"""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1.ent import submit_simulation
from app.api.v1.tests import submit_test_attempt
from app.config import settings
from app.core.match_tokens import ent_scope, match_answer_token
from app.core.rating import compute_test_xp
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category
from app.models.ent_question import EntMatchPair, EntQuestion, EntQuestionType
from app.models.ent_simulation import EntSimulation, EntSimulationQuestion
from app.models.ent_subject import EntSubject
from app.models.lesson import Lesson
from app.models.question import Choice, MatchPair, Question
from app.models.section import Section
from app.models.student_rating import StudentRating
from app.models.test_attempt import TestAttempt
from app.models.test_attempt import TestAttemptStatus as AttemptStatus
from app.models.user import RoleEnum, User
from app.models.xp_event import XpEvent
from app.schemas.ent_simulation import EntSimulationSubmitIn
from app.schemas.test_attempt import TestAttemptIn

_IS_SQLITE = settings.database_url.startswith("sqlite")


async def _enrolled_course(db_session, student, slug: str):
    """An approved category with one section and one lesson whose mini-test
    has a single-choice question and a three-pair matching question."""
    category = Category(name=slug, slug=slug, is_active=True)
    db_session.add(category)
    await db_session.flush()
    db_session.add(Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved))
    section = Section(category_id=category.id, title="Раздел", order_index=0)
    db_session.add(section)
    await db_session.flush()
    lesson = Lesson(section_id=section.id, title="Урок", order_index=0)
    db_session.add(lesson)
    await db_session.flush()

    single = Question(lesson_id=lesson.id, qtype=EntQuestionType.single, text="2+2", max_score=1, order_index=0)
    single.choices = [Choice(text="4", is_correct=True, order_index=0), Choice(text="5", is_correct=False, order_index=1)]
    matching = Question(lesson_id=lesson.id, qtype=EntQuestionType.matching, text="Пары", max_score=2, order_index=1)
    matching.match_pairs = [
        MatchPair(prompt_text=f"p{i}", answer_text=f"a{i}", order_index=i) for i in range(3)
    ]
    db_session.add_all([single, matching])
    await db_session.commit()
    return lesson, single, matching


def _correct_answers(session: dict, single: Question, matching: Question) -> list[dict]:
    """What a student who knows the material sends: the right choice, and
    each prompt paired with the answer text that belongs to it."""
    by_id = {q["id"]: q for q in session["questions"]}
    token_by_text = {a["text"]: a["id"] for a in by_id[matching.id]["match_answers"]}
    correct_choice = next(c for c in single.choices if c.is_correct)
    return [
        {"question_id": single.id, "choice_id": correct_choice.id},
        {
            "question_id": matching.id,
            "pairs": {str(p.id): token_by_text[p.answer_text] for p in matching.match_pairs},
        },
    ]


# --- matching answers no longer carry the key ------------------------------


async def test_matching_answer_ids_do_not_reveal_the_pairing(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    lesson, _, matching = await _enrolled_course(db_session, student, "match-leak")
    login_as(student)

    session = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
    question = next(q for q in session["questions"] if q["id"] == matching.id)

    prompt_ids = {p["id"] for p in question["match_prompts"]}
    answer_ids = {a["id"] for a in question["match_answers"]}
    assert all(isinstance(a, str) for a in answer_ids)
    assert not answer_ids & {str(pid) for pid in prompt_ids}


async def test_pairing_answers_by_prompt_id_scores_nothing(client, db_session, make_user, login_as):
    """The old exploit -- answer every prompt with its own id -- must now
    be worth zero on that question."""
    student = await make_user(RoleEnum.student)
    lesson, single, matching = await _enrolled_course(db_session, student, "match-exploit")
    login_as(student)

    session = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
    response = await client.post(
        f"/api/v1/test-attempts/{session['attempt_id']}/submit",
        json={
            "answers": [
                {"question_id": matching.id, "pairs": {str(p.id): str(p.id) for p in matching.match_pairs}},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["earned_points"] == 0


async def test_tokens_from_one_attempt_are_worthless_in_the_next(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    lesson, single, matching = await _enrolled_course(db_session, student, "match-replay")
    login_as(student)

    first = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
    answers = _correct_answers(first, single, matching)
    await client.post(f"/api/v1/test-attempts/{first['attempt_id']}/submit", json={"answers": answers})

    second = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
    assert second["attempt_id"] != first["attempt_id"]
    result = (
        await client.post(f"/api/v1/test-attempts/{second['attempt_id']}/submit", json={"answers": answers})
    ).json()
    # The single-choice point survives (choice ids are not secret); the
    # replayed matching tokens do not.
    assert result["earned_points"] == 1


# --- lesson test sessions ---------------------------------------------------


async def test_lesson_detail_no_longer_hands_out_questions(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    lesson, _, _ = await _enrolled_course(db_session, student, "detail")
    login_as(student)

    body = (await client.get(f"/api/v1/lessons/{lesson.id}")).json()
    assert "questions" not in body
    assert body["question_count"] == 2


async def test_start_resumes_the_open_attempt(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    lesson, _, _ = await _enrolled_course(db_session, student, "resume")
    login_as(student)

    a = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
    b = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()

    assert a["attempt_id"] == b["attempt_id"]
    assert a["started_at"] == b["started_at"]
    open_count = await db_session.scalar(
        select(func.count(TestAttempt.id)).where(
            TestAttempt.student_id == student.id, TestAttempt.status == AttemptStatus.in_progress
        )
    )
    assert open_count == 1


async def test_perfect_attempt_earns_accuracy_and_speed_xp(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    lesson, single, matching = await _enrolled_course(db_session, student, "xp-perfect")
    login_as(student)

    session = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
    result = (
        await client.post(
            f"/api/v1/test-attempts/{session['attempt_id']}/submit",
            json={"answers": _correct_answers(session, single, matching)},
        )
    ).json()

    assert result["passed"] is True
    assert result["score"] == 100
    assert (result["correct_count"], result["question_count"]) == (2, 2)
    assert (result["earned_points"], result["max_points"]) == (3, 3)
    assert result["accuracy_xp"] == 20
    assert result["speed_bonus"] > 0
    assert result["xp_earned"] == result["accuracy_xp"] + result["speed_bonus"]

    rating = await db_session.get(StudentRating, student.id)
    await db_session.refresh(rating)
    assert rating.total_xp == result["xp_earned"]
    events = (await db_session.scalars(select(XpEvent).where(XpEvent.student_id == student.id))).all()
    assert [(e.source, e.source_id, e.xp) for e in events] == [("lesson_test", session["attempt_id"], result["xp_earned"])]


async def test_retaking_a_passed_test_does_not_farm_xp(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    lesson, single, matching = await _enrolled_course(db_session, student, "xp-farm")
    login_as(student)

    earned = []
    for _ in range(3):
        session = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
        result = (
            await client.post(
                f"/api/v1/test-attempts/{session['attempt_id']}/submit",
                json={"answers": _correct_answers(session, single, matching)},
            )
        ).json()
        earned.append(result["xp_earned"])

    # The first perfect run is paid; identical retakes add at most the few
    # XP a marginally faster clock is worth, never another full award.
    assert earned[0] >= 20
    assert sum(earned[1:]) <= compute_test_xp(3, 3, 2, 0).total - earned[0]
    rating = await db_session.get(StudentRating, student.id)
    await db_session.refresh(rating)
    assert rating.total_xp == sum(earned) <= compute_test_xp(3, 3, 2, 0).total


async def test_failed_attempt_earns_nothing(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    lesson, single, _ = await _enrolled_course(db_session, student, "xp-fail")
    login_as(student)

    session = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
    wrong = next(c for c in single.choices if not c.is_correct)
    result = (
        await client.post(
            f"/api/v1/test-attempts/{session['attempt_id']}/submit",
            json={"answers": [{"question_id": single.id, "choice_id": wrong.id}]},
        )
    ).json()

    assert result["passed"] is False
    assert result["xp_earned"] == 0
    assert await db_session.scalar(select(func.count(XpEvent.id)).where(XpEvent.student_id == student.id)) == 0


async def test_attempt_cannot_be_submitted_twice(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    lesson, single, matching = await _enrolled_course(db_session, student, "twice")
    login_as(student)

    session = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
    body = {"answers": _correct_answers(session, single, matching)}
    first = await client.post(f"/api/v1/test-attempts/{session['attempt_id']}/submit", json=body)
    second = await client.post(f"/api/v1/test-attempts/{session['attempt_id']}/submit", json=body)

    assert first.status_code == 200
    assert second.status_code == 409


async def test_student_cannot_submit_someone_elses_attempt(client, db_session, make_user, login_as):
    owner = await make_user(RoleEnum.student)
    intruder = await make_user(RoleEnum.student)
    lesson, _, _ = await _enrolled_course(db_session, owner, "foreign")
    login_as(owner)
    session = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()

    login_as(intruder)
    response = await client.post(f"/api/v1/test-attempts/{session['attempt_id']}/submit", json={"answers": []})

    assert response.status_code == 404
    attempt = await db_session.get(TestAttempt, session["attempt_id"])
    assert attempt.status == AttemptStatus.in_progress


# --- ЕНТ: tokens and the double-submit race --------------------------------


async def _open_ent_simulation(db_session, student) -> tuple[EntSimulation, EntQuestion]:
    category = Category(name="ent-course", slug=f"ent-course-{student.id}", is_active=True)
    db_session.add(category)
    await db_session.flush()
    db_session.add(Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved))
    subject = EntSubject(name="История", slug=f"history-{student.id}")
    db_session.add(subject)
    await db_session.flush()
    question = EntQuestion(subject_id=subject.id, qtype=EntQuestionType.matching, text="Пары", max_score=2)
    question.match_pairs = [EntMatchPair(prompt_text=f"p{i}", answer_text=f"a{i}", order_index=i) for i in range(3)]
    db_session.add(question)
    await db_session.flush()
    simulation = EntSimulation(student_id=student.id, is_timed=False)
    db_session.add(simulation)
    await db_session.flush()
    db_session.add(EntSimulationQuestion(simulation_id=simulation.id, question_id=question.id, order_index=0))
    await db_session.commit()
    return simulation, question


async def test_ent_matching_tokens_grade_and_store_row_ids(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    simulation, question = await _open_ent_simulation(db_session, student)
    login_as(student)

    exam = (await client.get(f"/api/v1/ent/simulations/{simulation.id}")).json()
    q = exam["questions"][0]
    assert not {a["id"] for a in q["match_answers"]} & {str(p["id"]) for p in q["match_prompts"]}

    token_by_text = {a["id"]: a["text"] for a in q["match_answers"]}
    text_to_token = {v: k for k, v in token_by_text.items()}
    pairs = {str(p.id): text_to_token[p.answer_text] for p in question.match_pairs}
    result = (
        await client.post(
            f"/api/v1/ent/simulations/{simulation.id}/submit",
            json={"answers": [{"question_id": question.id, "pairs": pairs}]},
        )
    ).json()

    assert result["total_score"] == 2
    # Stored and echoed back as row ids, so the result screen still lines
    # the given answer up against match_pairs.
    assert result["answers"][0]["given_answer"]["pairs"] == {str(p.id): p.id for p in question.match_pairs}


@pytest.mark.skipif(_IS_SQLITE, reason="SQLite has no row locks; the race needs Postgres")
async def test_concurrent_ent_submits_award_xp_once(test_engine, db_session, make_user):
    """Five submits of one simulation, each in its own session and
    connection, all in flight at once.

    Driven through the handler directly rather than the test client: the
    in-process ASGI transport runs requests one after another, so through it
    the race never happens and the test would pass with the lock removed.
    """
    student = await make_user(RoleEnum.student)
    simulation, question = await _open_ent_simulation(db_session, student)

    tokens = {p.answer_text: match_answer_token(ent_scope(simulation.id), p.id) for p in question.match_pairs}
    payload = EntSimulationSubmitIn(
        answers=[
            {"question_id": question.id, "pairs": {str(p.id): tokens[p.answer_text] for p in question.match_pairs}}
        ]
    )
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    # Everyone holds a live connection before anyone submits; without this
    # the first coroutine finishes while the rest are still connecting.
    start_line = asyncio.Barrier(5)

    async def submit() -> int:
        async with factory() as db:
            me = await db.get(User, student.id)
            await start_line.wait()
            try:
                await submit_simulation(simulation.id, payload, db=db, student=me)
                return 200
            except HTTPException as e:
                return e.status_code

    codes = await asyncio.gather(*(submit() for _ in range(5)))

    assert sorted(codes) == [200, 409, 409, 409, 409]
    rating = await db_session.get(StudentRating, student.id)
    await db_session.refresh(rating)
    assert rating.total_xp == 2
    assert rating.simulations_completed == 1
    assert await db_session.scalar(select(func.count(XpEvent.id)).where(XpEvent.student_id == student.id)) == 1


@pytest.mark.skipif(_IS_SQLITE, reason="SQLite has no row locks; the race needs Postgres")
async def test_concurrent_lesson_test_submits_award_xp_once(client, test_engine, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    lesson, single, matching = await _enrolled_course(db_session, student, "lesson-race")
    login_as(student)
    session = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
    payload = TestAttemptIn(answers=_correct_answers(session, single, matching))

    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    start_line = asyncio.Barrier(5)

    async def submit() -> int:
        async with factory() as db:
            me = await db.get(User, student.id)
            await start_line.wait()
            try:
                await submit_test_attempt(session["attempt_id"], payload, db=db, student=me)
                return 200
            except HTTPException as e:
                return e.status_code

    codes = await asyncio.gather(*(submit() for _ in range(5)))

    assert sorted(codes) == [200, 409, 409, 409, 409]
    assert await db_session.scalar(select(func.count(XpEvent.id)).where(XpEvent.student_id == student.id)) == 1


# --- leaderboards -----------------------------------------------------------


async def test_overall_and_lesson_leaderboards(client, db_session, make_user, login_as):
    fast = await make_user(RoleEnum.student)
    slow = await make_user(RoleEnum.student)
    lesson, single, matching = await _enrolled_course(db_session, fast, "board")
    db_session.add(
        Application(
            student_id=slow.id,
            category_id=(await db_session.get(Section, lesson.section_id)).category_id,
            status=ApplicationStatusEnum.approved,
        )
    )
    await db_session.commit()

    login_as(fast)
    session = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
    await client.post(
        f"/api/v1/test-attempts/{session['attempt_id']}/submit",
        json={"answers": _correct_answers(session, single, matching)},
    )

    # Passes at 2/3 points: the single-choice right, one matching pair right
    # and the other two swapped.
    login_as(slow)
    session = (await client.post(f"/api/v1/lessons/{lesson.id}/test/start")).json()
    answers = _correct_answers(session, single, matching)
    pairs = answers[1]["pairs"]
    p1, p2 = (str(p.id) for p in matching.match_pairs[1:])
    pairs[p1], pairs[p2] = pairs[p2], pairs[p1]
    slow_result = (
        await client.post(f"/api/v1/test-attempts/{session['attempt_id']}/submit", json={"answers": answers})
    ).json()
    assert (slow_result["earned_points"], slow_result["correct_count"], slow_result["passed"]) == (2, 1, True)

    board = (await client.get(f"/api/v1/leaderboard/lessons/{lesson.id}")).json()
    assert [e["student_id"] for e in board["entries"]] == [fast.id, slow.id]
    top = board["entries"][0]
    assert (top["passed"], top["score"], top["correct_count"], top["question_count"]) == (True, 100, 2, 2)
    assert top["duration_seconds"] is not None
    assert board["me"]["student_id"] == slow.id and board["me"]["rank"] == 2

    for period in ("all", "week"):
        overall = (await client.get("/api/v1/leaderboard", params={"period": period})).json()
        assert overall["entries"][0]["student_id"] == fast.id
        assert overall["entries"][0]["tests_passed"] == 1
        assert overall["me"]["student_id"] == slow.id

    scopes = (await client.get("/api/v1/leaderboard/scopes")).json()
    assert scopes[0]["sections"][0]["lessons"] == [{"id": lesson.id, "title": lesson.title}]


async def test_lesson_leaderboard_requires_enrollment(client, db_session, make_user, login_as):
    enrolled = await make_user(RoleEnum.student)
    outsider = await make_user(RoleEnum.student)
    lesson, _, _ = await _enrolled_course(db_session, enrolled, "board-private")
    # Enrolled somewhere else, so the outsider passes the "any course"
    # gate and is stopped by the per-category one.
    await _enrolled_course(db_session, outsider, "board-other")

    login_as(outsider)
    response = await client.get(f"/api/v1/leaderboard/lessons/{lesson.id}")
    assert response.status_code == 403


def test_speed_bonus_shrinks_with_time_and_accuracy():
    instant = compute_test_xp(10, 10, 10, 0)
    slow = compute_test_xp(10, 10, 10, 10 * 60)
    sloppy = compute_test_xp(5, 10, 10, 0)

    assert instant.accuracy_xp == 100 and instant.speed_bonus == 50
    assert slow.speed_bonus == 0
    assert sloppy.accuracy_xp == 50 and sloppy.speed_bonus == 25
