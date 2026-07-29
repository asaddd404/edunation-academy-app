import secrets
from datetime import datetime, timedelta, timezone

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


async def issue_refresh_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    ttl_seconds = settings.jwt_refresh_ttl_days * 24 * 60 * 60
    await redis_client.set(f"refresh:{token}", str(user_id), ex=ttl_seconds)
    return token


async def consume_refresh_token(token: str) -> int | None:
    """Validates and deletes the refresh token (rotation). Returns user_id or None."""
    key = f"refresh:{token}"
    user_id = await redis_client.get(key)
    if user_id is None:
        return None
    await redis_client.delete(key)
    return int(user_id)


async def revoke_refresh_token(token: str) -> None:
    await redis_client.delete(f"refresh:{token}")


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
