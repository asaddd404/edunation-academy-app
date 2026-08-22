"""Redis-backed request throttling.

Two rules shape everything here.

*Password guessing is an account problem, not an address problem.* The users
are schoolchildren and teachers: a whole computer lab shares one external IP,
so "5 attempts per minute per IP" locks the entire class out at the start of
a lesson. The strict limit is therefore keyed on the normalized phone number
being logged into; the IP limit exists only to slow down someone spraying one
password across many accounts, and is set far above what a real classroom
produces.

*A limiter that fails closed takes the site down with Redis.* If Redis is
unreachable the request is allowed through and the failure is logged -- the
alternative is that a cache outage becomes a total outage.
"""

import logging
import time

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.config import settings
from app.core.client_ip import client_ip
from app.redis_client import redis_client

logger = logging.getLogger(__name__)


class RateLimit:
    """A fixed window: at most `limit` hits per `window_seconds` per key."""

    def __init__(self, name: str, limit: int, window_seconds: int) -> None:
        self.name = name
        self.limit = limit
        self.window_seconds = window_seconds

    def _redis_key(self, subject: str) -> str:
        bucket = int(time.time()) // self.window_seconds
        return f"ratelimit:{self.name}:{subject}:{bucket}"

    async def hit(self, subject: str) -> tuple[bool, int]:
        """Records one use. Returns (allowed, seconds_until_reset)."""
        if not settings.rate_limit_enabled:
            return True, 0

        key = self._redis_key(subject)
        try:
            pipeline = redis_client.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, self.window_seconds)
            count, _ = await pipeline.execute()
        except RedisError:
            # Fail open, loudly: a Redis outage must not lock everyone out of
            # logging in, but it does mean the limit is not being enforced.
            logger.warning("Rate limit %s not enforced: Redis unavailable", self.name, exc_info=True)
            return True, 0

        if int(count) > self.limit:
            retry_after = self.window_seconds - (int(time.time()) % self.window_seconds)
            return False, max(1, retry_after)
        return True, 0

    async def enforce(self, subject: str) -> None:
        allowed, retry_after = await self.hit(subject)
        if not allowed:
            logger.warning("Rate limit %s exceeded for %r", self.name, subject)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Слишком много запросов. Попробуйте позже.",
                headers={"Retry-After": str(retry_after)},
            )

    async def reset(self, subject: str) -> None:
        """Clears the current window -- called after a *successful* login so a
        few mistyped passwords don't count against the next real session."""
        try:
            await redis_client.delete(self._redis_key(subject))
        except RedisError:
            logger.warning("Could not reset rate limit %s", self.name, exc_info=True)


# Password guessing against one account.
LOGIN_BY_ACCOUNT = RateLimit("login_account", limit=5, window_seconds=15 * 60)
# Account spraying from one address. Deliberately loose: a 30-seat computer
# lab logging in at the bell must pass, so this only catches automated volume.
LOGIN_BY_IP = RateLimit("login_ip", limit=60, window_seconds=60)
REGISTER_BY_IP = RateLimit("register_ip", limit=10, window_seconds=60 * 60)
CHANGE_PASSWORD_BY_USER = RateLimit("change_password_user", limit=10, window_seconds=60 * 60)
REFRESH_BY_IP = RateLimit("refresh_ip", limit=120, window_seconds=60)
# The client pings once a minute; 45s leaves room for clock drift and a tab
# waking up, while still capping how much activity time can be fabricated.
ACTIVITY_PING_BY_USER = RateLimit("activity_ping_user", limit=1, window_seconds=45)
# PDF parsing is the heaviest thing a teacher can ask for.
ENT_PDF_IMPORT_BY_USER = RateLimit("ent_pdf_import_user", limit=10, window_seconds=60 * 60)
BULK_DELETE_BY_USER = RateLimit("ent_bulk_delete_user", limit=20, window_seconds=60 * 60)
BULK_CREATE_BY_USER = RateLimit("ent_bulk_create_user", limit=60, window_seconds=60 * 60)
UPLOAD_BY_USER = RateLimit("upload_user", limit=120, window_seconds=60 * 60)


def request_ip(request: Request) -> str:
    return client_ip(request)
