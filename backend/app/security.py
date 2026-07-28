import secrets
from datetime import datetime, timedelta, timezone

import jwt
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
