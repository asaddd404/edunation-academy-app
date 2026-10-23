"""The background transcode must not hold a database transaction while
ffmpeg runs.

Production Postgres ends any connection idle in a transaction after
db_idle_tx_timeout_ms (30 s); a real transcode takes minutes. With the
session held across it, the closing commit hit a dead connection and every
uploaded video stayed "processing" forever. Reproduced here with a one-second
timeout and a transcode that outlasts it.
"""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1 import teacher_content
from app.core.video import VideoProcessingError
from app.models import Category, Lesson, Section
from app.models.lesson import VideoStatusEnum
from tests.conftest import _TEST_DATABASE_URL

IDLE_TX_TIMEOUT_MS = 1000


@pytest.fixture
async def strict_sessions(test_engine, monkeypatch):
    if not _TEST_DATABASE_URL.startswith("postgresql"):
        pytest.skip("idle-in-transaction timeout is a Postgres behaviour")
    engine = create_async_engine(
        _TEST_DATABASE_URL,
        connect_args={"server_settings": {"idle_in_transaction_session_timeout": str(IDLE_TX_TIMEOUT_MS)}},
    )
    monkeypatch.setattr(teacher_content, "async_session_factory", async_sessionmaker(engine, expire_on_commit=False))
    yield
    await engine.dispose()


@pytest.fixture
async def lesson(db_session):
    category = Category(name="Физика", slug="fizika-video-test")
    db_session.add(category)
    await db_session.flush()
    section = Section(category_id=category.id, title="Раздел")
    db_session.add(section)
    await db_session.flush()
    row = Lesson(section_id=section.id, title="Урок", video_status=VideoStatusEnum.processing)
    db_session.add(row)
    await db_session.commit()
    return row


async def _status(db_session, lesson_id):
    db_session.expire_all()
    return await db_session.get(Lesson, lesson_id)


async def test_a_transcode_longer_than_the_idle_timeout_is_recorded(strict_sessions, lesson, db_session, tmp_path, monkeypatch):
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"video")

    async def slow_transcode(lesson_id, raw_path):
        await asyncio.sleep(IDLE_TX_TIMEOUT_MS / 1000 * 1.5)
        return 180

    monkeypatch.setattr(teacher_content, "transcode_to_hls", slow_transcode)
    await teacher_content._transcode_and_record(lesson.id, raw)

    stored = await _status(db_session, lesson.id)
    assert stored.video_status == VideoStatusEnum.ready
    assert stored.video_duration_seconds == 180
    assert not raw.exists()


async def test_a_failed_slow_transcode_is_recorded_as_failed(strict_sessions, lesson, db_session, tmp_path, monkeypatch):
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"video")

    async def slow_failure(lesson_id, raw_path):
        await asyncio.sleep(IDLE_TX_TIMEOUT_MS / 1000 * 1.5)
        raise VideoProcessingError("Неподдерживаемый кодек")

    monkeypatch.setattr(teacher_content, "transcode_to_hls", slow_failure)
    await teacher_content._transcode_and_record(lesson.id, raw)

    stored = await _status(db_session, lesson.id)
    assert stored.video_status == VideoStatusEnum.failed
    assert stored.video_error == "Неподдерживаемый кодек"
    assert not raw.exists()
