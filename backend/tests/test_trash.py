"""«Корзина»: deleted lessons and sections wait 30 days and come back whole."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.trash import purge_trash
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category, teacher_categories
from app.models.ent_question import EntQuestionType
from app.models.lesson import Lesson
from app.models.question import Choice, Question
from app.models.section import Section
from app.models.test_attempt import TestAttempt, TestAttemptStatus
from app.models.trash import TrashItem
from app.models.user import RoleEnum


async def _course(db_session, make_user, slug: str):
    teacher = await make_user(RoleEnum.teacher)
    student = await make_user(RoleEnum.student)
    category = Category(name=slug, slug=slug, is_active=True)
    db_session.add(category)
    await db_session.flush()
    await db_session.execute(teacher_categories.insert().values(teacher_id=teacher.id, category_id=category.id))
    db_session.add(Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved))
    s1 = Section(category_id=category.id, title="Раздел 1", order_index=0)
    s2 = Section(category_id=category.id, title="Раздел 2", order_index=1)
    db_session.add_all([s1, s2])
    await db_session.flush()
    lessons = [Lesson(section_id=s1.id, title=f"Урок {i + 1}", order_index=i) for i in range(3)]
    db_session.add_all(lessons)
    await db_session.flush()
    q = Question(lesson_id=lessons[1].id, qtype=EntQuestionType.single, text="?", max_score=1, order_index=0)
    q.choices = [Choice(text="да", is_correct=True, order_index=0), Choice(text="нет", is_correct=False, order_index=1)]
    db_session.add(q)
    # The student passed lesson 2's test: their result must survive the trip.
    db_session.add(
        TestAttempt(
            student_id=student.id,
            lesson_id=lessons[1].id,
            status=TestAttemptStatus.completed,
            score=100,
            passed=True,
            submitted_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()
    return teacher, student, category, s1, s2, lessons


async def _titles(client, category_id):
    sections = (await client.get(f"/api/v1/teacher/categories/{category_id}/sections")).json()
    return [(s["title"], [l["title"] for l in s["lessons"]]) for s in sections]


async def test_deleted_lesson_goes_to_the_trash_and_comes_back_in_place(client, db_session, make_user, login_as):
    teacher, student, category, _s1, _s2, lessons = await _course(db_session, make_user, "trash-lesson")
    login_as(teacher)
    assert (await client.delete(f"/api/v1/teacher/lessons/{lessons[1].id}")).status_code == 204
    assert await _titles(client, category.id) == [("Раздел 1", ["Урок 1", "Урок 3"]), ("Раздел 2", [])]

    trash = (await client.get("/api/v1/teacher/trash")).json()
    assert [(t["kind"], t["title"], t["course"]) for t in trash] == [("lesson", "Урок 2", "trash-lesson")]
    assert trash[0]["deleted_by"]

    login_as(student)
    assert (await client.get(f"/api/v1/lessons/{lessons[1].id}")).status_code == 403

    login_as(teacher)
    r = await client.post(f"/api/v1/teacher/trash/lesson/{lessons[1].id}/restore")
    assert r.status_code == 200 and "восстановлен" in r.json()["message"]
    assert await _titles(client, category.id) == [("Раздел 1", ["Урок 1", "Урок 2", "Урок 3"]), ("Раздел 2", [])]
    assert (await client.get("/api/v1/teacher/trash")).json() == []
    attempts = (await db_session.scalars(select(TestAttempt).where(TestAttempt.lesson_id == lessons[1].id))).all()
    assert len(attempts) == 1 and attempts[0].passed


async def test_deleted_section_comes_back_with_its_lessons(client, db_session, make_user, login_as):
    teacher, _student, category, s1, _s2, _lessons = await _course(db_session, make_user, "trash-section")
    login_as(teacher)
    assert (await client.delete(f"/api/v1/teacher/sections/{s1.id}")).status_code == 204
    assert await _titles(client, category.id) == [("Раздел 2", [])]
    assert (await client.get("/api/v1/teacher/trash")).json()[0]["lesson_count"] == 3

    assert (await client.post(f"/api/v1/teacher/trash/section/{s1.id}/restore")).status_code == 200
    assert await _titles(client, category.id) == [("Раздел 1", ["Урок 1", "Урок 2", "Урок 3"]), ("Раздел 2", [])]


async def test_lesson_whose_section_is_gone_lands_in_the_first_section(client, db_session, make_user, login_as):
    teacher, _student, category, s1, _s2, lessons = await _course(db_session, make_user, "trash-orphan")
    login_as(teacher)
    await client.delete(f"/api/v1/teacher/lessons/{lessons[0].id}")
    await client.delete(f"/api/v1/teacher/sections/{s1.id}")
    r = await client.post(f"/api/v1/teacher/trash/lesson/{lessons[0].id}/restore")
    assert r.status_code == 200 and "Раздел 2" in r.json()["message"]
    assert await _titles(client, category.id) == [("Раздел 2", ["Урок 1"])]


async def test_another_teacher_cannot_see_or_restore(client, db_session, make_user, login_as):
    teacher, _student, _category, _s1, _s2, lessons = await _course(db_session, make_user, "trash-foreign")
    login_as(teacher)
    await client.delete(f"/api/v1/teacher/lessons/{lessons[0].id}")
    login_as(await make_user(RoleEnum.teacher))
    assert (await client.get("/api/v1/teacher/trash")).json() == []
    assert (await client.post(f"/api/v1/teacher/trash/lesson/{lessons[0].id}/restore")).status_code == 403


async def test_the_trash_course_is_never_listed(client, db_session, make_user, login_as):
    teacher, _student, _category, _s1, _s2, lessons = await _course(db_session, make_user, "trash-hidden")
    login_as(teacher)
    await client.delete(f"/api/v1/teacher/lessons/{lessons[0].id}")
    admin = await make_user(RoleEnum.admin)
    login_as(admin)
    assert all(not c["slug"].startswith("__") for c in (await client.get("/api/v1/teacher/categories")).json())
    assert all(not c["slug"].startswith("__") for c in (await client.get("/api/v1/admin/categories")).json()["items"])
    assert all(c["name"] != "Корзина (служебный)" for c in (await client.get("/api/v1/teacher/today")).json()["courses"])


async def test_after_30_days_it_is_gone_for_good(client, db_session, make_user, login_as):
    teacher, _student, _category, s1, _s2, lessons = await _course(db_session, make_user, "trash-purge")
    login_as(teacher)
    await client.delete(f"/api/v1/teacher/lessons/{lessons[2].id}")
    await client.delete(f"/api/v1/teacher/sections/{s1.id}")
    # Fresh: nothing is purged.
    assert await purge_trash(db_session) == 0
    for item in (await db_session.scalars(select(TrashItem))).all():
        item.deleted_at = datetime.now(timezone.utc) - timedelta(days=31)
    await db_session.commit()

    assert await purge_trash(db_session) == 2
    db_session.expunge_all()
    assert await db_session.get(Section, s1.id) is None
    for lesson in lessons:
        assert await db_session.get(Lesson, lesson.id) is None
    assert (await db_session.scalars(select(TrashItem))).all() == []
