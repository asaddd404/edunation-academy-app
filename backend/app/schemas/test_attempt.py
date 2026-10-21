from typing import Annotated, Literal

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
    # The attempt being submitted, as returned by .../test/attempts/start.
    # Optional only so a tab opened before per-attempt draws can still submit
    # a test that shows every question; see app.api.v1.tests.
    attempt_id: int | None = None
    answers: Annotated[list[AnswerIn], Field(max_length=MAX_ANSWERS_PER_ATTEMPT)]


class TestAttemptOut(BaseModel):
    score: int
    passed: bool
    attempt_number: int


TestKind = Literal["lesson", "section"]


class TestInfoOut(BaseModel):
    """A test as the student sees it before starting it."""

    kind: TestKind
    id: int
    title: str
    is_unlocked: bool
    is_passed: bool
    # Questions one attempt shows, and how many the bank holds. When the bank
    # is larger, each attempt draws a different selection.
    question_count: int
    pool_size: int
    attempts_used: int
    best_score: int | None
    # Set when an attempt was started and not yet submitted: starting again
    # resumes it rather than drawing a fresh (possibly easier) set.
    in_progress_attempt_id: int | None = None


class TestAttemptStartOut(BaseModel):
    attempt_id: int
    questions: list[QuestionOut]


class TestHubSectionOut(BaseModel):
    section_id: int
    title: str
    lesson_tests: list[TestInfoOut] = []
    section_test: TestInfoOut | None = None


class TestHubCourseOut(BaseModel):
    category_id: int
    category_name: str
    sections: list[TestHubSectionOut] = []
