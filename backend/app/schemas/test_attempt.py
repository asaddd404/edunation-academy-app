from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.lesson import QuestionOut
from app.schemas.limits import MAX_ANSWERS_PER_ATTEMPT, MAX_CHOICES_PER_ANSWER, OptionalMediumText


class AnswerIn(BaseModel):
    question_id: int
    choice_id: int | None = None
    # Bounded because the grader iterates them: an answer carrying a million
    # ids is one request that pins a worker.
    choice_ids: Annotated[list[int] | None, Field(default=None, max_length=MAX_CHOICES_PER_ANSWER)] = None
    # Values are answer tokens; ints are still accepted (and score 0) so a tab
    # left open across the deploy gets graded instead of a 422.
    pairs: Annotated[dict[str, str | int] | None, Field(default=None, max_length=MAX_CHOICES_PER_ANSWER)] = None
    text: OptionalMediumText = None


class TestAttemptIn(BaseModel):
    answers: Annotated[list[AnswerIn], Field(max_length=MAX_ANSWERS_PER_ATTEMPT)]


class TestAttemptOut(BaseModel):
    score: int
    passed: bool
    attempt_number: int


class SectionTestOut(BaseModel):
    section_id: int
    is_unlocked: bool
    is_passed: bool
    questions: list[QuestionOut] = []
