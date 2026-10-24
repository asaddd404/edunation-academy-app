"""Attachments of reviewed homework are deleted a few days after the review;
the answer, grade and status stay."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.core import retention, storage
from app.models.homework import HomeworkStatusEnum, HomeworkSubmission
from app.models.user import RoleEnum
from tests.test_homework_review import PNG, _course, _submit

DAYS = settings.homework_file_retention_days


@pytest.fixture(autouse=True)
def uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(storage, "HOMEWORK_DIR", tmp_path / "homework")
    return tmp_path


async def _reviewed(client, db_session, make_user, login_as, slug, *, status, reviewed_days_ago):
    teacher, student, lesson, _ = await _course(db_session, make_user, slug)
    login_as(student)
    created = (await _submit(client, lesson.id, "photo.png", PNG)).json()
    submission = await db_session.get(HomeworkSubmission, created["id"])
    if status != HomeworkStatusEnum.submitted:
        submission.status = status
        submission.grade = 80
        submission.reviewed_at = datetime.now(timezone.utc) - timedelta(days=reviewed_days_ago)
    await db_session.commit()
    return teacher, student, submission, storage.resolve_upload_path(submission.file_path)


async def _purge(test_engine):
    async with async_sessionmaker(test_engine, expire_on_commit=False)() as db:
        return await retention.purge_expired_homework_files(db)


@pytest.mark.parametrize("status", [HomeworkStatusEnum.accepted, HomeworkStatusEnum.revision_requested])
async def test_files_of_work_reviewed_past_the_period_are_deleted(client, db_session, make_user, login_as, test_engine, status):
    _, _, submission, path = await _reviewed(
        client, db_session, make_user, login_as, f"ret-old-{status.value}", status=status, reviewed_days_ago=DAYS + 1
    )
    assert path.is_file()

    assert await _purge(test_engine) == 1

    await db_session.refresh(submission)
    assert not path.exists()
    assert submission.file_path is None and submission.file_deleted_at is not None
    # Everything but the file stays.
    assert submission.text_answer and submission.grade == 80 and submission.status == status
    assert submission.file_original_name == "photo.png"


async def test_recently_reviewed_and_unreviewed_work_keeps_its_file(client, db_session, make_user, login_as, test_engine):
    _, _, recent, recent_path = await _reviewed(
        client, db_session, make_user, login_as, "ret-recent", status=HomeworkStatusEnum.accepted, reviewed_days_ago=DAYS - 1
    )
    _, _, pending, pending_path = await _reviewed(
        client, db_session, make_user, login_as, "ret-pending", status=HomeworkStatusEnum.submitted, reviewed_days_ago=0
    )

    assert await _purge(test_engine) == 0
    assert recent_path.is_file() and pending_path.is_file()


async def test_a_file_already_missing_on_disk_is_still_marked(client, db_session, make_user, login_as, test_engine):
    _, _, submission, path = await _reviewed(
        client, db_session, make_user, login_as, "ret-missing", status=HomeworkStatusEnum.accepted, reviewed_days_ago=DAYS + 5
    )
    path.unlink()

    assert await _purge(test_engine) == 1
    await db_session.refresh(submission)
    assert submission.file_deleted_at is not None


async def test_the_api_reports_the_deletion_and_refuses_the_download(client, db_session, make_user, login_as, test_engine):
    teacher, _, submission, _ = await _reviewed(
        client, db_session, make_user, login_as, "ret-api", status=HomeworkStatusEnum.accepted, reviewed_days_ago=DAYS + 1
    )
    await _purge(test_engine)
    login_as(teacher)

    item = (await client.get("/api/v1/teacher/homework?status=all")).json()[0]
    assert item["file_deleted"] is True and item["file_kind"] is None and item["file_expires_at"] is None
    response = await client.get(f"/api/v1/homework/{submission.id}/file")
    assert response.status_code == 410


async def test_reviewed_work_says_when_its_file_will_go(client, db_session, make_user, login_as):
    teacher, _, submission, _ = await _reviewed(
        client, db_session, make_user, login_as, "ret-expiry", status=HomeworkStatusEnum.accepted, reviewed_days_ago=1
    )
    login_as(teacher)

    item = (await client.get("/api/v1/teacher/homework?status=all")).json()[0]
    expires = datetime.fromisoformat(item["file_expires_at"])
    assert expires == submission.reviewed_at + timedelta(days=DAYS)
    assert item["file_deleted"] is False


async def test_a_new_upload_replaces_the_old_file_on_disk(client, db_session, make_user, login_as, test_engine):
    _, student, submission, old_path = await _reviewed(
        client, db_session, make_user, login_as, "ret-replace", status=HomeworkStatusEnum.revision_requested, reviewed_days_ago=1
    )
    login_as(student)

    again = (await _submit(client, submission.lesson_id, "photo2.png", PNG)).json()

    assert not old_path.exists()
    assert again["file_original_name"] == "photo2.png" and again["file_deleted"] is False


async def test_only_one_sweep_runs_at_a_time(monkeypatch, test_engine):
    """Two uvicorn workers each run the loop; the advisory lock lets one in."""
    if test_engine.dialect.name != "postgresql":
        pytest.skip("advisory locks are Postgres")
    from sqlalchemy import text

    monkeypatch.setattr(retention, "engine", test_engine)
    monkeypatch.setattr(retention, "async_session_factory", async_sessionmaker(test_engine, expire_on_commit=False))
    async with test_engine.connect() as holder:
        holder = await holder.execution_options(isolation_level="AUTOCOMMIT")
        await holder.execute(text("SELECT pg_advisory_lock(:k)"), {"k": retention._ADVISORY_LOCK_KEY})
        try:
            assert await retention.sweep_once() == 0
        finally:
            await holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": retention._ADVISORY_LOCK_KEY})
    assert await retention.sweep_once() == 0  # nothing to do, but it ran
