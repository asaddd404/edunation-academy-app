from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.lesson import LessonSummaryOut


class SectionIn(BaseModel):
    title: str
    description: str | None = None


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
