"""Homework attachments do not outlive their rows: deleting a lesson or a
section removes the students' files, and a resubmission replaces the old
file only once the new one is saved."""

import pytest

from app.core import storage
from app.models.homework import HomeworkSubmission
from tests.test_homework_review import PDF, PNG, _course, _submit


@pytest.fixture(autouse=True)
def uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(storage, "HOMEWORK_DIR", tmp_path / "homework")
    return tmp_path


async def _submitted_file(client, db_session, make_user, login_as, slug):
    teacher, student, lesson, _ = await _course(db_session, make_user, slug)
    login_as(student)
    created = (await _submit(client, lesson.id, "photo.png", PNG)).json()
    submission = await db_session.get(HomeworkSubmission, created["id"])
    path = storage.resolve_upload_path(submission.file_path)
    assert path.is_file()
    return teacher, student, lesson, path


async def test_deleting_a_lesson_removes_its_homework_files(client, db_session, make_user, login_as):
    teacher, _, lesson, path = await _submitted_file(client, db_session, make_user, login_as, "hw-clean-lesson")

    login_as(teacher)
    assert (await client.delete(f"/api/v1/teacher/lessons/{lesson.id}")).status_code == 204
    assert path.exists()  # in the trash: everything kept for 30 days
    assert (await client.delete(f"/api/v1/teacher/trash/lesson/{lesson.id}")).status_code == 204
    assert not path.exists()


async def test_deleting_a_section_removes_its_homework_files(client, db_session, make_user, login_as):
    teacher, _, lesson, path = await _submitted_file(client, db_session, make_user, login_as, "hw-clean-section")

    login_as(teacher)
    assert (await client.delete(f"/api/v1/teacher/sections/{lesson.section_id}")).status_code == 204
    assert path.exists()
    assert (await client.delete(f"/api/v1/teacher/trash/section/{lesson.section_id}")).status_code == 204
    assert not path.exists()


async def test_resubmitting_replaces_the_old_file(client, db_session, make_user, login_as):
    _, student, lesson, old_path = await _submitted_file(client, db_session, make_user, login_as, "hw-clean-resubmit")

    response = await _submit(client, lesson.id, "work.pdf", PDF)
    assert response.status_code == 201
    submission = await db_session.get(HomeworkSubmission, response.json()["id"], populate_existing=True)
    assert not old_path.exists()
    assert storage.resolve_upload_path(submission.file_path).is_file()
