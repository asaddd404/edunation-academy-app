"""Cross-tenant access attempts, and what the database looks like afterwards.

The pattern every test follows is deliberate: assert the status code *and*
assert the object is unchanged. A handler that answers 403 and mutates the
row anyway passes the first assertion perfectly well, and that is exactly the
bug this file exists to catch.
"""

from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from app.config import settings
from app.models.category import Category, teacher_categories
from app.models.lesson import Lesson
from app.models.question import Question
from app.models.section import Section
from app.models.user import RoleEnum, User
from app.security import create_access_token


async def _course_owned_by(db_session, teacher: User, name: str):
    """A category assigned to `teacher`, with one section, lesson and question."""
    category = Category(name=name, slug=name.lower().replace(" ", "-"), is_active=True)
    db_session.add(category)
    await db_session.flush()
    await db_session.execute(
        teacher_categories.insert().values(teacher_id=teacher.id, category_id=category.id)
    )
    section = Section(category_id=category.id, title=f"{name} раздел", order_index=0)
    db_session.add(section)
    await db_session.flush()
    lesson = Lesson(section_id=section.id, title=f"{name} урок", order_index=0)
    db_session.add(lesson)
    await db_session.flush()
    question = Question(lesson_id=lesson.id, text="Вопрос", max_score=1, order_index=0)
    db_session.add(question)
    await db_session.flush()
    await db_session.commit()
    return category, section, lesson, question


# --- teacher against another teacher's course ------------------------------

async def test_teacher_cannot_edit_another_teachers_lesson(client, db_session, make_user, login_as):
    owner = await make_user(RoleEnum.teacher)
    intruder = await make_user(RoleEnum.teacher)
    _, _, lesson, _ = await _course_owned_by(db_session, owner, "Физика")
    original_title = lesson.title

    login_as(intruder)
    response = await client.patch(f"/api/v1/teacher/lessons/{lesson.id}", json={"title": "Взломано"})

    assert response.status_code in (403, 404)
    stored = await db_session.scalar(select(Lesson.title).where(Lesson.id == lesson.id))
    assert stored == original_title


async def test_teacher_cannot_delete_another_teachers_lesson(client, db_session, make_user, login_as):
    owner = await make_user(RoleEnum.teacher)
    intruder = await make_user(RoleEnum.teacher)
    _, _, lesson, _ = await _course_owned_by(db_session, owner, "Химия")

    login_as(intruder)
    response = await client.delete(f"/api/v1/teacher/lessons/{lesson.id}")

    assert response.status_code in (403, 404)
    assert await db_session.scalar(select(Lesson.id).where(Lesson.id == lesson.id)) is not None


async def test_teacher_cannot_delete_another_teachers_section(client, db_session, make_user, login_as):
    """The most destructive teacher-level delete: the section cascade takes
    its lessons, their questions and every submission with it."""
    owner = await make_user(RoleEnum.teacher)
    intruder = await make_user(RoleEnum.teacher)
    _, section, lesson, _ = await _course_owned_by(db_session, owner, "Биология")

    login_as(intruder)
    response = await client.delete(f"/api/v1/teacher/sections/{section.id}")

    assert response.status_code in (403, 404)
    assert await db_session.scalar(select(Section.id).where(Section.id == section.id)) is not None
    assert await db_session.scalar(select(Lesson.id).where(Lesson.id == lesson.id)) is not None


async def test_teacher_cannot_delete_another_teachers_question(client, db_session, make_user, login_as):
    owner = await make_user(RoleEnum.teacher)
    intruder = await make_user(RoleEnum.teacher)
    _, _, _, question = await _course_owned_by(db_session, owner, "География")

    login_as(intruder)
    response = await client.delete(f"/api/v1/teacher/questions/{question.id}")

    assert response.status_code in (403, 404)
    assert await db_session.scalar(select(Question.id).where(Question.id == question.id)) is not None


async def test_teacher_cannot_add_a_lesson_to_another_teachers_section(client, db_session, make_user, login_as):
    owner = await make_user(RoleEnum.teacher)
    intruder = await make_user(RoleEnum.teacher)
    _, section, _, _ = await _course_owned_by(db_session, owner, "История")

    login_as(intruder)
    response = await client.post(
        f"/api/v1/teacher/sections/{section.id}/lessons", json={"title": "Подброшенный урок"}
    )

    assert response.status_code in (403, 404)
    lessons = (await db_session.scalars(select(Lesson).where(Lesson.section_id == section.id))).all()
    assert len(lessons) == 1


# --- role boundaries -------------------------------------------------------

