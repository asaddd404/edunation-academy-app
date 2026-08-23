"""Resource-exhaustion defences.

The failure this file is about does not look like a crash. The service stays
up, answers nothing in time, and recovers only when the load stops -- so
there is no exception to assert on and no error to catch. What can be
asserted is the shape of the defences: that heavy work is bounded, that
nothing waits forever, and that the expensive aggregate is computed once
rather than per request.
"""

import asyncio
import time

import pytest
from fastapi import HTTPException
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.config import settings
from app.core.cache import cached_json
from app.core.concurrency import BoundedWorkPool, ConcurrencyGate
from app.models.user import RoleEnum


# --- bounded pools ----------------------------------------------------------

async def test_pool_runs_work_off_the_event_loop():
    """A blocking call must not stall the loop -- that is the whole reason
    the pool exists rather than a plain function call."""
    pool = BoundedWorkPool("unit-offloop", max_concurrent=1, queue_wait_seconds=1.0)

    loop_ticked = False

    async def ticker():
        nonlocal loop_ticked
        await asyncio.sleep(0.05)
        loop_ticked = True

    task = asyncio.create_task(ticker())
    result = await pool.run(time.sleep, 0.2, timeout=5)
    await task

    assert result is None
    assert loop_ticked, "the event loop was blocked while the pool ran its work"


async def test_pool_serializes_work_beyond_its_width():
    """One slot means one CPU-bound job at a time. Measured cost of a real
    PDF import is ~10 s of CPU; two at once on a one-vCPU box is what takes
    the site down, so the limit is the defence."""
    pool = BoundedWorkPool("unit-serial", max_concurrent=1, queue_wait_seconds=5.0)

    started = time.perf_counter()
    await asyncio.gather(*(pool.run(time.sleep, 0.15, timeout=5) for _ in range(3)))
    elapsed = time.perf_counter() - started

    # Serialized: ~0.45 s. Parallel would be ~0.15 s.
    assert elapsed >= 0.4, f"three 0.15s jobs finished in {elapsed:.2f}s -- they ran in parallel"


async def test_pool_sheds_load_instead_of_queueing_forever():
    """The property that keeps the rest of the site answering: a caller who
    cannot get a slot is turned away quickly with 429, rather than holding a
    worker while the queue behind it grows."""
    pool = BoundedWorkPool("unit-shed", max_concurrent=1, queue_wait_seconds=0.05)

    occupied = asyncio.create_task(pool.run(time.sleep, 0.5, timeout=5))
    await asyncio.sleep(0.05)

    with pytest.raises(HTTPException) as excinfo:
        await pool.run(time.sleep, 0.01, timeout=5)

    assert excinfo.value.status_code == 429
    assert excinfo.value.headers["Retry-After"]
    await occupied


async def test_pool_releases_its_slot_after_a_timeout():
    """A timed-out job must not leak the slot, or one bad file permanently
    reduces capacity and the next import is refused forever."""
    pool = BoundedWorkPool("unit-timeout", max_concurrent=1, queue_wait_seconds=1.0)

    with pytest.raises(asyncio.TimeoutError):
        await pool.run(time.sleep, 0.5, timeout=0.05)

    # The slot is free again even though the thread is still finishing.
    await pool.run(lambda: "ok", timeout=5)


async def test_gate_limits_concurrency_without_refusing():
    """Transcoding is minutes long and already accepted, so it waits rather
    than fails -- the opposite trade-off to the import pool, on purpose."""
    gate = ConcurrencyGate("unit-gate", max_concurrent=1)
    active = 0
    peak = 0

    async def work():
        nonlocal active, peak
        async with gate:
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.05)
            active -= 1

    await asyncio.gather(*(work() for _ in range(4)))
    assert peak == 1


# --- cache ------------------------------------------------------------------

async def test_expensive_work_runs_once_across_many_readers():
    """The leaderboard is identical for every viewer, so a hundred students
    refreshing must cost one aggregate, not a hundred."""
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return {"rows": [1, 2, 3]}

    for _ in range(10):
        assert await cached_json("unit:cache:key", 60, factory) == {"rows": [1, 2, 3]}

    assert calls == 1


async def test_cache_failure_degrades_to_recomputing(monkeypatch):
    """A Redis outage must make the page slower, never broken."""

    class BrokenRedis:
        async def get(self, key):
            raise RedisTimeoutError("redis is not answering")

        async def set(self, key, value, ex=None):
            raise RedisTimeoutError("redis is not answering")

    monkeypatch.setattr("app.core.cache.redis_client", BrokenRedis())

    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return {"ok": True}

    assert await cached_json("unit:cache:broken", 60, factory) == {"ok": True}
    assert await cached_json("unit:cache:broken", 60, factory) == {"ok": True}
    assert calls == 2, "a failing cache must fall through to the real work"


