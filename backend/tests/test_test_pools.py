"""Lesson/section tests drawn from a bank: every attempt a different set."""

import random

from app.core.test_draw import draw_question_ids
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category, teacher_categories
from app.models.lesson import Lesson
from app.models.question import Choice, Question
from app.models.section import Section
from app.models.user import RoleEnum


# --- the draw ----------------------------------------------------------------

def test_draw_prefers_questions_the_last_attempt_did_not_show():
    pool = list(range(1, 7))
    first = draw_question_ids(pool, 3, None, random.Random(1))
    second = draw_question_ids(pool, 3, first, random.Random(2))
    assert len(first) == len(second) == 3
    assert not set(first) & set(second)


def test_draw_tops_up_from_the_last_attempt_when_the_bank_is_small():
    pool = [1, 2, 3, 4]
    second = draw_question_ids(pool, 3, [1, 2, 3], random.Random(3))
    assert 4 in second and len(set(second)) == 3


def test_draw_never_repeats_the_same_order_for_the_same_set():
    pool = [1, 2, 3]
    previous = [1, 2, 3]
    for seed in range(50):
        assert draw_question_ids(pool, None, previous, random.Random(seed)) != previous


def test_draw_without_a_limit_takes_the_whole_bank():
    assert sorted(draw_question_ids([5, 6, 7], None, None, random.Random(0))) == [5, 6, 7]
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
        question = Question(lesson_id=lesson.id, text=f"Вопрос {i}", max_score=1, order_index=i)
        question.choices = [
            Choice(text="верно", is_correct=True, order_index=0),
            Choice(text="неверно", is_correct=False, order_index=1),
        ]
        db_session.add(question)
    await db_session.commit()
    return student, teacher, category, section, lesson


async def _correct_answers(db_session, question_ids):
    from sqlalchemy import select

    rows = await db_session.execute(
        select(Choice.question_id, Choice.id).where(Choice.question_id.in_(question_ids), Choice.is_correct.is_(True))
    )
    return [{"question_id": qid, "choice_id": cid} for qid, cid in rows.all()]


async def test_each_attempt_draws_a_different_set(client, db_session, make_user, login_as):
    student, _, _, _, lesson = await _course(db_session, make_user, questions=6, per_attempt=3, slug="pool-diff")
    login_as(student)

    info = (await client.get(f"/api/v1/lessons/{lesson.id}/test")).json()
    assert info["question_count"] == 3 and info["pool_size"] == 6

    first = (await client.post(f"/api/v1/lessons/{lesson.id}/test/attempts/start")).json()
    first_ids = [q["id"] for q in first["questions"]]
    assert len(first_ids) == 3

    # Reopening the page resumes the same attempt instead of rerolling it.
    again = (await client.post(f"/api/v1/lessons/{lesson.id}/test/attempts/start")).json()
    assert again["attempt_id"] == first["attempt_id"]
    assert [q["id"] for q in again["questions"]] == first_ids
    assert [c["id"] for c in again["questions"][0]["choices"]] == [c["id"] for c in first["questions"][0]["choices"]]

    answers = await _correct_answers(db_session, first_ids)
    result = await client.post(
        f"/api/v1/lessons/{lesson.id}/test/attempts", json={"attempt_id": first["attempt_id"], "answers": answers}
    )
    # Graded on the three questions shown, not on the six in the bank.
    assert result.status_code == 201
    assert result.json()["score"] == 100

    second = (await client.post(f"/api/v1/lessons/{lesson.id}/test/attempts/start")).json()
    assert second["attempt_id"] != first["attempt_id"]
    assert not set(first_ids) & {q["id"] for q in second["questions"]}


async def test_an_attempt_cannot_be_submitted_twice(client, db_session, make_user, login_as):
    student, _, _, _, lesson = await _course(db_session, make_user, questions=2, per_attempt=None, slug="pool-twice")
    login_as(student)
    start = (await client.post(f"/api/v1/lessons/{lesson.id}/test/attempts/start")).json()
    body = {"attempt_id": start["attempt_id"], "answers": []}

    assert (await client.post(f"/api/v1/lessons/{lesson.id}/test/attempts", json=body)).status_code == 201
    assert (await client.post(f"/api/v1/lessons/{lesson.id}/test/attempts", json=body)).status_code == 409


