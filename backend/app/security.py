import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import jwt
from fastapi import Response
from pwdlib import PasswordHash

from app.config import settings
from app.redis_client import redis_client

password_hasher = PasswordHash.recommended()


def hash_password(plain: str) -> str:
    return password_hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return password_hasher.verify(plain, hashed)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A hash of a value nobody knows, built once on first use."""
    return password_hasher.hash(secrets.token_urlsafe(32))


def verify_password_dummy() -> None:
    """Burns the same argon2 work a real password check would.

    Without this, `/auth/login` answers in microseconds for a phone number
    that has no account and in ~100ms for one that does -- which turns the
    single shared error message into a working account-enumeration oracle
    for anyone with a stopwatch.
    """
    password_hasher.verify(secrets.token_urlsafe(16), _dummy_hash())


def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_ttl_minutes),
        "jti": secrets.token_hex(8),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError for anything that is not an access token.

    The video ticket is signed with the same secret, so a valid signature
    alone does not make a token a session: without the shape check a ticket
    presented as a bearer token got as far as `payload["sub"]` and answered
    500. Tokens minted before the `type` claim existed carry no `type`, and
    are accepted until they expire on their own (fifteen minutes)."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("type", "access") != "access" or "purpose" in payload or not str(payload.get("sub", "")).isdigit():
        raise jwt.InvalidTokenError("Not an access token")
    return payload


def _user_sessions_key(user_id: int | str) -> str:
    """Index of a user's live refresh tokens. Without it, `refresh:{token}`
    can only be revoked one token at a time -- there is no way to end every
    session at once when the password changes."""
    return f"refresh_sessions:{user_id}"


async def issue_refresh_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    ttl_seconds = settings.jwt_refresh_ttl_days * 24 * 60 * 60
    await redis_client.set(f"refresh:{token}", str(user_id), ex=ttl_seconds)
    await redis_client.sadd(_user_sessions_key(user_id), token)
    # Re-armed on every issue so the index outlives the tokens it points at.
    await redis_client.expire(_user_sessions_key(user_id), ttl_seconds)
    return token


# How long a just-rotated refresh token is remembered as "rotated" rather
# than "unknown". Two tabs refreshing at once both send the same cookie; the
# loser must not answer with a cookie-clearing 401, or it deletes the new
# cookie the winner was just given and both tabs are signed out. It still
# gets no session -- only the hint to retry with the cookie the browser now
# holds -- so a stolen, already-rotated token stays worthless.
REFRESH_ROTATION_GRACE_SECONDS = 60


async def consume_refresh_token(token: str) -> int | None:
    """Validates and deletes the refresh token (rotation). Returns user_id or None.

    GETDEL, not GET then DELETE: in between, a second request carrying the
    same token would also see it as valid, and one token would mint two
    sessions."""
    key = f"refresh:{token}"
    user_id = await redis_client.getdel(key)
    if user_id is None:
        return None
    await redis_client.srem(_user_sessions_key(user_id), token)
    await redis_client.set(f"refresh_rotated:{token}", str(user_id), ex=REFRESH_ROTATION_GRACE_SECONDS)
    return int(user_id)


async def was_recently_rotated(token: str) -> bool:
    return await redis_client.get(f"refresh_rotated:{token}") is not None


async def revoke_refresh_token(token: str) -> None:
    user_id = await redis_client.get(f"refresh:{token}")
    await redis_client.delete(f"refresh:{token}")
    if user_id is not None:
        await redis_client.srem(_user_sessions_key(user_id), token)


async def revoke_all_refresh_tokens(user_id: int) -> None:
    """Ends every session the user has, on every device.

    The index is a convenience, not the source of truth, and the fallback
    below is why. Redis runs with `maxmemory` and `allkeys-lru` so that a
    runaway keyspace cannot OOM the box out from under Postgres -- which
    means any key can be evicted, including this index.

    Everything else about eviction is fail-safe: the token keys are an
    allowlist, so losing one logs somebody out. This was the exception.
    Losing only the index left the token keys behind with nothing pointing
    at them, so "log out everywhere" would report success and revoke
    nothing -- and the person who most often presses it is someone changing
    their password to throw an intruder out.

    So when the index is missing but sessions might not be, the tokens are
    found the slow way. SCAN is O(keyspace) and this is the rare path
    (password change, admin reset), which is the right way round.
    """
    key = _user_sessions_key(user_id)
    tokens = set(await redis_client.smembers(key))

    if not tokens:
        tokens = await _scan_tokens_for_user(user_id)

    if tokens:
        await redis_client.delete(*(f"refresh:{token}" for token in tokens))
    await redis_client.delete(key)


async def _scan_tokens_for_user(user_id: int) -> set[str]:
    """Every live refresh token belonging to `user_id`, found by scanning.

    Deliberately not `KEYS`: that blocks the server for the length of the
    sweep, and blocking Redis blocks every request that touches it.
    """
    found: set[str] = set()
    async for key in redis_client.scan_iter(match="refresh:*", count=500):
        if await redis_client.get(key) == str(user_id):
            found.add(key.removeprefix("refresh:"))
    return found


# Scoped to the auth router's own path, so the browser attaches it only to
# /refresh and /logout and to nothing else the API serves. That scoping is
# most of the CSRF story: every other endpoint authenticates with a bearer
# header, which a cross-site page cannot set. Tied to the prefixes in
# app.api (`/api/v1`) and app.api.v1.auth (`/auth`).
REFRESH_COOKIE_NAME = "edunation_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, token: str) -> None:
    """Hands the refresh token to the browser as a cookie it cannot read.

    httpOnly is the whole point: script on the page -- injected or imported --
    can no longer read the token, so an XSS bug costs the attacker the current
    tab rather than a thirty-day session on every device.

    `secure` is gated on the environment because a Secure cookie is simply
    dropped over plain http: setting it unconditionally would make login fail
    silently on a developer's machine, and the usual fix for that is to turn
    the flag off everywhere.
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.jwt_refresh_ttl_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.is_production,
        # Lax, not Strict: Strict withholds the cookie on any cross-site
        # navigation, so a pupil following a link to a lesson from a chat or
        # an email would land on the login page despite having a live
        # session. Lax still blocks the cross-site POST that CSRF needs.
        samesite="lax",
    )


