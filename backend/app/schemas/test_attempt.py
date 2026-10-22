from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.lesson import QuestionOut
from app.schemas.limits import MAX_ANSWERS_PER_ATTEMPT, MAX_CHOICES_PER_ANSWER, OptionalMediumText, ShortText


class AnswerIn(BaseModel):
    question_id: int
    choice_id: int | None = None
    # Bounded because the grader iterates them: an answer carrying a million
    # ids is one request that pins a worker.
    choice_ids: Annotated[list[int] | None, Field(default=None, max_length=MAX_CHOICES_PER_ANSWER)] = None
    # prompt id -> answer token, as handed out in `match_answers`.
    pairs: Annotated[dict[str, ShortText] | None, Field(default=None, max_length=MAX_CHOICES_PER_ANSWER)] = None
    text: OptionalMediumText = None


class TestAttemptIn(BaseModel):
    __test__ = False

    answers: Annotated[list[AnswerIn], Field(max_length=MAX_ANSWERS_PER_ATTEMPT)]


class TestSessionOut(BaseModel):
    """An open attempt: the questions to answer, under this attempt's
    matching tokens, and when the clock started."""

    attempt_id: int
    started_at: datetime
    # Server-side elapsed time, so a reopened tab resumes the timer where the
    # server has it rather than from zero.
    elapsed_seconds: int
    questions: list[QuestionOut]


class TestAttemptOut(BaseModel):
    __test__ = False

    attempt_id: int
    score: int
    passed: bool
    attempt_number: int
    correct_count: int
    question_count: int
    earned_points: int
    max_points: int
    duration_seconds: int
    # What this attempt added to the student's XP: the accuracy + speed
    # value of the attempt, minus what earlier attempts at the same test
    # already earned (see core.rating.apply_test_attempt_xp).
    xp_earned: int
    accuracy_xp: int
    speed_bonus: int


class SectionTestOut(BaseModel):
    section_id: int
    is_unlocked: bool
    is_passed: bool
    question_count: int
