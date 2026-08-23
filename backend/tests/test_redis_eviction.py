"""What survives when Redis evicts keys.

Production runs Redis with `maxmemory 256mb` and `allkeys-lru`, chosen so a
runaway keyspace sheds cold keys instead of growing until the kernel kills
Postgres. The price is that *any* key can vanish at any moment, so every
structure kept there has to be examined for what its absence means.

Two possible answers, and only one is acceptable:

  fail-safe   the key's absence denies access  (a session ends)
  fail-open   the key's absence grants access  (a revoked token works again)

These tests pin down which is which by deleting keys behind the code's back
-- exactly what eviction does.
"""

from app.security import (
    consume_refresh_token,
    issue_refresh_token,
    revoke_all_refresh_tokens,
    revoke_refresh_token,
)


async def test_sessions_are_an_allowlist_so_eviction_logs_out(fake_redis):
    """The token store answers "is this token live?" by presence. Evicting an
    entry therefore ends a session -- annoying, never dangerous.

    This is the property that makes allkeys-lru tolerable at all. Had the
    design been a blocklist of revoked tokens, the same eviction would have
    brought a revoked token back to life.
    """
    token = await issue_refresh_token(user_id=1)
    assert await consume_refresh_token(token) == 1

    token = await issue_refresh_token(user_id=1)
    await fake_redis.delete(f"refresh:{token}")  # the eviction

    assert await consume_refresh_token(token) is None


async def test_revoke_all_still_works_when_the_index_was_evicted(fake_redis):
    """The one fail-open path, and the reason for the SCAN fallback.

    `refresh_sessions:{user}` only indexes the token keys. Evict it alone and
    the tokens are still there with nothing pointing at them, so a
    password change would report success and revoke nothing -- while the
    person pressing it is usually trying to throw an intruder out.
    """
    first = await issue_refresh_token(user_id=7)
    second = await issue_refresh_token(user_id=7)

    await fake_redis.delete("refresh_sessions:7")  # the eviction
    assert f"refresh:{first}" in fake_redis.values, "precondition: the tokens outlived the index"

    await revoke_all_refresh_tokens(7)

    assert await consume_refresh_token(first) is None
    assert await consume_refresh_token(second) is None


async def test_revoke_all_does_not_touch_other_users(fake_redis):
    """The fallback scans the whole keyspace, so it has to match on the
    stored owner rather than on the key pattern alone."""
    mine = await issue_refresh_token(user_id=7)
    theirs = await issue_refresh_token(user_id=8)
    await fake_redis.delete("refresh_sessions:7")

    await revoke_all_refresh_tokens(7)

    assert await consume_refresh_token(mine) is None
    assert await consume_refresh_token(theirs) == 8


async def test_single_revoke_survives_an_evicted_index(fake_redis):
    """Logging out one device must not depend on the index either."""
    token = await issue_refresh_token(user_id=3)
    await fake_redis.delete("refresh_sessions:3")

    await revoke_refresh_token(token)

    assert await consume_refresh_token(token) is None


async def test_rate_limit_counters_are_the_accepted_loss(fake_redis):
    """Named rather than fixed, so the trade-off is on the record.

    A counter evicted mid-window resets, handing an attacker a fresh set of
    attempts. It is accepted because the alternative -- `noeviction` -- makes
    a full Redis stop logins outright, and because the counters are the
    hottest keys in the instance, so LRU reaches them last.
    """
    from app.core.rate_limit import RateLimit

    limit = RateLimit("unit_eviction", limit=2, window_seconds=60)
    await limit.hit("account")
    await limit.hit("account")
    assert (await limit.hit("account"))[0] is False

    for key in [k for k in list(fake_redis.values) if k.startswith("ratelimit:")]:
        await fake_redis.delete(key)

    assert (await limit.hit("account"))[0] is True, (
        "documented consequence: evicting a counter restores the attacker's budget"
    )
