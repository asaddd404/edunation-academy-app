from pydantic import BaseModel

from app.schemas.lesson import QuestionOut


class AnswerIn(BaseModel):
    question_id: int
    choice_id: int | None = None
    choice_ids: list[int] | None = None
    pairs: dict[str, int] | None = None
    text: str | None = None


class TestAttemptIn(BaseModel):
    answers: list[AnswerIn]


class TestAttemptOut(BaseModel):
    score: int
    passed: bool
    attempt_number: int


class SectionTestOut(BaseModel):
    section_id: int
    is_unlocked: bool
    is_passed: bool
    questions: list[QuestionOut] = []
