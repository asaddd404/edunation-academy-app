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
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


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


async def consume_refresh_token(token: str) -> int | None:
    """Validates and deletes the refresh token (rotation). Returns user_id or None."""
    key = f"refresh:{token}"
    user_id = await redis_client.get(key)
    if user_id is None:
        return None
    await redis_client.delete(key)
    await redis_client.srem(_user_sessions_key(user_id), token)
    return int(user_id)


async def revoke_refresh_token(token: str) -> None:
    user_id = await redis_client.get(f"refresh:{token}")
    await redis_client.delete(f"refresh:{token}")
    if user_id is not None:
        await redis_client.srem(_user_sessions_key(user_id), token)


async def revoke_all_refresh_tokens(user_id: int) -> None:
    """Ends every session the user has, on every device."""
    key = _user_sessions_key(user_id)
    tokens = await redis_client.smembers(key)
    if tokens:
        await redis_client.delete(*(f"refresh:{token}" for token in tokens))
    await redis_client.delete(key)


def create_video_ticket(lesson_id: int) -> str:
    """Short-lived, stateless token that authorizes GET access to one
    lesson's HLS manifest/segments. Carried as a query param instead of a
    bearer header because native <video>/hls.js requests can't attach one."""
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": "video",
        "lesson_id": lesson_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.video_ticket_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_video_ticket(token: str, lesson_id: int) -> None:
    """Raises jwt.PyJWTError (via decode) or ValueError if the ticket is
    invalid, expired, or scoped to a different lesson."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("purpose") != "video" or payload.get("lesson_id") != lesson_id:
        raise ValueError("Ticket not valid for this lesson")


def set_video_ticket_cookie(response: Response, lesson_id: int) -> None:
    """Scopes the cookie to this lesson's own video path, so the browser
    only ever sends it on manifest/segment requests for that lesson --
    matches native <video>/HLS playback, which can't attach a bearer header
    or forward query params to segment requests it issues itself.
    NOTE: set secure=True once the app is served over HTTPS."""
    response.set_cookie(
        key="video_ticket",
        value=create_video_ticket(lesson_id),
        max_age=settings.video_ticket_ttl_minutes * 60,
        path=f"/api/v1/video/lessons/{lesson_id}",
        httponly=True,
        samesite="lax",
    )
