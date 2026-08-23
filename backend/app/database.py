from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _server_settings() -> dict[str, str]:
    """Per-connection Postgres limits, applied to every session the app opens.

    These are the ceilings that turn a slow query into a failed request
    instead of a failed service. Without `statement_timeout` a single bad
    plan -- a missing index, a lock, a table that grew -- runs until someone
    notices, holding a pooled connection the whole time; a handful of those
    exhausts the pool and every other request then blocks waiting for one,
    which is a total outage caused by one slow query.

    15 seconds is far above any legitimate query here (the slowest, the ЕНТ
    leaderboard aggregate, is milliseconds on the current data) and far below
    the point where users have given up anyway.

    `idle_in_transaction_session_timeout` covers the other direction: a
    transaction left open by a crashed or hung handler holds its row locks
    indefinitely, and every writer touching those rows queues behind it.
    """
    return {
        "statement_timeout": str(settings.db_statement_timeout_ms),
        "idle_in_transaction_session_timeout": str(settings.db_idle_tx_timeout_ms),
    }


_IS_POSTGRES = settings.database_url.startswith("postgresql")

# Pool sizing is a budget, not a preference: pool_size + max_overflow, times
# the number of uvicorn workers, must stay under the server's
# max_connections (100 by default). Two workers x (5 + 5) = 20 leaves ample
# headroom for migrations, psql and a backup running at the same time.
#
# `pool_timeout` is deliberately short. The default is 30 seconds, which
# means a request that cannot get a connection sits and holds a worker for
# half a minute before failing -- during a pile-up that turns a small
# shortage into an unresponsive site. Five seconds fails fast, which sheds
# load instead of absorbing it.
#
# All of it is Postgres-only. SQLite (the no-Docker test path in
# tests/conftest.py) runs on NullPool, which has no pool to size and rejects
# these arguments outright, and has no server-side statement timeout either.
_POSTGRES_KWARGS = {
    "pool_size": settings.db_pool_size,
    "max_overflow": settings.db_max_overflow,
    "pool_timeout": settings.db_pool_timeout_seconds,
    # Connections are recycled well inside any idle-connection reaping done
    # by Postgres or an intermediary, so a long-idle worker does not wake up
    # holding a dead socket.
    "pool_recycle": 1800,
    "connect_args": {"server_settings": _server_settings()},
}

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    **(_POSTGRES_KWARGS if _IS_POSTGRES else {}),
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
