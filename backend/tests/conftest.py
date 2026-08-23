"""Settings the app requires at import time.

`app.config.Settings` is constructed at module import, so anything that
reaches `app.database` (the schemas do, via the ORM enums) needs these
present before the import happens. Most tests in this suite never open a
connection -- these values only have to be well-formed for import to
succeed.

The fixtures below (`test_engine`/`db_session`/`client`/`login_as`) are the
exception: they talk to a real database, reusing whatever `DATABASE_URL`
already points at (the same one the Docker-compose `backend` service uses)
but against a sibling database named `<original>_test` instead of the dev
one, so nothing here ever touches real/seeded data. That database is
created automatically on first use (via a maintenance connection to the
`postgres` database) -- the only precondition is that the Postgres server
itself is reachable and the credentials in `DATABASE_URL` can create
databases, which is true of the default docker-compose superuser. Run these
with `docker compose exec backend pytest` so `DATABASE_URL`'s `postgres`
hostname resolves; running straight on the host only works if you've mapped
that hostname yourself.

Without Docker, point `DATABASE_URL` at SQLite instead:

    DATABASE_URL=sqlite+aiosqlite:///./test.db pytest

That path exists so the authorization and session tests can be run at all on
a machine with no container runtime -- a check nobody can execute is worth
less than one executed against an imperfect database. It is not equivalent:
SQLite does not enforce the enum types or the partial indexes, so Postgres
stays the reference for anything that depends on them, and for CI.
"""
import os
import sys
from urllib.parse import urlsplit, urlunsplit

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")

import itertools

import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.deps import get_current_user
from app.main import app
from app.models.user import RoleEnum, User
from tests.fake_redis import FakeRedis


def _swap_db_name(url: str, new_name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{new_name}", parts.query, parts.fragment))


_IS_SQLITE = settings.database_url.startswith("sqlite")

if _IS_SQLITE:
    # Escape hatch, opt-in by pointing DATABASE_URL at sqlite+aiosqlite. It
    # exists so the security tests can be run on a machine with no Docker --
    # an untested authorization check is worth less than one verified against
    # an imperfect database.
    #
    # Postgres remains the reference: it is what production runs, what CI
    # should run, and the only place the partial indexes and real enum types
    # are exercised. Anything that depends on those has to be checked there.
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles

    @compiles(JSONB, "sqlite")
    def _jsonb_as_json(type_, compiler, **kw):  # noqa: ANN001 -- SQLAlchemy hook signature
        """One column (EntSimulationQuestion.answer_data) is JSONB, which
        SQLite has no compiler for, so create_all would fail before any test
        ran. JSON is close enough for storing and reading a dict back."""
        return "JSON"

    _TEST_DATABASE_URL = settings.database_url
else:
    _TEST_DB_NAME = urlsplit(settings.database_url).path.lstrip("/") + "_test"
    _TEST_DATABASE_URL = _swap_db_name(settings.database_url, _TEST_DB_NAME)
    _ADMIN_DATABASE_URL = _swap_db_name(settings.database_url, "postgres")


async def _ensure_test_database() -> None:
    if _IS_SQLITE:
        return
    # CREATE DATABASE can't run inside a transaction block.
    admin_engine = create_async_engine(_ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": _TEST_DB_NAME}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{_TEST_DB_NAME}"'))
    finally:
        await admin_engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    await _ensure_test_database()
    engine = create_async_engine(_TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    """A real session against the test database, for the test itself to set
    up fixture rows with. The app under test (see `client` below) opens its
    *own* session per request, exactly like production -- so this one
    commits for real rather than trying to share a connection with it,
    which is what a request needs in order to see it. Cleaned up by
    truncating every table after the test, not by rolling back a
    transaction."""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def client(test_engine, db_session):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def _get_db_override():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db_override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def login_as():
    """Swaps which user `get_current_user` resolves to, so a test can act
    as two different teachers without faking JWTs -- the real `require_role`
    check still runs against whatever this returns.

    Only the *id* is captured, and the User is re-loaded from the request's
    own session. Returning the test's instance directly would hand handlers
    an object owned by a different session, and any handler that writes to
    the current user (`/me/avatar`, `/me`) then fails inside `db.refresh` with
    "not persistent within this Session" -- an error the endpoint cannot
    produce in production, where get_current_user loads from that same
    session. A fixture that only works for read-only handlers hides exactly
    the write paths worth testing.
    """

    def _login(user: User) -> None:
        user_id = user.id

        async def _override(db: AsyncSession = Depends(get_db)) -> User:
            return await db.get(User, user_id)

        app.dependency_overrides[get_current_user] = _override

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


_phone_counter = itertools.count(1)


@pytest_asyncio.fixture
async def make_user(db_session):
    """Inserts a `User` row directly (no real password needed -- these
    tests never exercise login).

    Committed, not flushed: the app under test opens its own session per
    request, and a flushed-but-uncommitted row is invisible to it. That only
    stopped mattering while `login_as` handed the instance straight to the
    handler; now that it re-loads by id, like production does, the row has to
    actually be there."""

    async def _make(role: RoleEnum = RoleEnum.teacher) -> User:
        n = next(_phone_counter)
        user = User(
            phone=f"+7700{n:07d}",
            password_hash="unused-in-tests",
            first_name="Test",
            last_name=f"User{n}",
            role=role,
        )
        db_session.add(user)
        await db_session.commit()
        return user

    return _make


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Every test gets a clean in-memory Redis.

    Autouse rather than opt-in because `RateLimit.hit` fails *open* when
    Redis is unreachable: without this a rate-limit test would pass while the
    limit was never enforced at all, which is the one outcome a security test
    must never produce. A fresh instance per test also stops one test's login
    attempts from tripping the limiter in the next.
    """
    fake = FakeRedis()

    # Patched by discovery rather than by a hand-written list. Modules bind
    # the client with `from app.redis_client import redis_client`, so each
    # one holds its own reference and patching the source module alone
    # changes nothing for them. A list would silently go stale the next time
    # a module imports it -- and the test would then quietly talk to a real
    # Redis, or hang waiting for one that is not there.
    monkeypatch.setattr("app.redis_client.redis_client", fake)
    for name, module in list(sys.modules.items()):
        if name.startswith("app.") and getattr(module, "redis_client", None) is not None:
            monkeypatch.setattr(f"{name}.redis_client", fake)

    return fake


@pytest_asyncio.fixture
async def make_password_user(db_session):
    """A user with a real, known password -- for the login tests, which have
    to exercise the actual hash/verify path rather than override it."""
    from app.security import hash_password

    async def _make(password: str, role: RoleEnum = RoleEnum.student, is_active: bool = True) -> User:
        n = next(_phone_counter)
        user = User(
            phone=f"+7701{n:07d}",
            password_hash=hash_password(password),
            first_name="Test",
            last_name=f"User{n}",
            role=role,
            is_active=is_active,
        )
        db_session.add(user)
        await db_session.commit()
        return user

    return _make
