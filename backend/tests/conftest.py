"""Settings the app requires at import time.

`app.config.Settings` is constructed at module import, so anything that
reaches `app.database` (the schemas do, via the ORM enums) needs these
present before the import happens. Most tests in this suite never open a
connection -- these values only have to be well-formed for import to
succeed.

The fixtures below (`test_engine`/`db_session`/`client`/`login_as`) are the
exception: they talk to a *real* Postgres, reusing whatever `DATABASE_URL`
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
"""
import os
from urllib.parse import urlsplit, urlunsplit

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")

import itertools

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.deps import get_current_user
from app.main import app
from app.models.user import RoleEnum, User


def _swap_db_name(url: str, new_name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{new_name}", parts.query, parts.fragment))


_TEST_DB_NAME = urlsplit(settings.database_url).path.lstrip("/") + "_test"
_TEST_DATABASE_URL = _swap_db_name(settings.database_url, _TEST_DB_NAME)
_ADMIN_DATABASE_URL = _swap_db_name(settings.database_url, "postgres")


async def _ensure_test_database() -> None:
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
    as two different teachers without faking JWTs -- the real
    `require_role` check still runs against whatever this returns."""

    def _login(user: User) -> None:
        app.dependency_overrides[get_current_user] = lambda: user

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


_phone_counter = itertools.count(1)


@pytest_asyncio.fixture
async def make_user(db_session):
    """Inserts a `User` row directly (no real password needed -- these
    tests never exercise login)."""

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
        await db_session.flush()
        return user

    return _make
