from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.lesson import LessonSummaryOut
from app.schemas.limits import NonBlankShortText, OptionalMediumText, OptionalNonBlankShortText, ShortText


class SectionIn(BaseModel):
    title: NonBlankShortText
    description: OptionalMediumText = None


class SectionUpdateIn(BaseModel):
    title: OptionalNonBlankShortText = None
    description: OptionalMediumText = None
    # Section-test bank: questions per attempt. 0 = all of them (NULL).
    questions_per_attempt: int | None = Field(default=None, ge=0, le=200)


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    title: str
    description: str | None
    order_index: int
    created_at: datetime
    questions_per_attempt: int | None = None
    lessons: list[LessonSummaryOut] = []
    has_test: bool = False
    is_test_unlocked: bool = False
    is_test_passed: bool = False