def clear_refresh_cookie(response: Response) -> None:
    # The path must match the one it was set with, or the browser deletes
    # nothing and the session outlives the logout.
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


def refresh_cookie_clear_header() -> dict[str, str]:
    """The Set-Cookie header that deletes the refresh cookie, as a raw header.

    Needed because FastAPI discards the injected `Response` object when the
    handler raises: calling `clear_refresh_cookie(response)` and then raising
    an HTTPException reads correctly and does nothing at all, which leaves the
    browser replaying a dead cookie on every navigation until it expires.
    Passing the header through the exception is what actually reaches the
    client.
    """
    probe = Response()
    clear_refresh_cookie(probe)
    return {"set-cookie": probe.headers["set-cookie"]}


def create_video_ticket(lesson_id: int, user_id: int) -> str:
    """Short-lived, stateless token that authorizes GET access to one
    lesson's HLS manifest/segments, for one user. Carried in a path-scoped
    httpOnly cookie because native <video>/hls.js requests can't attach a
    bearer header.

    `sub` binds it to the person it was issued to, so the video endpoint can
    re-check that *they* still have access (see app.api.v1.video) rather
    than trusting whoever holds the cookie for its whole lifetime."""
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": "video",
        "lesson_id": lesson_id,
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.video_ticket_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_video_ticket(token: str, lesson_id: int) -> int:
    """Returns the user id the ticket was issued to. Raises jwt.PyJWTError
    (via decode) or ValueError if the ticket is invalid, expired, scoped to a
    different lesson, or predates user binding."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("purpose") != "video" or payload.get("lesson_id") != lesson_id:
        raise ValueError("Ticket not valid for this lesson")
    sub = str(payload.get("sub", ""))
    if not sub.isdigit():
        raise ValueError("Ticket is not bound to a user")
    return int(sub)


def set_video_ticket_cookie(response: Response, lesson_id: int, user_id: int) -> None:
    """Scopes the cookie to this lesson's own video path, so the browser
    only ever sends it on manifest/segment requests for that lesson --
    matches native <video>/HLS playback, which can't attach a bearer header
    or forward query params to segment requests it issues itself."""
    response.set_cookie(
        key="video_ticket",
        value=create_video_ticket(lesson_id, user_id),
        max_age=settings.video_ticket_ttl_minutes * 60,
        path=f"/api/v1/video/lessons/{lesson_id}",
        httponly=True,
        # Same gating as the refresh cookie: required in production, and
        # unsettable over plain http in development.
        secure=settings.is_production,
        samesite="lax",
    )
