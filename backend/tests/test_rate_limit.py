"""The limiter itself, independent of any endpoint.

Two properties matter beyond "it counts": the window has to be keyed so that
one account's attempts never consume another's quota (a whole classroom
shares one address), and a Redis outage has to fail *open* -- a cache that is
down must not lock every user out of the site.
"""

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.rate_limit import RateLimit


async def test_requests_within_the_limit_are_allowed():
    limit = RateLimit("unit_allow", limit=3, window_seconds=60)
    for _ in range(3):
        allowed, _ = await limit.hit("subject")
        assert allowed is True


async def test_the_request_past_the_limit_is_refused():
    limit = RateLimit("unit_refuse", limit=3, window_seconds=60)
    for _ in range(3):
        await limit.hit("subject")
    allowed, retry_after = await limit.hit("subject")
    assert allowed is False
    assert retry_after >= 1


async def test_enforce_raises_429_with_retry_after():
    limit = RateLimit("unit_enforce", limit=1, window_seconds=60)
    await limit.enforce("subject")
    with pytest.raises(HTTPException) as excinfo:
        await limit.enforce("subject")
    assert excinfo.value.status_code == 429
    assert "Retry-After" in excinfo.value.headers


async def test_subjects_do_not_share_a_quota():
    """The property that keeps a school computer lab working: one pupil
    exhausting their attempts must not spend anybody else's."""
    limit = RateLimit("unit_isolation", limit=2, window_seconds=60)
    await limit.hit("account-a")
    await limit.hit("account-a")
    exhausted, _ = await limit.hit("account-a")
    assert exhausted is False

    fresh, _ = await limit.hit("account-b")
    assert fresh is True


async def test_reset_clears_the_window():
    """A successful sign-in after two typos must not leave the account three
    attempts short for the next quarter of an hour."""
    limit = RateLimit("unit_reset", limit=2, window_seconds=60)
    await limit.hit("subject")
    await limit.hit("subject")
    await limit.reset("subject")
    allowed, _ = await limit.hit("subject")
    assert allowed is True


async def test_redis_outage_fails_open(monkeypatch):
    """Deliberate: a limiter that fails closed turns a Redis restart into a
    total outage where nobody can log in. The trade-off is that limits are
    not enforced while Redis is down, which is why `hit` logs a warning."""

    class BrokenRedis:
        def pipeline(self):
            raise RedisConnectionError("redis is down")

    monkeypatch.setattr("app.core.rate_limit.redis_client", BrokenRedis())
    limit = RateLimit("unit_outage", limit=1, window_seconds=60)
    for _ in range(5):
        allowed, _ = await limit.hit("subject")
        assert allowed is True


async def test_limiter_can_be_switched_off_for_local_work(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    limit = RateLimit("unit_disabled", limit=1, window_seconds=60)
    for _ in range(5):
        allowed, _ = await limit.hit("subject")
        assert allowed is True
