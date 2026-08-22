"""An in-memory stand-in for the Redis client used by the tests.

The rate limiters and the refresh-token store both talk to Redis, and both
are things this suite has to assert on. Pointing them at a real server would
make the security tests depend on a running container and on that container's
state not leaking between tests; failing to point them anywhere at all is
worse, because `RateLimit.hit` deliberately fails *open* when Redis is down,
so every limit test would pass without the limit ever being enforced.

Only the handful of commands the app actually issues are implemented.
"""

from __future__ import annotations

import time


class _Pipeline:
    def __init__(self, store: "FakeRedis") -> None:
        self._store = store
        self._ops: list = []

    def incr(self, key: str):
        self._ops.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int):
        self._ops.append(("expire", key, seconds))
        return self

    async def execute(self) -> list:
        results = []
        for op in self._ops:
            if op[0] == "incr":
                results.append(await self._store.incr(op[1]))
            elif op[0] == "expire":
                results.append(await self._store.expire(op[1], op[2]))
        self._ops.clear()
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.expiry: dict[str, float] = {}

    # -- expiry ------------------------------------------------------------
    def _expire_if_due(self, key: str) -> None:
        due = self.expiry.get(key)
        if due is not None and due <= time.time():
            self.values.pop(key, None)
            self.sets.pop(key, None)
            self.expiry.pop(key, None)

    # -- strings -----------------------------------------------------------
    async def get(self, key: str):
        self._expire_if_due(key)
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.values[key] = str(value)
        if ex is not None:
            self.expiry[key] = time.time() + ex
        return True

    async def incr(self, key: str) -> int:
        self._expire_if_due(key)
        new = int(self.values.get(key, 0)) + 1
        self.values[key] = str(new)
        return new

    async def expire(self, key: str, seconds: int) -> bool:
        if key in self.values or key in self.sets:
            self.expiry[key] = time.time() + seconds
            return True
        return False

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += int(self.values.pop(key, None) is not None)
            removed += int(self.sets.pop(key, None) is not None)
            self.expiry.pop(key, None)
        return removed

    # -- sets --------------------------------------------------------------
    async def sadd(self, key: str, *members: str) -> int:
        self._expire_if_due(key)
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        bucket.update(str(m) for m in members)
        return len(bucket) - before

    async def srem(self, key: str, *members: str) -> int:
        bucket = self.sets.get(key)
        if not bucket:
            return 0
        before = len(bucket)
        bucket.difference_update(str(m) for m in members)
        return before - len(bucket)

    async def smembers(self, key: str) -> set[str]:
        self._expire_if_due(key)
        return set(self.sets.get(key, set()))

    def pipeline(self) -> _Pipeline:
        return _Pipeline(self)
