"""The fixed ЕНТ structure of a profile subject (профильный предмет).

Every simulation of a profile subject is exactly 40 questions, in this order:

* 1-25   single choice, one correct answer of 4 options (1 point each);
* 26-30  context: one correct answer of 4, about a passage of text (1 point);
* 31-35  matching, 2 points each; may offer more answers than prompts;
* 36-40  multiple choice, 1 to 3 correct answers of 6 options (2 points).

Two things read this table and nothing else restates it: the simulation
generator (which blocks to draw, in which order, how many) and the bank's
format check (which questions a profile subject accepts). A question that
does not fit -- one entered before the subject was made a profile one --
stays in the bank but is never drawn, so an attempt can never come out in
another shape.
"""
from __future__ import annotations

from sqlalchemy import ColumnElement, func, select

from app.models.ent_question import EntChoice, EntQuestion, EntQuestionType

PROFILE_STRUCTURE: tuple[tuple[EntQuestionType, int], ...] = (
    (EntQuestionType.single, 25),
    (EntQuestionType.context, 5),
    (EntQuestionType.matching, 5),
    (EntQuestionType.multiple, 5),
)
PROFILE_QUESTION_COUNT = sum(count for _, count in PROFILE_STRUCTURE)

PROFILE_SINGLE_OPTIONS = 4
PROFILE_MULTIPLE_OPTIONS = 6


def profile_format_problem(qtype: EntQuestionType, choice_count: int, max_score: int) -> str | None:
    """Why a question cannot go into a profile subject, or None if it can.

    On top of EntQuestionIn's own rules, which hold for every subject (1-3
    correct answers for multiple, 2 points for matching and multiple).
    """
    if qtype in (EntQuestionType.single, EntQuestionType.context):
        if choice_count != PROFILE_SINGLE_OPTIONS:
            return f"В профильном предмете вопрос с одним ответом содержит ровно {PROFILE_SINGLE_OPTIONS} варианта"
        if max_score != 1:
            return "В профильном предмете вопрос с одним ответом оценивается в 1 балл"
    elif qtype == EntQuestionType.multiple:
        if choice_count != PROFILE_MULTIPLE_OPTIONS:
            return f"В профильном предмете вопрос с несколькими ответами содержит ровно {PROFILE_MULTIPLE_OPTIONS} вариантов"
    elif qtype == EntQuestionType.short_answer:
        return "В профильном предмете нет вопросов с кратким ответом"
    return None


def _choice_count() -> ColumnElement[int]:
    return (
        select(func.count(EntChoice.id)).where(EntChoice.question_id == EntQuestion.id).scalar_subquery()
    )


def profile_pool_filters(qtype: EntQuestionType) -> list[ColumnElement[bool]]:
    """Extra conditions on a profile block's draw: only questions in the
    profile format, mirroring profile_format_problem."""
    if qtype in (EntQuestionType.single, EntQuestionType.context):
        return [_choice_count() == PROFILE_SINGLE_OPTIONS, EntQuestion.max_score == 1]
    if qtype == EntQuestionType.multiple:
        return [_choice_count() == PROFILE_MULTIPLE_OPTIONS]
    return []
