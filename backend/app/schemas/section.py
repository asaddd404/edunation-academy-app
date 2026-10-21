from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.lesson import LessonSummaryOut
from app.schemas.limits import OptionalMediumText, OptionalShortText, QuestionsPerAttempt, ShortText


class SectionIn(BaseModel):
    title: ShortText
    description: OptionalMediumText = None


class SectionUpdateIn(BaseModel):
    title: OptionalShortText = None
    description: OptionalMediumText = None
    # 0 = every question in the bank, every attempt.
    questions_per_attempt: QuestionsPerAttempt | None = None


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
    questions_per_attempt: int | None = None
    # Size of the section test's bank; filled for the course builder.
    test_question_count: int = 0
