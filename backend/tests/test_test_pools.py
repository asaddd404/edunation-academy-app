"""Lesson/section tests drawn from a bank: every attempt a different set."""

import random

from sqlalchemy import select

from app.core.test_draw import draw_question_ids
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category, teacher_categories
from app.models.ent_question import EntQuestionType
from app.models.lesson import Lesson
from app.models.question import Choice, Question
from app.models.section import Section
from app.models.test_attempt import TestAttempt
from app.models.user import RoleEnum


# --- the draw ----------------------------------------------------------------


def test_draw_prefers_questions_the_last_attempt_did_not_show():
    pool = list(range(1, 7))
    first = draw_question_ids(pool, 3, None, random.Random(1))
    second = draw_question_ids(pool, 3, first, random.Random(2))
    assert len(first) == len(second) == 3
    assert not set(first) & set(second)


def test_draw_tops_up_from_the_last_attempt_when_the_bank_is_small():
    second = draw_question_ids([1, 2, 3, 4], 3, [1, 2, 3], random.Random(3))
    assert 4 in second and len(set(second)) == 3


def test_draw_never_repeats_the_same_order_for_the_same_set():
    for seed in range(50):
        assert draw_question_ids([1, 2, 3], 3, [1, 2, 3], random.Random(seed)) != [1, 2, 3]


def test_without_a_limit_nothing_changes():
    # Every question, in the teacher's order -- exactly as before banks.
    assert draw_question_ids([5, 6, 7], None, [5, 6, 7], random.Random(0)) == [5, 6, 7]
    assert sorted(draw_question_ids([5, 6, 7], 10, None, random.Random(0))) == [5, 6, 7]


# --- end to end ----------------------------------------------------------------


async def _course(db_session, make_user, *, questions: int, per_attempt: int | None, slug: str):
    student = await make_user(RoleEnum.student)
    teacher = await make_user(RoleEnum.teacher)
    category = Category(name=slug, slug=slug, is_active=True)
    db_session.add(category)
    await db_session.flush()
    await db_session.execute(teacher_categories.insert().values(teacher_id=teacher.id, category_id=category.id))
    db_session.add(Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved))
    section = Section(category_id=category.id, title="Раздел 1", order_index=0)
    db_session.add(section)
    await db_session.flush()
    lesson = Lesson(section_id=section.id, title="Урок 1", order_index=0, questions_per_attempt=per_attempt)
    db_session.add(lesson)
    await db_session.flush()
    for i in range(questions):
        question = Question(lesson_id=lesson.id, qtype=EntQuestionType.single, text=f"Вопрос {i}", max_score=1, order_index=i)
        question.choices = [
            Choice(text="верно", is_correct=True, order_index=0),
            Choice(text="неверно", is_correct=False, order_index=1),
        ]
        db_session.add(question)
    await db_session.commit()
    return student, teacher, category, section, lesson


async def _answers(db_session, question_ids, *, correct: bool = True):
    rows = await db_session.execute(
        select(Choice.question_id, Choice.id).where(Choice.question_id.in_(question_ids), Choice.is_correct.is_(correct))
    )
    return [{"question_id": qid, "choice_id": cid} for qid, cid in rows.all()]


async def _start(client, lesson_id):
    response = await client.post(f"/api/v1/lessons/{lesson_id}/test/start")
    assert response.status_code == 200, response.text
    return response.json()


async def test_each_attempt_draws_a_different_set(client, db_session, make_user, login_as):
    student, _, _, _, lesson = await _course(db_session, make_user, questions=6, per_attempt=3, slug="pool-diff")
    login_as(student)

    first = await _start(client, lesson.id)
    first_ids = [q["id"] for q in first["questions"]]
    assert len(first_ids) == 3
    # A reload resumes the same sheet, it never redraws.
    assert [q["id"] for q in (await _start(client, lesson.id))["questions"]] == first_ids

    wrong = await _answers(db_session, first_ids, correct=False)
    result = (await client.post(f"/api/v1/test-attempts/{first['attempt_id']}/submit", json={"answers": wrong})).json()
    assert result["question_count"] == 3 and result["passed"] is False

    second_ids = [q["id"] for q in (await _start(client, lesson.id))["questions"]]
    assert len(second_ids) == 3 and not set(first_ids) & set(second_ids)


async def test_submit_grades_only_the_drawn_questions(client, db_session, make_user, login_as):
    student, _, _, _, lesson = await _course(db_session, make_user, questions=5, per_attempt=2, slug="pool-grade")
    login_as(student)
    session = await _start(client, lesson.id)
    ids = [q["id"] for q in session["questions"]]
    # Answers to questions this attempt was not given count for nothing.
    all_ids = list((await db_session.scalars(select(Question.id).where(Question.lesson_id == lesson.id))).all())
    answers = await _answers(db_session, all_ids)
    result = (await client.post(f"/api/v1/test-attempts/{session['attempt_id']}/submit", json={"answers": answers})).json()
    assert result["question_count"] == 2 and result["max_points"] == 2 and result["score"] == 100
    attempt = await db_session.get(TestAttempt, session["attempt_id"])
    await db_session.refresh(attempt)
    assert attempt.question_ids == ids