async def test_corrupted_cache_entry_is_recomputed(fake_redis):
    """Something wrote garbage under our key. Recompute; do not 500 on a
    problem a `FLUSHALL` would have fixed."""
    await fake_redis.set("unit:cache:corrupt", "{not json")

    async def factory():
        return {"ok": True}

    assert await cached_json("unit:cache:corrupt", 60, factory) == {"ok": True}


# --- configured ceilings ----------------------------------------------------

def test_connection_pool_fits_inside_postgres_max_connections():
    """The arithmetic that decides whether a traffic spike is slow or fatal:
    pool + overflow, times workers, must stay under max_connections (100 by
    default). Two workers is what docker-compose.prod.yml runs."""
    per_worker = settings.db_pool_size + settings.db_max_overflow
    assert per_worker * 2 < 100


def test_every_wait_has_a_ceiling():
    """An unbounded wait anywhere on the request path converts one slow
    dependency into a service-wide outage, which is the single most common
    way this class of failure happens."""
    assert 0 < settings.db_pool_timeout_seconds <= 10
    assert 0 < settings.db_statement_timeout_ms <= 30_000
    assert 0 < settings.db_idle_tx_timeout_ms <= 60_000
    assert 0 < settings.redis_socket_timeout_seconds <= 5


def test_database_connections_would_carry_the_timeouts():
    """The settings are worth nothing if they never reach Postgres, and the
    wiring is the kind of thing a refactor drops silently -- so assert on
    what actually gets passed to the driver.

    Checked through `_server_settings()` rather than by introspecting a live
    engine, so it holds on the SQLite test path too, where no Postgres
    connection is ever made."""
    from app.database import _server_settings

    configured = _server_settings()
    assert configured["statement_timeout"] == str(settings.db_statement_timeout_ms)
    assert configured["idle_in_transaction_session_timeout"] == str(settings.db_idle_tx_timeout_ms)


async def test_pdf_import_can_be_switched_off(client, db_session, make_user, login_as, monkeypatch):
    """The runbook's load-shedding step. A kill switch nobody has tested is
    not a mitigation, it is a paragraph."""
    from app.models.ent_subject import EntSubject

    teacher = await make_user(RoleEnum.teacher)
    subject = EntSubject(name="Математика", slug="math-killswitch", created_by_id=teacher.id)
    db_session.add(subject)
    await db_session.commit()

    monkeypatch.setattr(settings, "ent_pdf_import_enabled", False)
    login_as(teacher)

    response = await client.post(
        "/api/v1/teacher/ent/questions/import-pdf",
        data={"subject_id": str(subject.id)},
        files={"file": ("variants.pdf", b"%PDF-1.7\n", "application/pdf")},
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"]


async def test_a_student_cannot_hoard_unfinished_attempts(client, db_session, make_user, login_as):
    """Each start writes an attempt plus a row per drawn question, and
    nothing reaps them -- so without a ceiling the client decides how large
    the biggest table in the ЕНТ module gets."""
    from app.models.application import Application, ApplicationStatusEnum
    from app.models.category import Category
    from app.models.ent_simulation import EntSimulation, EntSimulationStatus

    student = await make_user(RoleEnum.student)
    category = Category(name="Курс", slug="course-hoard", is_active=True)
    db_session.add(category)
    await db_session.flush()
    db_session.add(
        Application(
            student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved
        )
    )
    for _ in range(5):
        db_session.add(
            EntSimulation(
                student_id=student.id, is_timed=False, status=EntSimulationStatus.in_progress
            )
        )
    await db_session.commit()

    login_as(student)
    response = await client.post(
        "/api/v1/ent/simulations",
        json={"subject_ids": [1], "questions_per_subject": 10, "is_timed": False},
    )

    assert response.status_code == 409


def test_postgres_engine_is_built_with_the_pool_budget():
    """The SQLite path must not silently drop the pool settings for the real
    one -- that is exactly the shape of bug this split could introduce."""
    from app.database import _POSTGRES_KWARGS

    assert _POSTGRES_KWARGS["pool_size"] == settings.db_pool_size
    assert _POSTGRES_KWARGS["max_overflow"] == settings.db_max_overflow
    assert _POSTGRES_KWARGS["pool_timeout"] == settings.db_pool_timeout_seconds
    assert "server_settings" in _POSTGRES_KWARGS["connect_args"]
