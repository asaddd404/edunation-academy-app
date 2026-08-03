"""Language rules shared by the ЕНТ endpoints.

Three things live here rather than inline in the router, all for the same
reason -- they are the parts worth testing without a database:

* :func:`parse_language` -- the boundary check, so an unknown value is
  rejected with a sentence a teacher can act on instead of reaching a
  ``WHERE language = 'kz'`` that quietly matches nothing;
* :func:`question_pool_filters` -- the *one* place that says which questions
  a simulation may draw. Language is an extra condition on the existing
  subject (and qtype) filter, never a query of its own, and having a single
  function say so is what keeps that true;
* :func:`shortage_message` -- the wording of the 422 a short bank produces.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import ColumnElement

from app.models.ent_question import EntLanguage, EntQuestion, EntQuestionType

# Prepositional case, to read naturally inside "Недостаточно вопросов на
# ... языке".
LANGUAGE_NAME = {
    EntLanguage.ru: "русском",
    EntLanguage.kk: "казахском",
}

QTYPE_NAME = {
    EntQuestionType.single: "один правильный ответ",
    EntQuestionType.multiple: "несколько правильных ответов",
    EntQuestionType.matching: "сопоставление",
    EntQuestionType.short_answer: "краткий ответ",
}


class UnknownLanguageError(ValueError):
    """Raised by parse_language; the router turns it into a 400."""


def parse_language(value: str | EntLanguage) -> EntLanguage:
    """The ``EntLanguage`` a request asked for, or UnknownLanguageError.

    Deliberately not left to Pydantic's enum coercion: that answers with a
    422 whose body is the schema's own English ("Input should be 'ru' or
    'kk'"), and this is a value students pick on screen, so the failure is
    worth one explicit Russian sentence.
    """
    if isinstance(value, EntLanguage):
        return value
    try:
        return EntLanguage(value)
    except ValueError as exc:
        allowed = ", ".join(f"'{language.value}'" for language in EntLanguage)
        raise UnknownLanguageError(f"Неизвестный язык сдачи: '{value}'. Допустимые значения: {allowed}") from exc


def question_pool_filters(
    subject_id: int, language: EntLanguage, qtype: EntQuestionType | None = None
) -> list[ColumnElement[bool]]:
    """Which questions a simulation may draw for one subject.

    Language *narrows* the existing per-subject selection; it does not
    replace it. Returning the conditions as a list (rather than a finished
    query) lets the same filter serve both the "how many are there" count
    and the randomized draw without either of them restating it.
    """
    filters: list[ColumnElement[bool]] = [
        EntQuestion.subject_id == subject_id,
        EntQuestion.language == language,
    ]
    if qtype is not None:
        filters.append(EntQuestion.qtype == qtype)
    return filters


@dataclass(frozen=True)
class QuestionShortage:
    """One subject (optionally one qtype within it) that cannot fill its share
    of the requested exam in the requested language."""

    subject_name: str
    needed: int
    available: int
    qtype: EntQuestionType | None = None

    def describe(self) -> str:
        where = f"«{self.subject_name}»"
        if self.qtype is not None:
            where += f", тип «{QTYPE_NAME[self.qtype]}»"
        return f"{where} (нужно {self.needed}, доступно {self.available})"


def shortage_message(language: EntLanguage, shortages: list[QuestionShortage]) -> str:
    """The 422 body for a bank that is too thin in the chosen language.

    Says which subject, how many were needed and how many exist, because the
    person who has to fix it fixes it by importing more questions -- and
    cannot do that from "не удалось начать симуляцию".
    """
    return (
        f"Недостаточно вопросов на {LANGUAGE_NAME[language]} языке: "
        + "; ".join(shortage.describe() for shortage in shortages)
        + ". Добавьте вопросы в банк или выберите другой язык."
    )
