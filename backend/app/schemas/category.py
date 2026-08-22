from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.application import ApplicationStatusEnum
from app.schemas.limits import MediumText, OptionalMediumText, OptionalShortText, ShortText


class CategoryIn(BaseModel):
    name: ShortText
    slug: OptionalShortText = None
    description: OptionalMediumText = None


class CategoryUpdateIn(BaseModel):
    name: OptionalShortText = None
    description: OptionalMediumText = None
    is_active: bool | None = None


class TeacherCategoryUpdateIn(BaseModel):
    """Narrower than CategoryUpdateIn -- a teacher (or admin acting via this
    same course-builder endpoint) may only touch the description, not the
    name/slug/is_active, which stay admin-panel-only."""

    description: OptionalMediumText = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    has_image: bool = False
    is_active: bool
    created_at: datetime
    my_application_status: ApplicationStatusEnum | None = None
    lesson_count: int = 0
    total_duration_seconds: int = 0


class AssignTeacherIn(BaseModel):
    teacher_id: int


class CategoryTeacherSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str


class CategoryAdminOut(CategoryOut):
    teachers: list[CategoryTeacherSummary] = []