async def test_legacy_submit_without_attempt(client, db_session, make_user, login_as):
    """A page from before the change still works for a whole-bank test, and
    is told to reload for a drawn one."""
    student, _, _, _, lesson = await _course(db_session, make_user, questions=2, per_attempt=None, slug="pool-legacy")
    login_as(student)
    assert (await client.post(f"/api/v1/lessons/{lesson.id}/test/attempts", json={"answers": []})).status_code == 201

    lesson.questions_per_attempt = 1
    await db_session.commit()
    assert (await client.post(f"/api/v1/lessons/{lesson.id}/test/attempts", json={"answers": []})).status_code == 409


async def test_someone_elses_attempt_is_not_found(client, db_session, make_user, login_as):
    student, _, category, _, lesson = await _course(db_session, make_user, questions=2, per_attempt=None, slug="pool-other")
    other = await make_user(RoleEnum.student)
    db_session.add(Application(student_id=other.id, category_id=category.id, status=ApplicationStatusEnum.approved))
    await db_session.commit()
    login_as(student)
    start = (await client.post(f"/api/v1/lessons/{lesson.id}/test/attempts/start")).json()

    login_as(other)
    response = await client.post(
        f"/api/v1/lessons/{lesson.id}/test/attempts", json={"attempt_id": start["attempt_id"], "answers": []}
    )
    assert response.status_code == 404


async def test_lesson_page_does_not_list_the_bank(client, db_session, make_user, login_as):
    student, _, _, _, lesson = await _course(db_session, make_user, questions=5, per_attempt=2, slug="pool-hidden")
    login_as(student)
    body = (await client.get(f"/api/v1/lessons/{lesson.id}")).json()
    assert "questions" not in body
    assert body["has_test"] is True and body["test_question_count"] == 2


async def test_locked_test_cannot_be_started(client, db_session, make_user, login_as):
    student, _, _, section, _ = await _course(db_session, make_user, questions=1, per_attempt=None, slug="pool-locked")
    second = Lesson(section_id=section.id, title="Урок 2", order_index=1)
    db_session.add(second)
    await db_session.flush()
    db_session.add(Question(lesson_id=second.id, text="?", max_score=1, order_index=0))
    await db_session.commit()
    login_as(student)

    assert (await client.get(f"/api/v1/lessons/{second.id}/test")).json()["is_unlocked"] is False
    assert (await client.post(f"/api/v1/lessons/{second.id}/test/attempts/start")).status_code == 403


async def test_tests_hub_lists_lesson_and_section_tests(client, db_session, make_user, login_as):
    student, _, category, section, lesson = await _course(db_session, make_user, questions=3, per_attempt=2, slug="pool-hub")
    db_session.add(Question(section_id=section.id, text="Итоговый", max_score=1, order_index=0))
    await db_session.commit()
    login_as(student)

    hub = (await client.get("/api/v1/me/tests")).json()

    assert [c["category_id"] for c in hub] == [category.id]
    hub_section = hub[0]["sections"][0]
    assert hub_section["lesson_tests"][0]["id"] == lesson.id
    assert hub_section["lesson_tests"][0]["question_count"] == 2
    assert hub_section["section_test"]["kind"] == "section"
    assert hub_section["section_test"]["is_unlocked"] is False


async def test_teacher_sets_questions_per_attempt(client, db_session, make_user, login_as):
    _, teacher, category, section, lesson = await _course(db_session, make_user, questions=4, per_attempt=None, slug="pool-teacher")
    login_as(teacher)

    lesson_out = await client.patch(f"/api/v1/teacher/lessons/{lesson.id}", json={"questions_per_attempt": 2})
    section_out = await client.patch(f"/api/v1/teacher/sections/{section.id}", json={"questions_per_attempt": 5})
    assert lesson_out.json()["questions_per_attempt"] == 2
    assert section_out.json()["questions_per_attempt"] == 5

    reset = await client.patch(f"/api/v1/teacher/lessons/{lesson.id}", json={"questions_per_attempt": 0})
    assert reset.json()["questions_per_attempt"] is None

    listing = (await client.get(f"/api/v1/teacher/categories/{category.id}/sections")).json()
    assert listing[0]["lessons"][0]["question_count"] == 4