async def test_without_a_limit_the_whole_bank_in_order(client, db_session, make_user, login_as):
    student, _, _, _, lesson = await _course(db_session, make_user, questions=4, per_attempt=None, slug="pool-none")
    login_as(student)
    session = await _start(client, lesson.id)
    texts = [q["text"] for q in session["questions"]]
    assert texts == ["Вопрос 0", "Вопрос 1", "Вопрос 2", "Вопрос 3"]


async def test_an_attempt_from_before_banks_still_uses_every_question(client, db_session, make_user, login_as):
    student, _, _, _, lesson = await _course(db_session, make_user, questions=3, per_attempt=None, slug="pool-legacy")
    login_as(student)
    session = await _start(client, lesson.id)
    attempt = await db_session.get(TestAttempt, session["attempt_id"])
    attempt.question_ids = None  # as an attempt opened before the update
    await db_session.commit()
    resumed = await _start(client, lesson.id)
    assert len(resumed["questions"]) == 3


async def test_teacher_sets_questions_per_attempt_and_students_see_it(client, db_session, make_user, login_as):
    student, teacher, _, section, lesson = await _course(db_session, make_user, questions=5, per_attempt=None, slug="pool-teacher")
    login_as(teacher)
    r = await client.patch(f"/api/v1/teacher/lessons/{lesson.id}", json={"questions_per_attempt": 2})
    assert r.status_code == 200 and r.json()["questions_per_attempt"] == 2
    assert (await client.patch(f"/api/v1/teacher/sections/{section.id}", json={"questions_per_attempt": 4})).json()["questions_per_attempt"] == 4

    login_as(student)
    assert (await client.get(f"/api/v1/lessons/{lesson.id}")).json()["question_count"] == 2

    login_as(teacher)
    r = await client.patch(f"/api/v1/teacher/lessons/{lesson.id}", json={"questions_per_attempt": 0})
    assert r.json()["questions_per_attempt"] is None  # 0 = all questions
    assert (await client.patch(f"/api/v1/teacher/lessons/{lesson.id}", json={"questions_per_attempt": 500})).status_code == 422


# --- «Мои тесты» -------------------------------------------------------------


async def test_my_tests_lists_status_attempts_and_best_score(client, db_session, make_user, login_as):
    student, _teacher, _category, section, lesson = await _course(db_session, make_user, questions=5, per_attempt=2, slug="my-tests")
    second = Lesson(section_id=section.id, title="Урок 2", order_index=1)
    db_session.add(second)
    await db_session.flush()
    q = Question(section_id=section.id, qtype=EntQuestionType.single, text="Итог", max_score=1, order_index=0)
    q.choices = [Choice(text="да", is_correct=True, order_index=0), Choice(text="нет", is_correct=False, order_index=1)]
    db_session.add(q)
    await db_session.commit()
    login_as(student)

    courses = (await client.get("/api/v1/tests/my")).json()
    tests = courses[0]["sections"][0]["tests"]
    # Lesson 2 has no questions: not listed. The section test is.
    assert [(t["kind"], t["title"]) for t in tests] == [("lesson", "Урок 1"), ("section", "Раздел 1")]
    first, final = tests
    assert first["question_count"] == 2 and first["pool_size"] == 5
    assert first["is_unlocked"] and not first["is_passed"] and first["attempts_used"] == 0
    assert final["is_unlocked"] is False  # lesson 1 not passed yet

    session = await _start(client, lesson.id)
    ids = [x["id"] for x in session["questions"]]
    await client.post(f"/api/v1/test-attempts/{session['attempt_id']}/submit", json={"answers": await _answers(db_session, ids)})

    tests = (await client.get("/api/v1/tests/my")).json()[0]["sections"][0]["tests"]
    assert tests[0]["is_passed"] and tests[0]["attempts_used"] == 1 and tests[0]["best_score"] == 100
    assert tests[1]["is_unlocked"] is True


async def test_my_tests_is_for_students_only(client, make_user, login_as):
    login_as(await make_user(RoleEnum.teacher))
    assert (await client.get("/api/v1/tests/my")).status_code == 403


async def test_an_abandoned_sitting_counts_as_the_previous_one(client, db_session, make_user, login_as):
    from datetime import datetime, timedelta, timezone

    student, _, _, _, lesson = await _course(db_session, make_user, questions=6, per_attempt=3, slug="pool-stale")
    login_as(student)
    first = await _start(client, lesson.id)
    attempt = await db_session.get(TestAttempt, first["attempt_id"])
    attempt.started_at = datetime.now(timezone.utc) - timedelta(hours=3)  # left open, dropped on next start
    await db_session.commit()

    second = await _start(client, lesson.id)
    assert second["attempt_id"] != first["attempt_id"]
    assert not {q["id"] for q in first["questions"]} & {q["id"] for q in second["questions"]}
