"""Shared length/size bounds for request bodies.

Every one of these is a ceiling, not a business rule: they exist so a single
request cannot push an unbounded string into a TEXT column or an unbounded
list into a query, and they are set far above anything a teacher actually
types. Without them the only limit on `description` is the body-size cap --
25 MB of text per lesson, per request, straight into the database.
"""

import unicodedata
from typing import Annotated

from pydantic import AfterValidator, Field

# --- text ------------------------------------------------------------------
ShortText = Annotated[str, Field(max_length=200)]
"""Titles, names, subject and category names."""

OptionalShortText = Annotated[str | None, Field(default=None, max_length=200)]


# Bidirectional overrides and isolates: invisible, but they re-order how the
# text around them is drawn -- "Анна\u202eанна" renders backwards, enough to
# make a name in a teacher's list read as something else.
_BIDI_CONTROLS = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _not_blank(value: str) -> str:
    stripped = value.strip()
    # Control characters (newlines, tabs, NUL...) have no place in a name or
    # a title: a newline breaks every layout the name appears in, and a NUL
    # byte is refused by Postgres itself -- that one surfaced as a 500.
    if any(unicodedata.category(ch) == "Cc" for ch in stripped) or _BIDI_CONTROLS & set(stripped):
        raise ValueError("Поле содержит недопустимые символы")
    # Zero-width and other format characters alone look like nothing at all.
    if not "".join(ch for ch in stripped if unicodedata.category(ch) != "Cf").strip():
        raise ValueError("Поле не может быть пустым")
    return stripped


def _not_blank_if_given(value: str | None) -> str | None:
    return None if value is None else _not_blank(value)


NonBlankShortText = Annotated[str, Field(max_length=200), AfterValidator(_not_blank)]
"""A name or title: required, trimmed, and not just spaces. Plain ShortText
let `"   "` through, which made a nameless user, a blank lesson title, and a
category whose slug fell back to the generic `category`."""

PersonName = Annotated[str, Field(max_length=100), AfterValidator(_not_blank)]
"""A first or last name. 100, not 200: that is the width of users.first_name
and users.last_name, and a 101-200 character name passed validation only to
fail the INSERT with a 500."""

OptionalPersonName = Annotated[str | None, Field(default=None, max_length=100), AfterValidator(_not_blank_if_given)]

CatalogName = Annotated[str, Field(max_length=150), AfterValidator(_not_blank)]
"""Category and ЕНТ-subject names: their columns, and their slugs', are 150."""

OptionalCatalogName = Annotated[str | None, Field(default=None, max_length=150), AfterValidator(_not_blank_if_given)]

OptionalSlug = Annotated[str | None, Field(default=None, max_length=150)]

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
