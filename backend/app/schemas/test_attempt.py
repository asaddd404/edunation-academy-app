from pydantic import BaseModel

from app.schemas.lesson import QuestionOut


class AnswerIn(BaseModel):
    question_id: int
    choice_id: int


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
