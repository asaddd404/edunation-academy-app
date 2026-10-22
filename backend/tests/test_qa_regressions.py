"""Regressions for what a full QA pass of the site turned up.

Each test is the exact request that misbehaved, and what it must do now:
a section created from the course builder was a 500, and several names and
titles accepted nothing but spaces.
"""

import pytest
from sqlalchemy import func, select

from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category, teacher_categories
from app.models.homework import HomeworkSubmission
from app.models.lesson import Lesson
from app.models.question import Question
from app.models.section import Section
from app.models.user import RoleEnum, User


async def _owned_category(db_session, teacher, slug: str) -> Category:
    category = Category(name=slug, slug=slug, is_active=True)
    db_session.add(category)
    await db_session.flush()
    await db_session.execute(teacher_categories.insert().values(teacher_id=teacher.id, category_id=category.id))
    await db_session.commit()
    return category


# --- section create (was MissingGreenlet -> 500) -----------------------------


async def test_teacher_creates_a_section(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    category = await _owned_category(db_session, teacher, "qa-section-create")
    login_as(teacher)

    response = await client.post(
        f"/api/v1/teacher/categories/{category.id}/sections", json={"title": "Новый раздел", "description": "о чём"}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Новый раздел"
    assert body["lessons"] == []
    assert body["order_index"] == 0

    second = await client.post(f"/api/v1/teacher/categories/{category.id}/sections", json={"title": "Второй"})
    assert second.status_code == 201
    assert second.json()["order_index"] == 1
    listed = (await client.get(f"/api/v1/teacher/categories/{category.id}/sections")).json()
    assert [s["title"] for s in listed] == ["Новый раздел", "Второй"]


# --- blank names and titles -------------------------------------------------


@pytest.mark.parametrize("field", ["first_name", "last_name"])
async def test_register_refuses_blank_names(client, field):
    payload = {"phone": "+77779990001", "password": "Passw0rd!x", "first_name": "Имя", "last_name": "Фамилия"}
    payload[field] = "   "

    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422
    assert "Поле не может быть пустым" in response.text


async def test_register_trims_names(client, db_session):
    response = await client.post(
        "/api/v1/auth/register",
        json={"phone": "+77779990002", "password": "Passw0rd!x", "first_name": "  Алия ", "last_name": " Тестова  "},
    )

    assert response.status_code == 201
    user = await db_session.scalar(select(User).where(User.phone == "+77779990002"))
    assert (user.first_name, user.last_name) == ("Алия", "Тестова")


async def test_section_and_lesson_titles_must_not_be_blank(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    category = await _owned_category(db_session, teacher, "qa-blank-titles")
    login_as(teacher)

    assert (await client.post(f"/api/v1/teacher/categories/{category.id}/sections", json={"title": "  "})).status_code == 422
    section = (await client.post(f"/api/v1/teacher/categories/{category.id}/sections", json={"title": "Раздел"})).json()
    assert (await client.patch(f"/api/v1/teacher/sections/{section['id']}", json={"title": ""})).status_code == 422

    assert (await client.post(f"/api/v1/teacher/sections/{section['id']}/lessons", json={"title": " \t "})).status_code == 422
    lesson = (await client.post(f"/api/v1/teacher/sections/{section['id']}/lessons", json={"title": "Урок"})).json()
    assert (await client.patch(f"/api/v1/teacher/lessons/{lesson['id']}", json={"title": ""})).status_code == 422
    # Omitting the title in a PATCH still leaves it alone.
    renamed = await client.patch(f"/api/v1/teacher/lessons/{lesson['id']}", json={"homework_assignment": "ДЗ"})
    assert renamed.status_code == 200 and renamed.json()["title"] == "Урок"

    titles = (await db_session.scalars(select(Lesson.title).where(Lesson.section_id == section["id"]))).all()
    assert titles == ["Урок"]
    assert await db_session.scalar(select(func.count(Section.id)).where(Section.category_id == category.id)) == 1


async def test_category_name_must_not_be_blank(client, make_user, login_as):
    admin = await make_user(RoleEnum.admin)
    login_as(admin)

    assert (await client.post("/api/v1/admin/categories", json={"name": "   "})).status_code == 422
    created = await client.post("/api/v1/admin/categories", json={"name": "  Химия  "})
    assert created.status_code == 201 and created.json()["name"] == "Химия"
    assert (await client.patch(f"/api/v1/admin/categories/{created.json()['id']}", json={"name": " "})).status_code == 422


# --- homework that is only whitespace ---------------------------------------


async def test_whitespace_homework_is_not_a_submission(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    student = await make_user(RoleEnum.student)
    category = await _owned_category(db_session, teacher, "qa-homework-blank")
    section = Section(category_id=category.id, title="Раздел", order_index=0)
    db_session.add(section)
    await db_session.flush()
    lesson = Lesson(section_id=section.id, title="Урок", order_index=0)
    db_session.add_all(
        [lesson, Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved)]
    )
    await db_session.commit()
    login_as(student)

    blank = await client.post(f"/api/v1/lessons/{lesson.id}/homework", data={"text_answer": "  \n "})
    assert blank.status_code == 400
    assert await db_session.scalar(select(func.count(HomeworkSubmission.id))) == 0

    real = await client.post(f"/api/v1/lessons/{lesson.id}/homework", data={"text_answer": "  x = 5  "})
    assert real.status_code == 201
    assert real.json()["text_answer"] == "x = 5"


# --- deleting a section or lesson that has children (was a 500) --------------


async def _section_with_content(client, db_session, teacher, slug: str):
    category = await _owned_category(db_session, teacher, slug)
    section = (await client.post(f"/api/v1/teacher/categories/{category.id}/sections", json={"title": "Раздел"})).json()
    lesson = (await client.post(f"/api/v1/teacher/sections/{section['id']}/lessons", json={"title": "Урок"})).json()
    single = {
        "qtype": "single",
        "text": "2+2",
        "choices": [{"text": "4", "is_correct": True}, {"text": "5", "is_correct": False}],
    }
    await client.post(f"/api/v1/teacher/lessons/{lesson['id']}/questions", json=single)
    await client.post(f"/api/v1/teacher/sections/{section['id']}/questions", json=single)
    return section, lesson


async def test_teacher_deletes_a_section_with_lessons_and_questions(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    login_as(teacher)
    section, lesson = await _section_with_content(client, db_session, teacher, "qa-delete-section")

    response = await client.delete(f"/api/v1/teacher/sections/{section['id']}")

    assert response.status_code == 204, response.text
    assert await db_session.get(Section, section["id"]) is None
    assert await db_session.get(Lesson, lesson["id"]) is None
    assert await db_session.scalar(select(func.count(Question.id))) == 0


async def test_teacher_deletes_a_lesson_with_questions(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    login_as(teacher)
    section, lesson = await _section_with_content(client, db_session, teacher, "qa-delete-lesson")

    response = await client.delete(f"/api/v1/teacher/lessons/{lesson['id']}")

    assert response.status_code == 204, response.text
    assert await db_session.get(Lesson, lesson["id"]) is None
    # The section's own test is untouched.
    remaining = (await db_session.scalars(select(Question.section_id))).all()
    assert remaining == [section["id"]]
