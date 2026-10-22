"""Shared length/size bounds for request bodies.

Every one of these is a ceiling, not a business rule: they exist so a single
request cannot push an unbounded string into a TEXT column or an unbounded
list into a query, and they are set far above anything a teacher actually
types. Without them the only limit on `description` is the body-size cap --
25 MB of text per lesson, per request, straight into the database.
"""

from typing import Annotated

from pydantic import AfterValidator, Field

# --- text ------------------------------------------------------------------
ShortText = Annotated[str, Field(max_length=200)]
"""Titles, names, subject and category names."""

OptionalShortText = Annotated[str | None, Field(default=None, max_length=200)]


def _not_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Поле не может быть пустым")
    return stripped


def _not_blank_if_given(value: str | None) -> str | None:
    return None if value is None else _not_blank(value)


NonBlankShortText = Annotated[str, Field(max_length=200), AfterValidator(_not_blank)]
"""A name or title: required, trimmed, and not just spaces. Plain ShortText
let `"   "` through, which made a nameless user, a blank lesson title, and a
category whose slug fell back to the generic `category`."""

OptionalNonBlankShortText = Annotated[
    str | None, Field(default=None, max_length=200), AfterValidator(_not_blank_if_given)
]
"""For PATCH bodies: omitted (None) leaves the field alone, but a value that
is given must still be a real one -- renaming a lesson to "" is refused."""

MediumText = Annotated[str, Field(max_length=2000)]
"""Feedback, glossary explanations, a single answer option."""

OptionalMediumText = Annotated[str | None, Field(default=None, max_length=2000)]

QuestionText = Annotated[str, Field(max_length=5000)]

OptionalLongText = Annotated[str | None, Field(default=None, max_length=20_000)]
"""Free-form student text: a homework answer typed into the box."""

# The rich-text body is a serialized TipTap document, so its ceiling has to
# hold the JSON envelope as well as the prose -- a long lesson with tables
# runs to tens of kilobytes of structure around a few kilobytes of text.
OptionalRichText = Annotated[str | None, Field(default=None, max_length=500_000)]

Password = Annotated[str, Field(min_length=8, max_length=128)]
"""The upper bound matters: argon2 hashes whatever it is given, so an
unbounded password field is a CPU-exhaustion primitive -- a few megabytes per
login request, at one hash each."""

# --- collections -----------------------------------------------------------
MAX_ANSWERS_PER_ATTEMPT = 500
MAX_CHOICES_PER_ANSWER = 32
MAX_BULK_QUESTIONS = 1000
MAX_SUBJECTS_PER_SIMULATION = 20
