from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.core.phone import validate_phone
from app.schemas.limits import Password, ShortText
from app.schemas.user import UserOut


class RegisterIn(BaseModel):
    phone: ShortText
    password: Password
    first_name: ShortText
    last_name: ShortText

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return validate_phone(v)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Пароль должен быть не короче 8 символов")
        return v


class LoginIn(BaseModel):
    phone: ShortText
    # Bounded like the registration field: argon2 will happily hash a 10 MB
    # string, and an unbounded password on an unauthenticated endpoint is a
    # CPU-exhaustion primitive dressed up as a login attempt.
    password: Password

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return validate_phone(v)


class ChangePasswordIn(BaseModel):
    old_password: Password
    new_password: Password

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Пароль должен быть не короче 8 символов")
        return v


class RefreshIn(BaseModel):
    # `secrets.token_urlsafe(32)` is 43 characters; the ceiling only stops an
    # arbitrarily long string being used as a Redis key.
    refresh_token: Annotated[str, Field(max_length=512)]


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(TokenPair):
    user: UserOut
