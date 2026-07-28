from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.application import ApplicationStatusEnum


class CategoryIn(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None


class CategoryUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    is_active: bool
    created_at: datetime
    my_application_status: ApplicationStatusEnum | None = None


class AssignTeacherIn(BaseModel):
    teacher_id: int
