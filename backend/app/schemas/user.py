from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import RoleEnum


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    first_name: str
    last_name: str
    role: RoleEnum
    is_active: bool
    created_at: datetime


class UserUpdateIn(BaseModel):
    role: RoleEnum | None = None
    is_active: bool | None = None
