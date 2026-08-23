"""A small read-through cache in Redis, for aggregates on the request path.

Used where the cost of an answer is set by how much data exists rather than
by how much the caller asked for. The ЕНТ leaderboard is the example: it
sums every submitted attempt in the window, so one keypress recomputes the
whole table, and a student holding refresh is a denial-of-service tool the
app handed out itself. A 60-second cache turns any amount of that traffic
into one query a minute.

Fails open in both directions. A Redis that is down, slow or full must make
the page slower, never broken -- so a cache miss and a cache error are the
same thing here, and a write that cannot be stored is dropped silently.
"""

import json
import logging
from typing import Any, Awaitable, Callable

from redis.exceptions import RedisError

from app.redis_client import redis_client

logger = logging.getLogger(__name__)


async def cached_json(key: str, ttl_seconds: int, factory: Callable[[], Awaitable[Any]]) -> Any:
    """Returns the cached value for `key`, or computes, stores and returns it.

    The value must be JSON-serializable; callers pass plain dicts and lists
    rather than Pydantic models so that what is stored stays readable with
    `redis-cli GET` during an incident.
    """
    try:
        hit = await redis_client.get(key)
        if hit is not None:
            return json.loads(hit)
    except (RedisError, ValueError):
        # ValueError covers a corrupted entry: recompute rather than 500 on
        # something a flushall would have fixed.
        logger.warning("Cache read failed for %s, recomputing", key, exc_info=True)

    value = await factory()

    try:
        await redis_client.set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except RedisError:
        logger.warning("Cache write failed for %s", key, exc_info=True)

    return value
