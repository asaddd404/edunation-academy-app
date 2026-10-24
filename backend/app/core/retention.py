"""Retention policy for homework attachments.

Once a homework is reviewed -- accepted, or sent back for rework -- its
attached file is kept for `homework_file_retention_days` and then deleted
from disk. The row keeps everything else (answer text, grade, status,
feedback, the file's original name); file_path is cleared and
file_deleted_at records when, so the screens say the file expired rather
than offering a download that fails.

Runs inside the API process once every `homework_retention_interval_hours`
(see `run_retention_loop`, started from main.py's lifespan), and by hand or
from cron:

    docker compose ... exec backend python -m app.core.retention

Production runs two uvicorn workers, each with its own loop; a Postgres
advisory lock lets only one sweep at a time, and the sweep is idempotent
anyway (a row is only touched while it still has a file).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.storage import delete_upload
from app.database import async_session_factory, engine
from app.models.homework import HomeworkStatusEnum, HomeworkSubmission

logger = logging.getLogger(__name__)

# Arbitrary, fixed: the key of the advisory lock that serialises sweeps.
_ADVISORY_LOCK_KEY = 0x48574B52  # "HWKR"
_BATCH = 200
# First sweep shortly after start-up, not at it: a deploy restarts both
# workers at once and their start-up should not compete with a disk sweep.
_FIRST_RUN_DELAY_SECONDS = 300


def file_expires_at(submission: HomeworkSubmission) -> datetime | None:
    """When a reviewed homework's file will be deleted (None if it won't be)."""
    if (
        submission.file_path is None
        or submission.status == HomeworkStatusEnum.submitted
        or submission.reviewed_at is None
    ):
        return None
    return submission.reviewed_at + timedelta(days=settings.homework_file_retention_days)


async def purge_expired_homework_files(db: AsyncSession, now: datetime | None = None) -> int:
    """Deletes the files of homework reviewed more than the retention period
    ago. Returns how many were removed. Commits per batch."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.homework_file_retention_days)
    removed = 0
    while True:
        batch = (
            await db.scalars(
                select(HomeworkSubmission)
                .where(
                    HomeworkSubmission.file_path.is_not(None),
                    HomeworkSubmission.status != HomeworkStatusEnum.submitted,
                    HomeworkSubmission.reviewed_at < cutoff,
                )
                .order_by(HomeworkSubmission.reviewed_at)
                .limit(_BATCH)
                .with_for_update(skip_locked=True)
            )
        ).all()
        if not batch:
            return removed
        for submission in batch:
            # Missing on disk already (restored backup, manual cleanup) is
            # fine: the row is brought in line either way.
            delete_upload(submission.file_path)
            submission.file_path = None
            submission.file_deleted_at = now
        await db.commit()
        removed += len(batch)


async def sweep_once() -> int:
    """One sweep under the cross-worker lock; 0 if another worker holds it.

    The lock is session-level, so it is held on a dedicated connection for
    the whole sweep -- the ORM session hands its connection back to the pool
    at every commit, and an unlock sent over a different connection would
    leave the lock held for good. Autocommit, so that connection is never
    "idle in transaction" and killed by the server's timeout mid-sweep.
    """
    if engine.dialect.name != "postgresql":
        async with async_session_factory() as db:
            return await purge_expired_homework_files(db)

    async with engine.connect() as lock_conn:
        lock_conn = await lock_conn.execution_options(isolation_level="AUTOCOMMIT")
        if not await lock_conn.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY}):
            return 0
        try:
            async with async_session_factory() as db:
                removed = await purge_expired_homework_files(db)
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY})
    if removed:
        logger.info("Homework retention: removed %d expired attachment(s)", removed)
    return removed


async def run_retention_loop() -> None:
    """The in-process schedule: once shortly after start, then every interval.
    A failed sweep is logged and retried on the next tick, never fatal."""
    interval = settings.homework_retention_interval_hours * 3600
    await asyncio.sleep(_FIRST_RUN_DELAY_SECONDS)
    while True:
        try:
            await sweep_once()
        except Exception:  # noqa: BLE001 -- a background job must outlive its failures
            logger.exception("Homework retention sweep failed")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Удалено файлов: {asyncio.run(sweep_once())}")
