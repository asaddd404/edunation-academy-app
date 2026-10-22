from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.lesson import LessonSummaryOut
from app.schemas.limits import NonBlankShortText, OptionalMediumText, OptionalNonBlankShortText, ShortText


class SectionIn(BaseModel):
    title: NonBlankShortText
    description: OptionalMediumText = None


class SectionUpdateIn(BaseModel):
    title: OptionalNonBlankShortText = None
    description: OptionalMediumText = None


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    title: str
    description: str | None
    order_index: int
    created_at: datetime
    lessons: list[LessonSummaryOut] = []
    has_test: bool = False
    is_test_unlocked: bool = False
    is_test_passed: bool = False
