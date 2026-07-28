from pydantic import BaseModel, field_validator

from app.core.phone import validate_phone
from app.schemas.user import UserOut


class RegisterIn(BaseModel):
    phone: str
    password: str
    first_name: str
    last_name: str

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
    phone: str
    password: str

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return validate_phone(v)


class RefreshIn(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(TokenPair):
    user: UserOut
