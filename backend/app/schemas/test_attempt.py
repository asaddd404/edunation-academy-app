from pydantic import BaseModel


class AnswerIn(BaseModel):
    question_id: int
    choice_id: int


class TestAttemptIn(BaseModel):
    answers: list[AnswerIn]


class TestAttemptOut(BaseModel):
    score: int
    passed: bool
    attempt_number: int
