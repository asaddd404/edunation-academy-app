"""The teacher's homework review: attachments that can be opened, a grade,
the time of submission, and the work filtered by status or student."""

import pytest

from app.core import storage
from app.models.application import Application, ApplicationStatusEnum
from app.models.lesson import Lesson
from app.models.section import Section
from app.models.user import RoleEnum
from tests.test_qa_regressions import _owned_category

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64
DOCX = b"PK\x03\x04" + b"\x00" * 64


@pytest.fixture(autouse=True)
def uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(storage, "HOMEWORK_DIR", tmp_path / "homework")
    return tmp_path


async def _course(db_session, make_user, slug):
    teacher = await make_user(RoleEnum.teacher)
    student = await make_user(RoleEnum.student)
    category = await _owned_category(db_session, teacher, slug)
    section = Section(category_id=category.id, title="Раздел", order_index=0)
    db_session.add(section)
    await db_session.flush()
    lesson = Lesson(section_id=section.id, title="Урок", order_index=0)
    db_session.add_all([lesson, Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved)])
    await db_session.commit()
    return teacher, student, lesson, category


async def _submit(client, lesson_id, name, body, text="решение"):
    return await client.post(f"/api/v1/lessons/{lesson_id}/homework", data={"text_answer": text}, files={"file": (name, body)})


@pytest.mark.parametrize(
    ("name", "body", "kind", "media_type"),
    [("photo.png", PNG, "image", "image/png"), ("essay.pdf", PDF, "pdf", "application/pdf")],
)
async def test_images_and_pdfs_can_be_previewed_inline(client, db_session, make_user, login_as, name, body, kind, media_type):
    teacher, student, lesson, _ = await _course(db_session, make_user, f"hw-inline-{kind}")
    login_as(student)
    submission = (await _submit(client, lesson.id, name, body)).json()
    assert submission["file_kind"] == kind
    login_as(teacher)

    preview = await client.get(f"/api/v1/homework/{submission['id']}/file?inline=1")

    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith(media_type)
    assert preview.headers["content-disposition"].startswith("inline")
    assert preview.headers["x-content-type-options"] == "nosniff"


async def test_documents_only_ever_download(client, db_session, make_user, login_as):
    teacher, student, lesson, _ = await _course(db_session, make_user, "hw-docx")
    login_as(student)
    submission = (await _submit(client, lesson.id, "work.docx", DOCX)).json()
    assert submission["file_kind"] == "document"
    login_as(teacher)

    response = await client.get(f"/api/v1/homework/{submission['id']}/file?inline=1")

    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["content-type"] == "application/octet-stream"


async def test_review_records_a_grade_and_a_resubmission_clears_it(client, db_session, make_user, login_as):
    teacher, student, lesson, _ = await _course(db_session, make_user, "hw-grade")
    login_as(student)
    first = (await _submit(client, lesson.id, "photo.png", PNG)).json()
    login_as(teacher)

    reviewed = await client.post(
        f"/api/v1/teacher/homework/{first['id']}/review", json={"status": "revision_requested", "grade": 55}
    )
    assert reviewed.status_code == 200 and reviewed.json()["grade"] == 55

    login_as(student)
    again = (await _submit(client, lesson.id, "photo.png", PNG, text="исправил")).json()
    assert again["grade"] is None and again["status"] == "submitted"
    assert again["submitted_at"] > first["submitted_at"]


@pytest.mark.parametrize("grade", [-1, 101])
async def test_grade_must_be_0_to_100(client, db_session, make_user, login_as, grade):
    teacher, student, lesson, _ = await _course(db_session, make_user, f"hw-range-{grade}")
    login_as(student)
    submission = (await _submit(client, lesson.id, "photo.png", PNG)).json()
    login_as(teacher)

    response = await client.post(f"/api/v1/teacher/homework/{submission['id']}/review", json={"status": "accepted", "grade": grade})

    assert response.status_code == 422


async def test_list_filters_by_status_and_student_and_names_the_course(client, db_session, make_user, login_as):
    teacher, student, lesson, category = await _course(db_session, make_user, "hw-list")
    login_as(student)
    submission = (await _submit(client, lesson.id, "photo.png", PNG)).json()
    login_as(teacher)

    queue = (await client.get("/api/v1/teacher/homework?status=submitted")).json()
    assert [s["id"] for s in queue] == [submission["id"]]
    assert queue[0]["category_id"] == category.id and queue[0]["category_name"] == category.name
    assert queue[0]["student_name"] and queue[0]["student_phone"]

    await client.post(f"/api/v1/teacher/homework/{submission['id']}/review", json={"status": "accepted", "grade": 90})
    assert (await client.get("/api/v1/teacher/homework?status=submitted")).json() == []
    reviewed = (await client.get("/api/v1/teacher/homework?status=reviewed")).json()
    assert reviewed[0]["grade"] == 90
    assert (await client.get(f"/api/v1/teacher/homework?status=all&student_id={student.id}")).json()[0]["id"] == submission["id"]
    assert (await client.get(f"/api/v1/teacher/homework?status=all&student_id={student.id + 999}")).json() == []


async def test_another_teachers_homework_is_not_listed(client, db_session, make_user, login_as):
    _, student, lesson, _ = await _course(db_session, make_user, "hw-other")
    login_as(student)
    await _submit(client, lesson.id, "photo.png", PNG)
    login_as(await make_user(RoleEnum.teacher))

    assert (await client.get("/api/v1/teacher/homework?status=all")).json() == []