async def test_student_cannot_reach_teacher_endpoints(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    student = await make_user(RoleEnum.student)
    _, section, lesson, _ = await _course_owned_by(db_session, teacher, "Алгебра")
    original_title = lesson.title

    login_as(student)

    assert (await client.get("/api/v1/teacher/categories")).status_code == 403
    assert (await client.patch(f"/api/v1/teacher/lessons/{lesson.id}", json={"title": "x"})).status_code == 403
    assert (await client.delete(f"/api/v1/teacher/sections/{section.id}")).status_code == 403
    assert (await client.post("/api/v1/teacher/ent/subjects", json={"name": "Своё"})).status_code == 403

    assert await db_session.scalar(select(Lesson.title).where(Lesson.id == lesson.id)) == original_title


async def test_teacher_cannot_reach_admin_endpoints(client, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    login_as(teacher)

    assert (await client.get("/api/v1/admin/users")).status_code == 403
    assert (await client.post("/api/v1/admin/categories", json={"name": "Курс"})).status_code == 403
    assert (await client.post(f"/api/v1/admin/users/{teacher.id}/reset-password")).status_code == 403


async def test_teacher_cannot_promote_themselves_to_admin(client, db_session, make_user, login_as):
    """Privilege escalation in a single request if the admin router's guard
    were ever loosened -- worth its own assertion on the stored role."""
    teacher = await make_user(RoleEnum.teacher)
    await db_session.commit()

    login_as(teacher)
    response = await client.patch(f"/api/v1/admin/users/{teacher.id}", json={"role": "admin"})

    assert response.status_code == 403
    stored = await db_session.scalar(select(User.role).where(User.id == teacher.id))
    assert stored == RoleEnum.teacher


async def test_admin_cannot_demote_themselves(client, db_session, make_user, login_as):
    """There is no console tool to restore admin rights, so an admin who
    demotes themselves locks the installation's last operator out of it."""
    admin = await make_user(RoleEnum.admin)
    await db_session.commit()

    login_as(admin)
    response = await client.patch(f"/api/v1/admin/users/{admin.id}", json={"role": "student"})

    assert response.status_code == 400
    stored = await db_session.scalar(select(User.role).where(User.id == admin.id))
    assert stored == RoleEnum.admin


async def test_admin_cannot_deactivate_themselves(client, db_session, make_user, login_as):
    admin = await make_user(RoleEnum.admin)
    await db_session.commit()

    login_as(admin)
    response = await client.patch(f"/api/v1/admin/users/{admin.id}", json={"is_active": False})

    assert response.status_code == 400
    assert await db_session.scalar(select(User.is_active).where(User.id == admin.id)) is True


# --- unauthenticated and invalid tokens ------------------------------------

async def test_no_token_is_rejected(client, db_session, make_user):
    teacher = await make_user(RoleEnum.teacher)
    _, section, lesson, _ = await _course_owned_by(db_session, teacher, "Информатика")

    cases = [
        ("get", "/api/v1/admin/users", {}),
        ("get", "/api/v1/teacher/categories", {}),
        ("patch", f"/api/v1/teacher/lessons/{lesson.id}", {"json": {}}),
        ("delete", f"/api/v1/teacher/sections/{section.id}", {}),
        ("get", "/api/v1/auth/me", {}),
    ]
    for method, path, kwargs in cases:
        response = await getattr(client, method)(path, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} answered {response.status_code}"

    assert await db_session.scalar(select(Section.id).where(Section.id == section.id)) is not None


async def test_expired_token_is_rejected(client, make_user, monkeypatch):
    """A negative TTL produces a token that is structurally valid and signed
    with the real key -- only its `exp` is in the past."""
    user = await make_user(RoleEnum.admin)
    monkeypatch.setattr(settings, "jwt_access_ttl_minutes", -5)
    expired = create_access_token(user.id, user.role.value)

    response = await client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


async def test_token_signed_with_another_key_is_rejected(client, make_user):
    """The check that stops anyone minting their own admin token."""
    user = await make_user(RoleEnum.student)
    forged = jwt.encode(
        {
            "sub": str(user.id),
            "role": "admin",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "not-the-real-secret",
        algorithm="HS256",
    )

    response = await client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


async def test_role_claim_in_the_token_does_not_override_the_database(client, db_session, make_user):
    """The token carries a `role`, but authorization reads the User row. A
    correctly signed token whose claim says admin must still be a student --
    otherwise a stale token survives a demotion as a live privilege."""
    student = await make_user(RoleEnum.student)
    await db_session.commit()
    token = create_access_token(student.id, "admin")

    response = await client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
