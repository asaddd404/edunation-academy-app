from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.phone import validate_phone
from app.models.user import RoleEnum


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    first_name: str
    last_name: str
    role: RoleEnum
    is_active: bool
    has_avatar: bool = False
    created_at: datetime


class UserUpdateIn(BaseModel):
    role: RoleEnum | None = None
    is_active: bool | None = None


class PasswordResetOut(BaseModel):
    """The plaintext temporary password, shown to the admin exactly once --
    nothing stores it beyond this response, so there is no second chance to
    retrieve it after the dialog closes."""

    temporary_password: str


class ProfileUpdateIn(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_phone(v)

    @field_validator("first_name", "last_name")
    @classmethod
    def _not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Поле не может быть пустым")
        return v
