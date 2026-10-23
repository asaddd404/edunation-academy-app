"""Edge cases from the functional QA pass: profile text, column-width limits,
characters Postgres refuses, and the request-size ceiling.

Several of these were 500s -- a 101-character name, a NUL byte, a category
name longer than its column -- and the rest were accepted when they should
not have been: a name that is only a newline, or one that renders backwards.
"""

import pytest
from sqlalchemy import select

from app.config import settings
from app.core.middleware import BodySizeLimitMiddleware
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category, teacher_categories
from app.models.lesson import Lesson
from app.models.section import Section
from app.models.user import RoleEnum, User

REGISTER = {"phone": "+77779991000", "password": "Passw0rd!x", "first_name": "Имя", "last_name": "Фамилия"}


# --- profile names ----------------------------------------------------------


async def test_profile_trims_names(client, db_session, make_user, login_as):
    user = await make_user(RoleEnum.student)
    login_as(user)

    response = await client.patch("/api/v1/me", json={"first_name": "  Алия  ", "last_name": " Тестова "})

    assert response.status_code == 200
    assert (response.json()["first_name"], response.json()["last_name"]) == ("Алия", "Тестова")


@pytest.mark.parametrize(
    "value",
    ["Ан\nна", "Ан\tна", "Ан\x00на", "Анна‮анна", "​​", " ​ "],
    ids=["newline", "tab", "nul", "rlo", "zero-width-only", "spaces-and-zero-width"],
)
async def test_profile_refuses_unprintable_names(client, make_user, login_as, value):
    user = await make_user(RoleEnum.student)
    login_as(user)

    response = await client.patch("/api/v1/me", json={"first_name": value})

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("value", ["Әсел-Ұлбосын", "O'Brien", "Анна 😊", "Жан Поль"])
async def test_profile_keeps_real_names(client, make_user, login_as, value):
    user = await make_user(RoleEnum.student)
    login_as(user)

    response = await client.patch("/api/v1/me", json={"first_name": value})

    assert response.status_code == 200 and response.json()["first_name"] == value


async def test_name_length_follows_the_column(client, db_session, make_user, login_as):
    """users.first_name is VARCHAR(100); 101-200 used to pass validation and
    fail the INSERT with a 500."""
    user = await make_user(RoleEnum.student)
    login_as(user)

    assert (await client.patch("/api/v1/me", json={"first_name": "А" * 100})).status_code == 200
    assert (await client.patch("/api/v1/me", json={"first_name": "А" * 101})).status_code == 422
    assert (await client.post("/api/v1/auth/register", json={**REGISTER, "last_name": "Б" * 101})).status_code == 422
    stored = await db_session.scalar(select(User.first_name).where(User.id == user.id))
    assert stored == "А" * 100


async def test_register_refuses_unprintable_names(client):
    response = await client.post("/api/v1/auth/register", json={**REGISTER, "first_name": "Ан\nна"})

    assert response.status_code == 422


# --- catalog and ЕНТ names / texts longer than their columns ---------------


async def test_category_name_longer_than_column_is_422(client, make_user, login_as):
    admin = await make_user(RoleEnum.admin)
    login_as(admin)

    assert (await client.post("/api/v1/admin/categories", json={"name": "К" * 151})).status_code == 422
    assert (await client.post("/api/v1/admin/categories", json={"name": "К" * 150})).status_code == 201


async def test_ent_subject_and_question_limits(client, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    login_as(teacher)

    assert (await client.post("/api/v1/teacher/ent/subjects", json={"name": "П" * 151})).status_code == 422
    subject = (await client.post("/api/v1/teacher/ent/subjects", json={"name": "Физика"})).json()
    question = {
        "qtype": "single",
        "text": "Q" * 1001,
        "choices": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": False}],
    }
    response = await client.post(f"/api/v1/teacher/ent/subjects/{subject['id']}/questions", json=question)
    assert response.status_code == 422


# --- the database refusing text: a 422, never a 500 -------------------------


async def test_nul_byte_in_free_text_is_a_422(client, db_session, make_user, login_as):
    """Homework text has no character rules of its own; a NUL byte in it is
    refused by Postgres. The app-level handler turns that into a 422."""
    teacher = await make_user(RoleEnum.teacher)
    student = await make_user(RoleEnum.student)
    category = Category(name="qa-nul", slug="qa-nul", is_active=True)
    db_session.add(category)
    await db_session.flush()
    await db_session.execute(teacher_categories.insert().values(teacher_id=teacher.id, category_id=category.id))
    section = Section(category_id=category.id, title="Раздел", order_index=0)
    db_session.add(section)
    await db_session.flush()
    lesson = Lesson(section_id=section.id, title="Урок", order_index=0)
    db_session.add_all(
        [lesson, Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved)]
    )
    await db_session.commit()
    login_as(student)

    response = await client.post(f"/api/v1/lessons/{lesson.id}/homework", data={"text_answer": "x\x00y"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Текст содержит недопустимые символы."


# --- request size ceiling ----------------------------------------------------


def test_only_video_uploads_skip_the_body_ceiling():
    exempt = BodySizeLimitMiddleware._is_exempt
    assert exempt("/api/v1/teacher/lessons/12/video")
    assert not exempt("/api/v1/teacher/lessons/12")
    assert not exempt("/api/v1/teacher/lessons/12/questions")
    assert not exempt("/api/v1/me")


async def test_oversized_json_to_a_lesson_is_refused_before_parsing(client, make_user, login_as, monkeypatch):
    """The whole /teacher/lessons/ prefix used to be exempt, so a lesson
    PATCH would read and parse any size of JSON."""
    monkeypatch.setattr(settings, "max_request_body_bytes", 1024)
    teacher = await make_user(RoleEnum.teacher)
    login_as(teacher)

    response = await client.patch(
        "/api/v1/teacher/lessons/1",
        content='{"title": "' + "x" * 4096 + '"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
