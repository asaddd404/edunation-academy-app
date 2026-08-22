"""Multi-pass state-machine extraction of ЕНТ questions from a PDF's text.

This replaces the previous "flat regex" parser, which had two structural
failure modes that no additional regex could fix:

* **False split** -- a "Сопоставьте" question whose *own* prompt list is
  numbered ``1. 2. 3. 4.`` got shredded into four questions, because a
  line-level regex has no way to know it is already inside a question.
* **False merge** -- options typeset in columns (``E) ... F) ... G) ...``
  on one physical line) collapsed into a single option, because a
  line-level regex only ever produced one match per line.

Both are now structurally impossible rather than patched: parsing is a
finite state machine with explicit states, so "am I inside a question?" is
a fact the parser holds rather than a guess it re-derives per line, and
option extraction runs *within* a line rather than per line.

On top of the FSM sits a normalization + segmentation layer, so a file
that mixes Russian and Kazakh, typographic junk and fifty exam variants
parses as well as a clean single-variant one:

* **normalization** unifies typography globally (dashes, quotes, nbsp,
  zero-width, table pipes) but canonicalizes *letters* only where a marker
  has already been recognized. A global "Cyrillic А → Latin A" pass would
  corrupt the body text of every Russian and Kazakh question, so the
  homoglyph table is consulted per marker candidate and the printed glyph
  is preserved in ``raw_label``;
* **segmentation** cuts the document at "Вариант №N" / "N-нұсқа" triggers
  and runs the FSM once per variant, which both restarts question
  numbering where the document restarts it and confines a failure to the
  variant it happened in;
* **language classification** labels each question ru/kk so a simulation
  can be sat in one language. It runs on the segments the steps above
  produced -- per variant first, per question only to overrule it -- and
  reads nothing the parser has not already structured, so it cannot change
  how a single line is parsed.

The pipeline is a sequence of independently testable pure functions:

    normalize_typography() -> preprocess() -> classify_line()
        -> join_wrapped_lines() -> split_variants() -> run_fsm()
                                                          |-> split_options_in_line()
                                                          |-> parse_key()
                       -> determine_qtype() -> score_confidence()
                       -> detect_variant_language() -> question_language()

Nothing here raises to the caller. Every block is finalized under its own
``try/except`` and every variant is parsed under its own, so one
unparseable question comes back with ``confidence=0.0`` /
``needs_review=True`` / ``parse_error`` set, and one unparseable variant
costs only the questions after the failure inside it -- neither
disappears silently nor takes the rest of the import down.
"""
from __future__ import annotations

import logging
import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────
# Alphabets
# ─────────────────────────────────────────────────────────────────────────

# Option labels run A–H / А–З (8 slots) -- wider than the 5 the old parser
# allowed, because "multiple choice" ЕНТ items routinely go up to H.
_LATIN_LETTERS = "ABCDEFGH"
_CYRILLIC_LETTERS = "АБВГДЕЖЗ"

# Letters that only ever appear as a marker by *shape*, never as the Nth
# letter of a label sequence. Consulted after the two sequence alphabets
# above, so a document labelled "А) Б) В) Г)" still reads В as the third
# option rather than as Latin B -- the author was counting, not spelling.
#
# Several of these canonicalize outside A–H (K, M, N, O, P, T, U, X). That
# is deliberate: _letter_index rejects them, so "Т) ..." or "О) ..." at the
# start of a Russian sentence cannot be mistaken for an option marker.
_GLYPH_TO_LATIN = {
    # Cyrillic letters drawn identically to a Latin one.
    "С": "C", "Н": "H", "К": "K", "М": "M", "О": "O", "Р": "P", "Т": "T", "Х": "X",
    # Kazakh-specific letters -> nearest Latin analogue.
    "Ә": "A", "Ғ": "G", "Қ": "K", "Ң": "N", "Ө": "O", "Ұ": "U", "Ү": "U", "Һ": "H",
}

# Cyrillic letters a typist reaches for when they mean a *Latin* label.
# Kept apart from _GLYPH_TO_LATIN because each of these is also a letter of
# the Cyrillic counting sequence below, so the two readings genuinely
# disagree and only context can settle it:
#
#     "А) Алматы  Б) Астана  В) Шымкент"   -- counting: В is the 3rd, C
#     "А) Никель  В) Азот    С) Кальций"   -- spelling: В is Latin B
#
# Both occur in real papers. Neither reading can be made the global default
# without silently mislabelling the other kind of file, which is why
# letter_indices() returns *every* reading and the run check in
# split_options_in_line picks the one that continues the sequence.
_KEYBOARD_TO_LATIN = {"А": "A", "В": "B", "Д": "D", "Е": "E"}

# Every glyph that may open a marker. Membership here only makes a
# character a *candidate*; canonicalization and the run check in
# split_options_in_line decide whether it really is one.
_OPTION_LETTERS = _LATIN_LETTERS + _CYRILLIC_LETTERS + "".join(_GLYPH_TO_LATIN)
_OPTION_LETTER_CLASS = _OPTION_LETTERS + _OPTION_LETTERS.lower()
# Lowercase letters that may not follow a key letter: "Ответ: Астана" and
# "Жауабы: Ұлытау" are free text, not option А / option U.
_WORD_CONTINUATION_CLASS = "а-яёәөңғқұүһa-z"

# Latin/Cyrillic letters that render identically. Used only to recover a
# key written in the *other* alphabet than the options it refers to
# ("Ответ: В" under Latin-labelled options means B, not C) -- silently
# resolving such a key to the wrong option is the worst thing an import
# tool can do, so it is worth the ten lines.
_CYR_TO_LAT_INDEX = {0: 0, 2: 1, 5: 4}  # А→A, В→B, Е→E
_LAT_TO_CYR_INDEX = {v: k for k, v in _CYR_TO_LAT_INDEX.items()}


def canonical_letter(letter: str) -> str | None:
    """The Latin letter a marker glyph stands for, or None.

    Applied to single characters that a marker regex has already picked
    out -- never to running text (§1.2 of the import contract): Cyrillic
    "А" is an ordinary Russian and Kazakh word letter, so a document-wide
    substitution would rewrite the questions themselves.
    """
    upper = letter.upper()
    if upper in _LATIN_LETTERS:
        return upper
    if upper in _CYRILLIC_LETTERS:
        return _LATIN_LETTERS[_CYRILLIC_LETTERS.index(upper)]
    return _GLYPH_TO_LATIN.get(upper)


def _letter_index(letter: str) -> int:
    """Position of a marker letter in the canonical A–H run, or -1."""
    canonical = canonical_letter(letter)
    return _LATIN_LETTERS.find(canonical) if canonical else -1


def letter_indices(letter: str) -> list[int]:
    """Every position a marker glyph could occupy, best guess first.

    A Latin letter has exactly one reading. An ambiguous Cyrillic one (see
    _KEYBOARD_TO_LATIN) has two, and this returns both rather than choosing:
    the choice belongs to :func:`split_options_in_line`, which knows what
    run the letter has to fit into and can therefore settle it from
    evidence instead of from a guess about the document's typist.

    The counting reading is offered first, so a caller with no run behind it
    reproduces the historical behaviour exactly.
    """
    readings: list[int] = []
    for candidate in (canonical_letter(letter), _KEYBOARD_TO_LATIN.get(letter.upper())):
        index = _LATIN_LETTERS.find(candidate) if candidate else -1
        if index >= 0 and index not in readings:
            readings.append(index)
    return readings


def _is_cyrillic(letter: str) -> bool:
    return letter.upper() in _CYRILLIC_LETTERS


def _canonical_label(index: int) -> str:
    """Every option is relabelled to its Latin equivalent by position, so
    downstream code compares labels without caring which alphabet the PDF
    happened to use."""
    return _LATIN_LETTERS[index] if 0 <= index < len(_LATIN_LETTERS) else "?"


# ─────────────────────────────────────────────────────────────────────────
# Language classification
#
# Runs *after* the document has been cut into variants and the FSM has
# assembled its blocks: it classifies text the parser has already made sense
# of, and never influences how that text was read. Lives up here only
# because the parser's data model carries its result.
# ─────────────────────────────────────────────────────────────────────────

RUSSIAN = "ru"
KAZAKH = "kk"
# What a file with no Kazakh signal anywhere is taken to be. Applied per
# *variant*, never per question -- see question_language().
DEFAULT_LANGUAGE = RUSSIAN

# The nine letters Kazakh Cyrillic adds to the Russian alphabet. This is the
# primary signal and it is subject-independent: a chemistry paper and a
# history paper both use them, and no word list has to be kept up to date.
_KAZAKH_LETTER_RE = re.compile(r"[әғқңөұүһі]", re.IGNORECASE)

# Secondary signal, for pages where the primary one is thin: exam
# scaffolding that recurs in every Kazakh paper whatever the subject.
# Deliberately excludes subject vocabulary ("тұнба", "ерітінді" -- chemistry
# and nothing else): a list that covers one subject reads as coverage while
# providing none for the other four. Words spelled with the extra letters
# are already caught above, so what earns a place here is mostly the words
# that are not -- "жауабы", "сынып", "тапсырма".
_KAZAKH_KEYWORD_RE = re.compile(
    r"\b(?:жауабы|жауаптары|жауап|сұрақ|сынып|тапсырма|нұсқа|дұрыс|сәйкестендіріңіз|төмендегі)\b",
    re.IGNORECASE,
)

# What it takes for a question to overrule the language of the variant it
# sits in: distinct Kazakh-only letters *and* a Kazakh scaffolding word.
#
# Letters alone would not do. A Russian question naming a Kazakh person or
# place carries them -- "Абай Құнанбаев" alone is two distinct ones -- and a
# Russian-language История Казахстана paper is made of such names, so a
# letters-only rule relabels half of it. The scaffolding words ("Жауабы",
# "Дұрыс", "Сұрақ") are what mark the question's *prose* as Kazakh rather
# than its nouns, and they come with the question when one is pasted into a
# foreign variant, because a question brings its own answer key.
_STRONG_KAZAKH_LETTERS = 2
_STRONG_KAZAKH_KEYWORDS = 1


# Cyrillic at all -- the nine extra letters included. A question with none
# of it (a bare equation, a formula, a table of numbers) is evidence of
# neither language and is left out of the variant's vote entirely, rather
# than counted as "not Kazakh".
_CYRILLIC_RE = re.compile(r"[а-яёәғқңөұүһі]", re.IGNORECASE)


@dataclass(frozen=True)
class LanguageSignal:
    """How much a stretch of text looks like Kazakh.

    Kept as two counts rather than one boolean because the threshold differs
    by caller: a question votes on its variant's language on any signal at
    all, while overruling that variant takes a strong one.
    """

    # Distinct Kazakh-only letters, not occurrences: one word repeated on
    # every line of a page is one piece of evidence, not forty.
    letters: int
    keywords: int

    @property
    def strength(self) -> int:
        return self.letters + self.keywords


def kazakh_signal(text: str) -> LanguageSignal:
    lowered = text.lower()
    return LanguageSignal(
        letters=len(set(_KAZAKH_LETTER_RE.findall(lowered))),
        keywords=len(_KAZAKH_KEYWORD_RE.findall(lowered)),
    )


def detect_language(text: str) -> str | None:
    """``"kk"`` when the text carries a Kazakh signal, ``None`` when neutral.

    Returning None rather than "ru" is the point: a block of digits and
    formulas is not evidence of Russian, and every caller has a better
    fallback than a coin flip (the language of the enclosing variant).
    """
    return KAZAKH if kazakh_signal(text).strength > 0 else None


def detect_variant_language(question_texts: Iterable[str]) -> str:
    """The language of one "Вариант №N", voted on question by question.

    Classifying at the variant level rather than per question is what makes
    the detection work on real papers: a variant is written in one language
    throughout, so a question with no signal of its own (numeric options, a
    formula) can inherit an answer that the questions around it prove.

    Two details make the vote hold up on a mixed file:

    * questions with **no Cyrillic at all** don't vote. They are evidence of
      neither language, and counting them as "not Kazakh" would let a maths
      paper full of equations outvote the Kazakh wording of its own stems;
    * a **majority** is required, not a single hit. Any-signal-wins would
      let one Kazakh question pasted into a Russian variant relabel all ten
      -- the exact case question_language() exists to handle at the level it
      actually belongs to.

    Kazakh is the only side that can vote, since Russian has no letter or
    word Kazakh lacks; "not Kazakh" is therefore the abstention as well as
    the Russian ballot, which is why the majority is measured against the
    questions that carry Cyrillic rather than against the Kazakh ones.
    """
    votes = [detect_language(text) for text in question_texts if _CYRILLIC_RE.search(text)]
    if not votes:
        return DEFAULT_LANGUAGE
    kazakh = sum(1 for vote in votes if vote == KAZAKH)
    return KAZAKH if kazakh * 2 > len(votes) else DEFAULT_LANGUAGE


def question_language(text: str, variant_language: str) -> str:
    """The language of a single question inside an already-classified variant.

    Inheriting from the variant is the rule. Within a block the language is
    uniform in practice, and plenty of individual questions carry no signal
    at all -- "2+2=?" with numeric options is the same text in both
    languages -- so deciding those on their own text is exactly how a
    question ends up labelled Russian inside a Kazakh paper.

    The one override is asymmetric on purpose. Kazakh has nine letters
    Russian does not, so "this question is Kazakh though its variant is not"
    is provable and worth acting on (a typesetter pasting one Kazakh item
    into a Russian variant is a real, if rare, occurrence). The reverse is
    not provable: every Russian letter is also a Kazakh letter, so a Russian
    question inside a Kazakh paper is indistinguishable from a Kazakh
    question that happened to use none of the nine. Rather than guess, it
    keeps the variant's language -- and the teacher flips it on the card.

    Overruling therefore takes more evidence than voting does: letters *and*
    a scaffolding word (see _STRONG_KAZAKH_KEYWORDS). The cost of the
    stricter bar is that a Kazakh question pasted under a Russian answer key
    keeps the variant's label; the cost of the looser one was every Russian
    question that names a Kazakh city.
    """
    if variant_language == KAZAKH:
        return KAZAKH
    signal = kazakh_signal(text)
    overrules = signal.letters >= _STRONG_KAZAKH_LETTERS and signal.keywords >= _STRONG_KAZAKH_KEYWORDS
    return KAZAKH if overrules else variant_language


# ─────────────────────────────────────────────────────────────────────────
# Line-level patterns
# ─────────────────────────────────────────────────────────────────────────

# Stage 1 (preprocess) drops a line only when the *whole* line is document
# scaffolding. Deliberately narrow: a numbered line is never scaffolding,
# because that is exactly the matching-question prompt list bug #1 was about.
_DROP_LINE_RES = (
    re.compile(r"^[-=_]{5,}$"),
    re.compile(r"^РАЗДЕЛ\s+[IVXLC\d]+", re.IGNORECASE),
    re.compile(r"^БЛОК\s+\d+", re.IGNORECASE),
    re.compile(r"^ПРЕДМЕТ\s*:", re.IGNORECASE),
    re.compile(r"^Страница\s+\d+\s+из\s+\d+", re.IGNORECASE),
)

# "1. ", "1) ", "1 - " -- ambiguous: also how a matching question numbers
# its own prompts. Rule A in run_fsm() decides which one it is. The dash
# form insists on a space after it so the pairing key "1-C, 2-B" (never
# spaced in practice) is not read as question 1.
#
# The space after "." or ")" is optional, because "1.Молекула с ковалентной
# связью" is how a good tenth of the reference file numbers its questions.
# When it *is* omitted the next character may not be a digit: without that
# guard "12.5%-дық олеум" opens question 12, and -- far worse -- a variant
# header stops being recognized as one, because the unrecognized question
# below it gets glued onto the header line (nine variants were lost this
# way, taking their segment boundaries with them).
_NUMBER_MARKER_RE = re.compile(r"^\s*(\d{1,3})(?:[.)]\s+|[.)](?=\D)|\s*-\s+)(?=\S)")
# "17 Полураспад изотопа..." -- a question whose separator was lost
# altogether. Far too loose to trust on its own (every "400 см³" and
# "2 моль" matches it), so it is classified as a *candidate* and only the
# numbering check in run_fsm can promote it to a real question marker.
_BARE_NUMBER_MARKER_RE = re.compile(r"^\s*(\d{1,3})\s+(?=[^\d\s])")
# A question number typeset on a row of its own, either because its text
# wrapped to the next line ("39." / "Найдите массу...") or because the
# question has no text at all and is nothing but the table under it ("37."
# / "А) Аквакомплексы"). Both are questions; neither is recognizable from
# the line alone, so this is weak too.
_LONE_NUMBER_RE = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*$")
# "Вопрос 5:", "Вопрос №5.", "[5]", "№5", "5-сұрақ" -- unambiguous: a
# prompt list never uses these, so they may open a new question from any
# state.
_EXPLICIT_MARKER_RE = re.compile(
    r"^\s*(?:вопрос\s*№?\s*(\d{1,3})\s*[.):]?"
    r"|\[(\d{1,3})\]"
    r"|№\s*(\d{1,3})"
    r"|(\d{1,3})\s*-?\s*сұрақ\s*[.):]?"
    r")\s+(?=\S)",
    re.IGNORECASE,
)

# A new exam variant. Matched against a whole line, so a "Вариант" that is
# part of a question's wording cannot cut the document in half.
_VARIANT_TRIGGER_RE = re.compile(
    r"^(?:вариант\s*(?:№|N|N°)?\s*(\d{1,4})"
    r"|(\d{1,4})\s*-?\s*нұсқа"
    r"|нұсқа\s*(?:№|N)?\s*(\d{1,4})"
    r"|вариант\s*:\s*(\d{0,4})"
    r"|тест\s*(\d{1,4}))\s*[.:]?\s*$",
    re.IGNORECASE,
)

# What separates a marker letter from the option's text. The forms are
# graded by how much whitespace each may omit, because they differ in how
# ambiguous they are once the whitespace is gone:
#
#   "A) Барий"  "A)Барий"  "A ) Барий"   -- a bracket is only ever a marker
#   "A. Барий"  "A.Барий"                -- a full stop likewise, at a
#                                           letter that _letter_index vets
#   "A - Барий"                          -- a dash MUST keep its space:
#                                           "E-mail", "н-бутан" and
#                                           "A-Cl" are not options
#
# The leading "\s?" covers a marker whose bracket drifted off the letter
# during typesetting ("А )Алюминий" -- six of them in the reference file).
_OPTION_SEPARATOR = r"(?:\s?[).]\s*|\s?-\s+)"
# Option marker opening a line. Lowercase is allowed here (some PDFs use
# "а) б) в)") but NOT mid-line -- see split_options_in_line.
_OPTION_START_RE = re.compile(rf"^\s*([{_OPTION_LETTER_CLASS}]){_OPTION_SEPARATOR}(?=\S)")
# Option marker *inside* a line: must follow whitespace and be uppercase.
_OPTION_MIDLINE_RE = re.compile(rf"(?<=\s)([{_OPTION_LETTERS}]){_OPTION_SEPARATOR}(?=\S)")

# Answer-key phrases. The inflections are enumerated rather than written as
# "Ответ\w*" so that "ответственность - это ..." cannot be read as a key.
_KEY_PHRASE = (
    r"(?:правильн(?:ый|ые|ого|ых|ая|ое)\s+(?:ответ(?:ы|а|ов)?|вариант(?:ы|а|ов)?)"
    r"|ответ(?:ы|а|ов)?"
    r"|ключ(?:и)?"
    # Kazakh: "Жауабы:", "Дұрыс жауабы:". Same shape as the Russian
    # branch, so the "must be followed by a colon" guard below protects it
    # from the instruction "Дұрыс жауапты таңдаңыз:" in the same way.
    r"|(?:дұрыс\s+)?(?:жауаптары|жауабы|жауап))"
)
# A key phrase only counts mid-line when a sentence just ended ("Столица
# Франции? Ответ: Париж"). Otherwise the instruction "Выберите несколько
# верных ответов:" -- which ends in exactly the same words and colon --
# would be read as this question's answer key and swallow its options.
_KEY_RE = re.compile(rf"(?:^|(?<=[?.!])\s|(?<=[(\[]))\s*{_KEY_PHRASE}\s*[:\-–—]\s*", re.IGNORECASE)

_NUMBERED_ITEM_RE = re.compile(r"^\s*(\d{1,2})[.)]\s+(.+)$")
_MATCH_HINT_RE = re.compile(
    r"сопостав|установите\s+соответстви|соотнес|сәйкестендір|сәйкестікті", re.IGNORECASE
)
_MULTI_HINT_RE = re.compile(
    r"неск\w*\s+(?:верн|правильн)|один\s+или\s+неск|бірнеше\s+(?:дұрыс|тура)", re.IGNORECASE
)

# "1-C, 2-B" pairing key, and a line made of nothing but such pairs (a key
# wrapped onto a second physical line).
_PAIR_RE = re.compile(rf"(\d{{1,2}})\s*[-–—:]\s*([{_OPTION_LETTERS}])")
_PAIR_ONLY_LINE_RE = re.compile(
    rf"^\s*\d{{1,2}}\s*[-–—:]\s*[{_OPTION_LETTERS}]"
    rf"(?:\s*[,;]\s*\d{{1,2}}\s*[-–—:]\s*[{_OPTION_LETTERS}])*\s*[.;]?\s*$"
)
# A letter key: "A", "A, B, C", "AC". The negative lookahead stops
# "Ответ: Астана" from being read as option А.
_VARIANTS_RE = re.compile(
    rf"^([{_OPTION_LETTERS}])(?![{_WORD_CONTINUATION_CLASS}])"
    rf"(?:\s*(?:[,;/]|\sи\s)?\s*([{_OPTION_LETTERS}])(?![{_WORD_CONTINUATION_CLASS}]))*"
)
_VARIANT_LETTER_RE = re.compile(rf"[{_OPTION_LETTERS}]")


# ─────────────────────────────────────────────────────────────────────────
# Data model (mirrors the documented API schema)
# ─────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────
# Flags
#
# What is wrong with a question, named rather than summed into a single
# "needs review" boolean. The distinction that matters to the teacher is
# not how confident the parser is but whether the question is *usable*: a
# missing answer key means it cannot be saved, while an oddly-labelled
# option means it can be saved and glanced at. Only the first kind blocks
# saving, which is what makes "save the ready ones" a meaningful button.
# ─────────────────────────────────────────────────────────────────────────

# Blocking: the question cannot be saved as it stands.
FLAG_MISSING_KEY = "missing_key"
FLAG_MISSING_OPTIONS = "missing_options"
FLAG_MATCHING_LEFT_EMPTY = "matching_left_empty"
FLAG_KEY_OPTION_MISMATCH = "key_option_mismatch"
# Advisory: worth a look, saves fine.
FLAG_DUPLICATE_OPTION_LABEL = "duplicate_option_label"
FLAG_OPTIONS_AUTOLABELED = "options_autolabeled"
FLAG_SINGLE_OPTION_ONLY = "single_option_only"
FLAG_MIXED_OPTION_TYPES = "mixed_option_types"
FLAG_NUMBER_GAP = "question_number_gap"
FLAG_LONG_TEXT = "long_question_text"

BLOCKING_FLAGS = frozenset(
    {FLAG_MISSING_KEY, FLAG_MISSING_OPTIONS, FLAG_MATCHING_LEFT_EMPTY, FLAG_KEY_OPTION_MISMATCH}
)


class State(str, Enum):
    LOOKING_FOR_QUESTION = "LOOKING_FOR_QUESTION"
    READING_QUESTION_TEXT = "READING_QUESTION_TEXT"
    READING_OPTIONS = "READING_OPTIONS"
    READING_KEY = "READING_KEY"


class LineKind(str, Enum):
    BLANK = "blank"
    KEY = "key"
    OPTION = "option"
    QUESTION_MARKER = "question_marker"
    TEXT = "text"


@dataclass(frozen=True)
class Line:
    index: int
    text: str
    # Stretches of this line that were marked by colour in the PDF.
    marked: tuple[str, ...] = ()
    # This line is one whole cell of a ruled table. Such a line is complete
    # by construction -- the rule around it is where the author said it
    # ended -- so the wrap-joiner must not merge it with its neighbours.
    from_cell: bool = False


@dataclass
class VariantSegment:
    """One "Вариант №N" block of a multi-variant file.

    ``variant_id`` is the number the document printed; a file with no
    variant triggers at all is one segment numbered 0 with no label, which
    is also what the text *before* the first trigger becomes rather than
    being discarded.
    """

    variant_id: int
    label: str | None
    lines: list[Line]


@dataclass(frozen=True)
class LineClass:
    """What a line looks like *in isolation*. Whether an ambiguous numeric
    marker actually opens a question is the FSM's call, not this one's."""

    kind: LineKind
    number: str | None = None
    body: str = ""
    explicit: bool = False
    # A question marker recognized only by a leading number with no
    # separator at all ("17 Полураспад..."). The shape is far too common in
    # ordinary text to be trusted here, so it is passed up as a candidate
    # and run_fsm accepts it only where the numbering proves it.
    weak: bool = False
    key_start: int = -1
    key_payload: str = ""


# ── Visual-mark detection thresholds ────────────────────────────────────
# A mark must be genuinely colourful, so black text and grey table shading
# never register. 0.2 separates yellow/red/green from off-white paper and
# near-black ink without needing a per-document calibration.
_MIN_MARK_SATURATION = 0.2
_MIN_MARK_BRIGHTNESS = 0.25
# Offsets this far apart in a line still belong to one mark; wider means
# two separate marks. 3 bridges normal word spacing without joining the
# gap between two options typeset in adjacent columns.
_MARK_GAP_TOLERANCE = 3
# Share of an option's characters that must be marked to count as chosen.
# Below half means the highlight probably belongs to a neighbour.
_MARK_COVERAGE = 0.5
_MARK_ANNOT_SUBTYPES = ("Highlight", "Square", "Circle", "Ink", "StrikeOut", "Underline")

# How far apart two glyphs' baselines may sit and still be one line.
# pdfplumber defaults to 3, which is *below* the baseline shift of a
# subscript: in a chemistry paper that turns "A) FeCl₂, 3" into the two
# lines "A) FeCl , 3" and "2", detaching the subscript from its formula and
# leaving a fragment the FSM has to guess at. 6 reunites sub/superscripts
# with their line while staying well under the ~12pt leading between real
# rows, including the rows of a two-column matching table.
_LINE_Y_TOLERANCE = 6

# A PDF is a compressed container: a 15 MB upload can declare tens of
# thousands of pages, or a text layer that decompresses into gigabytes.
# Neither cap rejects a real ЕНТ file -- the reference 60-variant book is a
# few hundred pages -- and both stop a small file from exhausting the box.
MAX_PDF_PAGES = 800
MAX_EXTRACTED_CHARS = 12_000_000


class PdfTooLargeError(Exception):
    """The file is structurally within limits but too big to process."""



@dataclass(frozen=True)
class PdfExtract:
    """What :func:`extract_pdf_text` recovers from a file."""

    text: str
    # Line number within `text` -> the marked stretches of that line.
    marks: dict[int, tuple[str, ...]] = field(default_factory=dict)
    # Line numbers within `text` that are a whole table cell. Keyed the same
    # way as `marks` so both kinds of geometry arrive by the same route and
    # the parser stays textual -- see Line.from_cell.
    cells: frozenset[int] = frozenset()


@dataclass
class ParsedOption:
    label: str
    text: str
    # The letter as it was actually printed. Kept only so a key written in
    # the other alphabet than the options can be resolved by glyph shape
    # (see _resolve_key_letter); `label` is the canonical form everywhere else.
    raw_label: str = ""
    # Marked by colour in the source PDF -- treated as "this is the correct
    # answer" when the file carries no written key.
    marked: bool = False


@dataclass
class ParsedMatchRef:
    left: str
    right: str


@dataclass
class KeyResult:
    match_pairs: list[ParsedMatchRef] = field(default_factory=list)
    answer_variants: list[str] = field(default_factory=list)
    answer_text: str | None = None
    # Text left on the key's line after the key itself -- usually the start
    # of the next question, which must not be thrown away.
    tail: str = ""

    def is_empty(self) -> bool:
        return not (self.match_pairs or self.answer_variants or self.answer_text)


@dataclass
class QuestionBlock:
    """Raw FSM output for one question, before classification."""

    number: str | None = None
    text_lines: list[str] = field(default_factory=list)
    options: list[ParsedOption] = field(default_factory=list)
    key: KeyResult | None = None
    first_line: int = 0
    last_line: int = 0
    raw_lines: list[str] = field(default_factory=list)
    matching_hint: bool = False
    # The left-hand column of a matching question's table, in the order it
    # was printed. Empty for every other question type.
    match_left_items: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class ParsedQuestion:
    id: str
    raw_line_range: list[int]
    qtype: str
    text: str
    # Which "Вариант №N" of the file this came from; 0 / None when the
    # document is a single unlabelled variant.
    variant_id: int = 0
    variant_label: str | None = None
    # The number the question was printed under, within its variant. This is
    # what a bulk answer key ("1-B, 2-C, ...") is keyed by, so it has to
    # survive to the preview screen -- the question's position in the list
    # is not the same thing whenever the file skipped a number.
    question_number: int | None = None
    # "ru" / "kk". Inherited from the variant unless this question overrules
    # it on a strong signal of its own -- see question_language().
    language: str = DEFAULT_LANGUAGE
    options: list[ParsedOption] = field(default_factory=list)
    # The left-hand column of a matching question, recovered from the table
    # the PDF typeset it as. Empty for every other question type.
    match_left_items: list[str] = field(default_factory=list)
    match_pairs: list[ParsedMatchRef] = field(default_factory=list)
    answer_variants: list[str] | None = None
    answer_text: str | None = None
    confidence: float = 0.0
    needs_review: bool = True
    # Everything the teacher should look at, named. See the flag constants
    # above: the blocking ones stop the question being saved as ready.
    flags: list[str] = field(default_factory=list)
    parse_error: str | None = None
    raw_text: str = ""
    # Where the answer came from: written in the file ("text"), inferred
    # from a colour mark ("highlight"), or not found at all ("none").
    key_source: str = "none"


@dataclass
class VariantParseError:
    """A whole variant the FSM could not walk. Reported per variant so the
    teacher is told *which* of fifty blocks to look at rather than being
    handed a file-wide "something went wrong"."""

    variant_id: int
    variant_label: str | None
    error: str


@dataclass
class ParseStats:
    total_lines: int = 0
    total_blocks_detected: int = 0
    needs_review_count: int = 0
    parse_errors: list[str] = field(default_factory=list)
    variants_detected: int = 0
    variant_errors: list[VariantParseError] = field(default_factory=list)
    # How many questions carry each flag. This is what tells a teacher
    # whether 2000 questions need two minutes of key entry or an afternoon
    # of repair -- a single "needs review: 2374" tells them neither.
    by_flag: dict[str, int] = field(default_factory=dict)
    # Repeated "Вариант №N" headers folded back into the block they belong
    # to. A running page header prints once per page, not once per variant.
    duplicate_variant_headers: int = 0


@dataclass
class ParseResult:
    questions: list[ParsedQuestion] = field(default_factory=list)
    stats: ParseStats = field(default_factory=ParseStats)
    # File-level notes for the teacher (empty text layer, absurd variant
    # counts). Distinct from stats.parse_errors, which are per question.
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────
# Stage 1: preprocessing
# ─────────────────────────────────────────────────────────────────────────


# Typographic variants that carry no meaning of their own. Substituting
# them document-wide is safe precisely because none of them is ever a
# letter of a word -- unlike the homoglyphs in _GLYPH_TO_LATIN, which is
# why those are handled per marker instead.
# Written as escapes, not literals: a soft hyphen or zero-width space
# pasted into source is invisible and silently lost by the next editor.
_DASH_CHARS = "\u2012\u2013\u2014\u2015\u2212\u00ad\u2010\u2011"
_QUOTE_CHARS = "\u00ab\u00bb\u201e\u201c\u201d\u2018\u2019\u201a\u2039\u203a"
# nbsp and narrow nbsp become an ordinary space rather than being deleted:
# removing them would run two words together.
_SPACE_CHARS = "\u00a0\u202f\u2007"
_TYPOGRAPHY_TABLE = str.maketrans(
    {
        **{char: "-" for char in _DASH_CHARS},
        **{char: '"' for char in _QUOTE_CHARS},
        **{char: " " for char in _SPACE_CHARS},
    }
)
_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\ufeff]")
# A messenger export header pasted in with the question it introduced
# ("[16:09, 07.04.2025] ~Farangiz: 11. \u049a\u04b1\u0440\u0430\u043c\u044b\u043d\u0434\u0430 90% \u043c\u0435\u0442\u0430\u043d..."). Stripped
# rather than dropped: the question is on the same line as the timestamp,
# so dropping the line loses it and keeping the line hides its number.
_CHAT_PREFIX_RE = re.compile(r"^\s*\[\d{1,2}:\d{2}[^\]]*\]\s*~?[^:]{0,40}:\s*", re.MULTILINE)
# A table rule that survived text extraction. Only removed when it stands
# alone or edges a line -- a "|" inside a word is part of the content.
_TABLE_PIPE_RE = re.compile(r"(?<=\s)\|(?=\s)|^\|+|\|+$", re.MULTILINE)


def normalize_typography(text: str) -> str:
    """Unifies punctuation and strips invisible characters, leaving the
    line structure and every visible word exactly as it was.

    Deliberately does *not* touch letters: see :func:`canonical_letter`.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = normalized.translate(_TYPOGRAPHY_TABLE)
    normalized = _CHAT_PREFIX_RE.sub("", normalized)
    return _TABLE_PIPE_RE.sub("", normalized)


def preprocess(
    text: str,
    marks: dict[int, tuple[str, ...]] | None = None,
    cells: frozenset[int] | None = None,
) -> list[Line]:
    """Normalizes typography and newlines, collapses intra-line whitespace
    runs, drops whole-line scaffolding, and numbers what survives.

    Line numbers are assigned *after* cleaning so that a question's
    ``raw_line_range`` points at lines the teacher can actually be shown.
    ``marks`` and ``cells`` are keyed by the line's number *before* cleaning
    and are carried onto the surviving Line, so the two numbering schemes
    never have to be reconciled anywhere else. Normalization is line-count
    preserving, so those keys stay valid.
    """
    normalized = normalize_typography(text)

    lines: list[Line] = []
    for source_index, raw in enumerate(normalized.split("\n")):
        collapsed = re.sub(r"[^\S\n]{2,}", " ", raw).strip()
        if collapsed and any(pattern.match(collapsed) for pattern in _DROP_LINE_RES):
            continue
        lines.append(
            Line(
                index=len(lines),
                text=collapsed,
                marked=(marks or {}).get(source_index, ()),
                from_cell=source_index in (cells or frozenset()),
            )
        )
    return lines


# ─────────────────────────────────────────────────────────────────────────
# Stage 2a: line classification
# ─────────────────────────────────────────────────────────────────────────


def classify_line(text: str) -> LineClass:
    """Context-free shape of a single line.

    ``key_start``/``key_payload`` are filled in whenever a key phrase
    appears anywhere on the line, even when the line's primary kind is
    something else ("5. Столица Франции? Ответ: Париж").
    """
    stripped = text.strip()
    if not stripped:
        return LineClass(kind=LineKind.BLANK)

    key_match = _KEY_RE.search(stripped)
    key_start = key_match.start() if key_match else -1
    key_payload = stripped[key_match.end():] if key_match else ""

    if key_match and key_match.start() == 0:
        return LineClass(kind=LineKind.KEY, key_start=0, key_payload=key_payload)

    # A question opened on the same line as its own key ("5. Столица
    # Франции? Ответ: Париж") must not carry the key into its text.
    body_end = key_start if key_start > 0 else len(stripped)

    explicit = _EXPLICIT_MARKER_RE.match(stripped)
    if explicit:
        number = explicit.group(1) or explicit.group(2)
        return LineClass(
            kind=LineKind.QUESTION_MARKER,
            number=number,
            body=stripped[explicit.end():body_end],
            explicit=True,
            key_start=key_start,
            key_payload=key_payload,
        )

    option = _OPTION_START_RE.match(stripped)
    if option:
        return LineClass(kind=LineKind.OPTION, body=stripped, key_start=key_start, key_payload=key_payload)

    number_marker = _NUMBER_MARKER_RE.match(stripped)
    if number_marker:
        return LineClass(
            kind=LineKind.QUESTION_MARKER,
            number=number_marker.group(1),
            body=stripped[number_marker.end():body_end],
            explicit=False,
            key_start=key_start,
            key_payload=key_payload,
        )

    # "37." with nothing after it. In the reference file this is a matching
    # question whose stem was left blank and whose whole content is the
    # table below, so the number is all there is to recognize it by. Weak,
    # because a wrecked table drops bare digits on their own lines too.
    lone = _LONE_NUMBER_RE.match(stripped)
    if lone:
        return LineClass(
            kind=LineKind.QUESTION_MARKER,
            number=lone.group(1),
            body="",
            weak=True,
            key_start=key_start,
            key_payload=key_payload,
        )

    bare = _BARE_NUMBER_MARKER_RE.match(stripped)
    if bare:
        return LineClass(
            kind=LineKind.QUESTION_MARKER,
            number=bare.group(1),
            body=stripped[bare.end():body_end],
            explicit=False,
            weak=True,
            key_start=key_start,
            key_payload=key_payload,
        )

    return LineClass(kind=LineKind.TEXT, body=stripped, key_start=key_start, key_payload=key_payload)


# ─────────────────────────────────────────────────────────────────────────
# Stage 2b: rejoining lines a PDF wrapped mid-sentence
# ─────────────────────────────────────────────────────────────────────────

# A line ending in one of these finished a thought; the next line starts a
# new one. ")" is not here: "1)" ends an unfinished marker, not a sentence.
_SENTENCE_ENDINGS = ".!?:;"
# An opening bracket or quote at the end of a line is a wrap *inside* a
# construct, but joining across it would put the bracket's contents on the
# wrong side of a marker check -- so it too blocks the join.
_OPEN_TAIL_RE = re.compile(r"[(\[\"]\s*$")
# A line that is nothing but a marker ("A)", "1.") -- joining onto it
# would fold the marker into the previous line's text and lose it.
_BARE_MARKER_RE = re.compile(rf"^\s*(?:\d{{1,3}}|[{_OPTION_LETTER_CLASS}])\s*[).\-]?\s*$")


def opens_a_structure(text: str) -> bool:
    """True when a line begins something the parser must be able to see:
    a question number, an option letter, an answer key or a variant."""
    if _VARIANT_TRIGGER_RE.match(text.strip()):
        return True
    kind = classify_line(text).kind
    return kind in (LineKind.KEY, LineKind.OPTION, LineKind.QUESTION_MARKER)


def _continues_previous(previous: str, current: str) -> bool:
    """Whether ``current`` is the tail of a sentence wrapped off ``previous``.

    Every condition is a veto, and every veto errs towards *not* joining:
    a question left with a spurious line break keeps its text (harmless),
    while a wrongly joined line can hide a marker inside another line's
    text and lose a whole question (not harmless). That asymmetry is why
    this is a list of refusals rather than a similarity score.
    """
    previous, current = previous.strip(), current.strip()
    if not previous or not current:
        return False
    if previous[-1] in _SENTENCE_ENDINGS:
        return False
    if _OPEN_TAIL_RE.search(previous) or _BARE_MARKER_RE.match(previous):
        return False
    return not opens_a_structure(current)


# How much text the next line must carry to be adopted as that question's
# stem. A stray "4" above another stray "12" is a wrecked table, not a
# question; a full sentence is a question.
_ADOPTION_MIN_LENGTH = 12


def _adopts_next_line(previous: str, current: str) -> bool:
    """Whether ``previous`` is a bare question number owning ``current``.

    The forward direction exists only for this one shape. Everything else
    joins backwards (:func:`_continues_previous`), but a lone "39." has
    nothing behind it to attach to -- and left alone it is not a question
    marker at all, so the question loses its number and its text is
    absorbed by the question above.
    """
    if not _LONE_NUMBER_RE.match(previous.strip()):
        return False
    current = current.strip()
    if len(current) < _ADOPTION_MIN_LENGTH or not _CYRILLIC_RE.search(current):
        return False
    # Whatever follows must be prose, not another piece of structure: a
    # number sitting above an option row is a table artefact.
    return not opens_a_structure(current)


def join_wrapped_lines(lines: list[Line]) -> list[Line]:
    """Glues each wrapped continuation onto the line it belongs to and
    renumbers the result, so ``raw_line_range`` counts the lines a teacher
    sees in the preview rather than the PDF's physical rows.

    Colour marks are concatenated along with the text: a highlight that
    spanned a wrap has to keep covering the joined option.
    """
    merged: list[Line] = []
    for line in lines:
        # A table cell is already exactly as long as its author drew it, so
        # neither joining rule applies at its edges. Without this the option
        # "D) Бутанол-1" and the prompt of the row below it -- adjacent, both
        # unpunctuated, neither opening a structure -- merge into one line
        # and take the next matching pair down with them.
        across_cell = bool(merged) and (merged[-1].from_cell or line.from_cell)
        if merged and not across_cell and _adopts_next_line(merged[-1].text, line.text):
            previous = merged[-1]
            merged[-1] = Line(
                index=previous.index,
                text=f"{previous.text.strip()} {line.text.strip()}",
                marked=previous.marked + line.marked,
                from_cell=previous.from_cell,
            )
            continue
        if merged and not across_cell and _continues_previous(merged[-1].text, line.text):
            previous = merged[-1]
            merged[-1] = Line(
                index=previous.index,
                text=f"{previous.text} {line.text.strip()}".strip(),
                marked=previous.marked + line.marked,
                from_cell=previous.from_cell,
            )
            continue
        merged.append(
            Line(index=len(merged), text=line.text, marked=line.marked, from_cell=line.from_cell)
        )
    return merged


# ─────────────────────────────────────────────────────────────────────────
# Stage 2c: segmentation into exam variants
# ─────────────────────────────────────────────────────────────────────────


def split_variants(lines: list[Line]) -> tuple[list[VariantSegment], int]:
    """Cuts the document at each "Вариант №N" trigger.

    Returns the segments and how many triggers were folded back in as
    repeats. Two properties matter more than the cutting itself: anything
    *before* the first trigger becomes variant 0 rather than being dropped
    (plenty of files put their first block above the first header), and each
    segment keeps its lines' original numbering, so a question's
    ``raw_line_range`` still points into the whole document.

    A trigger that repeats the header of the variant *already open* -- same
    number and same wording -- is a running page header, and is dropped
    rather than cutting the variant into one segment per page.

    Both halves of that test are load-bearing. Matching on the open variant
    rather than on every number ever seen is what lets variant 7 be variant
    7 again in a second section of the file. Requiring the wording to match
    too is what keeps a bilingual paper intact: "Вариант №1" and "1 нұсқа"
    are two different variants that share a number, and a file that
    alternates the languages prints them back to back.
    """
    segments: list[VariantSegment] = []
    current = VariantSegment(variant_id=0, label=None, lines=[])
    seen = 0
    duplicates = 0

    def same_header(label: str) -> bool:
        if current.label is None:
            return False
        return re.sub(r"\s+", "", current.label).casefold() == re.sub(r"\s+", "", label).casefold()

    for line in lines:
        trigger = _VARIANT_TRIGGER_RE.match(line.text.strip())
        if not trigger:
            current.lines.append(line)
            continue

        seen += 1
        digits = next((group for group in trigger.groups() if group), "")
        variant_id = int(digits) if digits else seen
        label = line.text.strip()
        if variant_id and variant_id == current.variant_id and same_header(label):
            duplicates += 1
            continue

        if any(existing.text.strip() for existing in current.lines):
            segments.append(current)
        current = VariantSegment(variant_id=variant_id, label=label, lines=[])

    if any(existing.text.strip() for existing in current.lines) or not segments:
        segments.append(current)
    return segments, duplicates


# ─────────────────────────────────────────────────────────────────────────
# Stage 2d: Rule B -- options within one physical line
# ─────────────────────────────────────────────────────────────────────────


def _continues_the_run(index: int, previous_index: int | None) -> bool:
    """Whether a lone marker letter plausibly belongs to an option run.

    With no options collected yet the run has to start at A or B -- a
    solitary "Д." or "С." that far into the alphabet is a sentence opening
    ("В. Значит, вывод такой"), not option 5. Afterwards the letter must
    advance by one, or by two to tolerate a single option the extraction
    lost; a bigger jump means the regex caught prose.
    """
    if previous_index is None:
        return index <= 1
    return 0 < index - previous_index <= 2


def _resolve_index(letter: str, previous_index: int | None) -> int:
    """Which reading of a marker glyph the surrounding run supports, or -1.

    This is where the counting/spelling ambiguity of "А В Д Е" is decided
    (see _KEYBOARD_TO_LATIN): both readings are tried and the one that fits
    the run wins, so the same code reads

        А) Алматы   Б) Астана   В) Шымкент      -> A, B, C   (counting)
        А) Никель   В) Азот     С) Кальций      -> A, B, C   (spelling)

    correctly, without either document having to be configured. When no
    reading fits the run the letter is not a marker at all.

    An *exact* continuation is preferred over a gapped one, which is what
    keeps the two readings apart when both are admissible: after C, the "Д"
    of "А) В) С) Д)" reads as D (advance 1) rather than as the counting E
    (advance 2, tolerated only when nothing better is on offer).
    """
    candidates = letter_indices(letter)
    if previous_index is None:
        opening = [index for index in candidates if index <= 1]
        return min(opening) if opening else -1
    for advance in (1, 2):
        for index in candidates:
            if index == previous_index + advance:
                return index
    return -1


def split_options_in_line(text: str, previous_index: int | None = None) -> list[ParsedOption]:
    """Splits one physical line into every option it carries (fix for bug #2).

    Three guards keep this from firing on ordinary prose:

    * the line must *open* with an option marker -- so
      "Компания A) владеет патентом B) нет" is left alone, since whatever
      precedes the first marker would have to be discarded anyway;
    * a mid-line marker is accepted only when its letter directly continues
      the run (``E → F → G → H``), so a stray "B)" inside option A's text
      stays part of that text;
    * a line carrying a *single* marker must continue the run its block has
      built so far (``previous_index``), because one letter and a full stop
      is also how a Russian or Kazakh sentence starts. A line carrying two
      or more consecutive markers needs no such context: four letters in
      alphabetical order on one row are not a coincidence, which is what
      keeps the column-typeset ``E) F) G) H)`` case working with no
      preceding options.

    Note this deliberately does *not* rely on a double-space "column gap"
    to spot a mid-line marker: preprocessing collapses whitespace runs, so
    that gap no longer exists by the time we get here. The guards above
    work on single-spaced text and reject strictly more false positives.
    """
    stripped = text.strip()
    head = _OPTION_START_RE.match(stripped)
    if not head:
        return []

    marks = _marker_run(stripped, head, previous_index)
    return _options_from_marks(stripped, marks)


def repeats_a_collected_option(text: str, options: list[ParsedOption]) -> bool:
    """Whether this line reprints an option the block already has.

    A matching question is typeset as one table per prompt, and every one of
    those tables reprints the same right-hand column -- so a two-prompt
    question sends its four options through twice. The second cycle opens at
    ``A)``, which no run check will accept after ``D)``, and the line is
    then appended to option D's text: "SiO₂ A) Pt B) H₂S C) H₃PO₄".

    Identical label *and* identical text is what makes it a reprint rather
    than a fifth answer, and both are required -- a repeated label carrying
    new text is a real (if oddly labelled) option and is kept, flagged
    elsewhere as a duplicate label.
    """
    stripped = text.strip()
    head = _OPTION_START_RE.match(stripped)
    if not head:
        return False
    label = _canonical_label(_letter_index(head.group(1)))
    body = _normalize_for_match(stripped[head.end():])
    return any(
        option.label == label and _normalize_for_match(option.text) == body for option in options
    )


def split_out_of_order_option(text: str, taken: Iterable[str]) -> list[ParsedOption]:
    """A line opening with a marker whose letter runs *backwards*.

    Papers print their options out of order more often than one would like.
    Question 38 of the reference file is typeset

        A) K₃[Fe(CN)₆]   C) H[AuCl₄]   D) H₂[SiF₆]   B) Cu(NH₃)₄₂

    and the run check in :func:`split_options_in_line` -- which only ever
    advances -- rejects that trailing ``B)``. Rejected, it is not dropped
    but *appended to option D's text*, so the question silently loses an
    answer and gains a corrupted one. Requiring an ascending run also
    throws away the whole question if the rule is applied at block level,
    which is why it is the set of labels that is checked here and not their
    order.

    A backwards letter is accepted when it fills a **hole** in the run: not
    already taken, and below the highest label collected so far. A repeated
    letter stays rejected, since "B. Значит, ..." opening a sentence is far
    more likely than a second option B, and the block sorts its options by
    label once it closes.
    """
    stripped = text.strip()
    head = _OPTION_START_RE.match(stripped)
    if not head:
        return []
    index = _letter_index(head.group(1))
    if index < 0:
        return []

    filled = {_letter_index(label) for label in taken}
    filled.discard(-1)
    if not filled or index in filled or index > max(filled):
        return []
    return _options_from_marks(stripped, [(index, head.group(1), head.start(1), head.end())])


# (label_index, raw_letter, marker_start, text_start)
_Marker = tuple[int, str, int, int]


def _marker_run(stripped: str, head: re.Match[str], previous_index: int | None) -> list[_Marker]:
    """The chain of option markers a line carries, starting at ``head``.

    Both readings of an ambiguous head letter are tried, better guess
    first, and the one that yields the longer chain is kept -- so a row of
    columns settles its own alphabet even with no options behind it.
    """
    best: list[_Marker] = []
    for head_index in letter_indices(head.group(1)):
        marks: list[_Marker] = [(head_index, head.group(1), head.start(1), head.end())]
        for candidate in _OPTION_MIDLINE_RE.finditer(stripped, head.end()):
            index = _resolve_index(candidate.group(1), marks[-1][0])
            if index == marks[-1][0] + 1:
                marks.append((index, candidate.group(1), candidate.start(1), candidate.end()))
        # Two or more consecutive markers on one row are not a coincidence
        # and need no context; a lone one has to continue the block's run.
        if len(marks) > 1:
            if len(marks) > len(best):
                best = marks
        elif not best and _resolve_index(head.group(1), previous_index) == head_index:
            best = marks
    return best


def _options_from_marks(stripped: str, marks: list[_Marker]) -> list[ParsedOption]:
    options: list[ParsedOption] = []
    for position, (index, raw_letter, _, text_start) in enumerate(marks):
        text_end = marks[position + 1][2] if position + 1 < len(marks) else len(stripped)
        options.append(
            ParsedOption(
                label=_canonical_label(index),
                text=stripped[text_start:text_end].strip(),
                raw_label=raw_letter,
            )
        )
    return options


# ─────────────────────────────────────────────────────────────────────────
# Stage 2e: matching questions, which are tables rather than lists
#
# A "Сопоставьте" item is typeset as a two-column table, and extracting text
# from a table loses the thing that made it readable -- the columns. What
# arrives is a stream of rows in which the left-hand prompt and the option
# beside it share a physical line:
#
#     A) Никель
#     Катализатор, применяемый для B) Бензол
#     получения полиэтилена при низком
#     давлении C) Ортофосфорная кислота
#     D) Тетрахлорид титана
#     A) Никель                      <- the same four options, again,
#     ...                               because the table has a second row
#
# Read as a list of options (which is what every other question is) this is
# nonsense: eight options, four of them duplicates, and the prompt text
# swallowed into whichever option happened to precede it. Read as a table
# it is exactly two prompts and four answers.
#
# The reconstruction below runs *after* the FSM has bounded the question,
# so it never has to decide where the question starts or ends -- only how
# to read the rows it was given. Every option cycle that restarts at A
# begins a new row, which is the one structural invariant the extraction
# preserves.
# ─────────────────────────────────────────────────────────────────────────

# A row whose left cell is a formula or an equation, not a prompt: option
# markers must not be looked for in it, since "A :B -> A⁺ + :B⁻" opens with
# something the marker regex is delighted to accept.
_FORMULA_ROW_RE = re.compile(r"[→⇌⇄↔]|\s=\s")


def _split_table_row(text: str, previous_index: int | None) -> tuple[str, list[ParsedOption]]:
    """One row of a matching table, as (left-hand text, options on the row).

    Either half may be empty: a row is often only a prompt fragment, or
    only an option that the table put on a line of its own.
    """
    stripped = text.strip()
    if not stripped or _FORMULA_ROW_RE.search(stripped):
        return stripped, []

    head = _OPTION_START_RE.match(stripped)
    if head:
        marks = _marker_run(stripped, head, previous_index)
        if marks:
            return "", _options_from_marks(stripped, marks)
        return stripped, []

    for candidate in _OPTION_MIDLINE_RE.finditer(stripped):
        if _resolve_index(candidate.group(1), previous_index) < 0:
            continue
        marks = _marker_run(stripped, candidate, previous_index)
        if marks:
            return stripped[: candidate.start(1)].strip(), _options_from_marks(stripped, marks)
    return stripped, []


def rebuild_matching_table(block: QuestionBlock) -> None:
    """Re-reads a matching question's rows as a table, in place.

    Leaves the block untouched unless the rows really do repeat their
    options, because that repetition is the evidence that this is a table:
    a "Сопоставьте" question that simply lists four answers once is already
    parsed correctly and must not be rewritten.

    This is the recovery path for files whose tables are *not* ruled, where
    the columns have to be inferred from the text. When the PDF does rule
    them, :func:`column_ordered_table` has already separated the columns and
    the FSM has filed the prompts directly, so there is nothing to rebuild
    and guessing again could only make it worse.
    """
    if block.match_left_items:
        return

    rows = block.raw_lines[1:]
    if not rows:
        return

    # The first row carries the question number, so it is normally the stem
    # rather than part of the table -- but not always: plenty of items open
    # the table on the same line they are numbered on ("40. C₉H₁₂: A) Кумол
    # C₇H₈: B) О-ксилол"). Told apart by whether it holds options at all.
    stem_body = classify_line(block.raw_lines[0]).body
    if stem_body and _split_table_row(stem_body, None)[1]:
        rows = [stem_body, *rows]

    left_items: list[str] = []
    pending: list[str] = []
    options: dict[str, ParsedOption] = {}
    duplicated = False
    two_column = 0
    previous_index: int | None = None

    def flush() -> None:
        joined = " ".join(part for part in pending if part).strip()
        pending.clear()
        if len(joined) >= _MIN_LEFT_ITEM_LENGTH:
            left_items.append(joined)

    for row in rows:
        left, found = _split_table_row(row, previous_index)
        if not found:
            # Retry as the first option of a fresh cycle: after "D)" the run
            # check rejects "A)", which is precisely how a new row announces
            # itself.
            left, found = _split_table_row(row, None)
            if found and found[0].label in options:
                duplicated = True
                flush()

        if left and found:
            # Prompt and answer on one physical line: the signature of a
            # two-column table, and a shape a plain list of options cannot
            # produce.
            two_column += 1
        if left:
            pending.append(left)
        elif found and pending:
            # The left column has gone quiet while the right one carries on,
            # so the prompt that was being collected is complete. This is
            # what separates one table row from the next when the options
            # run only once and never restart at A.
            flush()

        for option in found:
            if option.label in options:
                duplicated = True
            else:
                options[option.label] = option
        if found:
            previous_index = _letter_index(found[-1].label)
    flush()

    # Three ways to know this is a table rather than a list: the options
    # repeated (a second row), or the prompt and the answer shared a line
    # in a question that says it is a matching one, or they shared a line
    # *twice*. The last needs no hint word, because one such line could be
    # an option whose text wrapped past the next marker while two is a
    # column layout -- which is what recovers the items headed only
    # "Соответствие..." or, like "40. C₉H₁₂: A) Кумол", nothing at all.
    enough = duplicated or two_column >= (1 if block.matching_hint else 2)
    if len(options) < 2 or not enough:
        return

    block.match_left_items = left_items
    block.options = [options[label] for label in sorted(options)]


# Shorter than this and the "prompt" is a stray character the table left
# behind (a lone bracket, a subscript digit), not a cell worth showing.
_MIN_LEFT_ITEM_LENGTH = 2

# An option's text is short. A "marker" trailed by a paragraph is a
# sentence that happened to start with a capital and a bracket, and the
# recovery below must not take it.
_MAX_RECOVERED_OPTION_LENGTH = 80


def recover_unstarted_options(block: QuestionBlock) -> None:
    """Options the run check refused because the run does not start at A.

    :func:`split_options_in_line` will not *open* a run past B, since a lone
    "С." begins a Russian sentence as often as it labels option three. With
    nothing to go on that is the right default, but it costs two shapes real
    files contain:

        E) 110   F) 78   G) 94   H) 196   -- a run whose A-D half was
                                             printed under another question
        C) 3                              -- the one option that survived
                                             editing (§4.5)

    Both are recoverable once the block is *closed*, which is why this runs
    here and not in the FSM: "prose or marker?" is a much easier question
    with the whole block in hand than it is one line at a time. A line that
    is nothing but a marker and a short payload, in a block that found no
    options at all, is an option -- there is nothing else it could be.

    Only ever runs on a block with no options, so a question that parsed
    normally cannot be touched by it.
    """
    if block.options:
        return

    recovered: list[ParsedOption] = []
    consumed: list[str] = []
    for text in block.text_lines:
        stripped = text.strip()
        head = _OPTION_START_RE.match(stripped)
        if not head:
            continue
        index = _letter_index(head.group(1))
        body = stripped[head.end():].strip()
        if index < 0 or not body or len(body) > _MAX_RECOVERED_OPTION_LENGTH:
            continue
        if any(option.label == _canonical_label(index) for option in recovered):
            # A repeated label means these are not a run at all.
            return
        recovered.append(
            ParsedOption(label=_canonical_label(index), text=body, raw_label=head.group(1))
        )
        consumed.append(text)

    if not recovered:
        return
    block.options = sorted(recovered, key=lambda option: _letter_index(option.label))
    block.text_lines = [text for text in block.text_lines if text not in consumed]


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def apply_option_marks(options: list[ParsedOption], runs: tuple[str, ...]) -> None:
    """Flags the options a line's colour marks actually cover.

    Compares by content rather than by offset: preprocessing rewrites
    whitespace, so any offset captured during extraction would no longer
    line up by the time the FSM has split the line into options.
    """
    if not runs or not options:
        return

    for option in options:
        target = _normalize_for_match(option.text)
        if not target:
            continue
        covered = 0
        for run in runs:
            candidate = _normalize_for_match(run)
            if not candidate:
                continue
            if target in candidate:
                # The mark spans the whole option (usually a highlight over
                # the entire line, label included).
                covered = len(target)
                break
            if candidate in target:
                covered = max(covered, len(candidate))
        if covered >= _MARK_COVERAGE * len(target):
            option.marked = True


# ─────────────────────────────────────────────────────────────────────────
# Stage 2c: Rule C -- the answer key
# ─────────────────────────────────────────────────────────────────────────


def parse_key(payload: str) -> KeyResult:
    """Parses the text following an "Ответ:"/"Ключ:" phrase.

    Recognizes, in order: pairings (``1-C, 2-B``), letter variants
    (``A, B, C`` or run-together ``AC``), and finally free text
    (``Ответ: Париж``). Anything left over after a pairing/variant key is
    returned as ``tail`` so a question crammed onto the same line as the
    previous answer is not lost.
    """
    body = payload.strip()
    if not body:
        return KeyResult()

    pair_matches = list(_PAIR_RE.finditer(body))
    if pair_matches and pair_matches[0].start() == 0:
        # Only take the leading, uninterrupted run of pairings; the first
        # gap ends the key and starts the tail.
        kept = [pair_matches[0]]
        for candidate in pair_matches[1:]:
            between = body[kept[-1].end():candidate.start()]
            if re.fullmatch(r"[\s,;и]*", between, re.IGNORECASE):
                kept.append(candidate)
            else:
                break
        return KeyResult(
            match_pairs=[ParsedMatchRef(left=m.group(1), right=m.group(2)) for m in kept],
            tail=body[kept[-1].end():].strip(" .;,"),
        )

    variants_match = _VARIANTS_RE.match(body)
    if variants_match:
        letters = _VARIANT_LETTER_RE.findall(variants_match.group(0))
        canonical = [canonical_letter(letter) for letter in letters]
        # An all-caps word made of marker glyphs ("Ответ: СССР") matches the
        # variants pattern but repeats letters, which a real key never does.
        if len(set(canonical)) == len(canonical):
            return KeyResult(
                answer_variants=letters,
                tail=body[variants_match.end():].strip(" .;,"),
            )

    return KeyResult(answer_text=body)


def _resolve_key_letter(letter: str, options: list[ParsedOption]) -> str | None:
    """Maps a key letter onto one of the collected option labels.

    When the key is typed in a different alphabet than the options it refers
    to ("Ответ: В" under Latin-labelled options), the glyph is trusted over
    the alphabet position -- the author was looking at the printed letter,
    so Cyrillic В means B, not the third option.
    """
    labels = [option.label for option in options]
    index = _letter_index(letter)
    if index < 0:
        return None

    letter_is_cyrillic = _is_cyrillic(letter)
    raw_labels = [option.raw_label for option in options if option.raw_label]
    options_are_cyrillic = any(_is_cyrillic(raw) for raw in raw_labels)

    candidates: list[int] = []
    if raw_labels and letter_is_cyrillic != options_are_cyrillic:
        homoglyph = (
            _CYR_TO_LAT_INDEX.get(index) if letter_is_cyrillic else _LAT_TO_CYR_INDEX.get(index)
        )
        if homoglyph is not None:
            candidates.append(homoglyph)
    candidates.append(index)

    for candidate in candidates:
        label = _canonical_label(candidate)
        if label in labels:
            return label
    return None


# ─────────────────────────────────────────────────────────────────────────
# Stage 2d: the state machine
# ─────────────────────────────────────────────────────────────────────────


def run_fsm(lines: list[Line], blocks: list[QuestionBlock] | None = None) -> list[QuestionBlock]:
    """Walks the preprocessed lines, emitting one QuestionBlock per question.

    Pass ``blocks`` to keep whatever was recognized if this raises: the
    list is appended to as each question closes, so a caller holding it
    still has the questions that came before the failure. This is what
    lets a broken variant cost only its own tail (see §4 of the import
    contract) instead of everything the FSM had found in it.

    Rule A (when a numeric marker opens a *new* question) is enforced here
    rather than by a regex, which is the whole point of the rewrite:

    * ``LOOKING_FOR_QUESTION`` -- always. This covers the first question in
      a file, which has no preceding answer key to lean on.
    * ``READING_QUESTION_TEXT`` -- never. A number inside a question stem is
      that question's own prompt list (fix for bug #1).
    * ``READING_OPTIONS`` -- only for a block that already has at least two
      options and shows no "Сопоставьте" hint, i.e. a question that plainly
      ended without printing its key.

    An explicit ``Вопрос N:``/``[N]`` marker is unambiguous and opens a new
    question from any state.
    """
    if blocks is None:
        blocks = []
    state = State.LOOKING_FOR_QUESTION
    current: QuestionBlock | None = None
    queue: deque[Line] = deque(lines)
    # The number of the last question opened. Starts at 0 and is never
    # carried across a call, which is what makes the numbering check work
    # per variant: run_fsm is invoked once per segment, and every variant
    # restarts its questions at 1 (§4.2 of the import contract).
    last_number = 0
    # Set once the open block turns out to number its own prompts; see the
    # READING_OPTIONS branch below. Reset with every block.
    prompt_list_started = False

    def marker_number(cls: LineClass) -> int | None:
        try:
            return int(cls.number) if cls.number is not None else None
        except ValueError:
            return None

    def continues_numbering(cls: LineClass, tolerate_gap: bool = False) -> bool:
        """Whether this marker's number follows on from the last question.

        The strict form is what promotes an otherwise untrustworthy marker
        ("17 Полураспад изотопа...", which is shaped exactly like "400 см³
        раствора"): a number that continues the sequence is a question
        number, and one that does not is prose.
        """
        number = marker_number(cls)
        if number is None:
            return False
        limit = 3 if tolerate_gap else 1
        return last_number < number <= last_number + limit

    def goes_backwards(cls: LineClass) -> bool:
        """Whether this marker numbers something *below* the last question.

        Such a number never opens a question: question numbering only ever
        climbs. What it does mean is a list that restarts inside the current
        block -- a matching question's prompts, or the numbered preamble
        shared by a group of questions ("1. ... 2. ... 3. ..." sitting
        between question 25 and question 26). Both must stay where they are.
        """
        number = marker_number(cls)
        return number is not None and last_number > 0 and number <= last_number

    def last_option_index() -> int | None:
        if current is None or not current.options:
            return None
        return _letter_index(current.options[-1].label)

    def close_current() -> None:
        nonlocal current, state
        if current is not None:
            blocks.append(current)
            current = None
        state = State.LOOKING_FOR_QUESTION

    def open_block(line: Line, cls: LineClass) -> QuestionBlock:
        nonlocal last_number, prompt_list_started
        prompt_list_started = False
        block = QuestionBlock(number=cls.number, first_line=line.index, last_line=line.index)
        if cls.body.strip():
            block.text_lines.append(cls.body.strip())
        block.raw_lines.append(line.text)
        block.matching_hint = bool(_MATCH_HINT_RE.search(cls.body))
        number = marker_number(cls)
        if number is not None:
            # A jump forward means the file skipped a number, which usually
            # means a question lost its own marker and was swallowed by the
            # one above it -- worth telling the teacher, not worth guessing.
            if last_number and number > last_number + 1:
                block.flags.append(FLAG_NUMBER_GAP)
            last_number = number
        return block

    def note_line(line: Line) -> None:
        if current is not None:
            current.last_line = max(current.last_line, line.index)
            current.raw_lines.append(line.text)

    def append_text(block: QuestionBlock, chunk: str) -> None:
        chunk = chunk.strip()
        if not chunk:
            return
        block.text_lines.append(chunk)
        if _MATCH_HINT_RE.search(chunk):
            block.matching_hint = True

    def apply_key(line: Line, block: QuestionBlock, payload: str) -> None:
        nonlocal state
        key = parse_key(payload)
        if block.key is None:
            block.key = key
        else:
            block.key.match_pairs.extend(key.match_pairs)
            block.key.answer_variants.extend(key.answer_variants)
        state = State.READING_KEY
        if key.tail:
            # Re-feed whatever followed the key on the same physical line;
            # it is usually the next question's opening.
            queue.appendleft(Line(index=line.index, text=key.tail))

    while queue:
        line = queue.popleft()
        cls = classify_line(line.text)

        # A marker recognized only by its leading number is prose unless the
        # numbering vouches for it. Demoting it here, once, keeps every
        # state below reading `cls.kind` at face value.
        if cls.kind is LineKind.QUESTION_MARKER and cls.weak and not continues_numbering(cls):
            cls = LineClass(
                kind=LineKind.TEXT,
                body=line.text.strip(),
                key_start=cls.key_start,
                key_payload=cls.key_payload,
            )

        # The first number inside a matching question that does *not*
        # continue the variant's sequence is where that question's own
        # prompt list begins ("1. Дизентерия" under question 5). Recorded
        # before this line is judged, so the "1." that opens the list is
        # itself covered by the rule it establishes.
        #
        # A numbered line that came out of a table cell is exempt: the
        # geometry has already proved it is a prompt, and it is filed as one
        # below. Letting it arm this flag as well would leave the flag set
        # for the rest of the block, and the flag vetoes the *next question's*
        # marker -- which is how a variant ends up 39 questions long, its
        # last one swallowed by the matching item above it.
        #
        # The numbering test matches the one in the branch that reads this
        # flag, gap and all. Armed on the strict test instead, a marker that
        # merely *skipped* a number ("36." then "38.", the 37 lost in
        # typesetting) sets the flag on its way in and is then vetoed by it,
        # so the one damaged question takes the whole tail of the variant
        # down with it.
        if (
            cls.kind is LineKind.QUESTION_MARKER
            and current is not None
            and current.matching_hint
            and not continues_numbering(cls, tolerate_gap=True)
            and not line.from_cell
        ):
            prompt_list_started = True

        # ── READING_KEY: absorb a wrapped key, otherwise close and re-dispatch
        if state is State.READING_KEY:
            if current is not None and (cls.kind is LineKind.KEY or _PAIR_ONLY_LINE_RE.match(line.text)):
                note_line(line)
                payload = cls.key_payload if cls.kind is LineKind.KEY else line.text
                extra = parse_key(payload)
                if current.key is not None:
                    current.key.match_pairs.extend(extra.match_pairs)
                    if not current.key.match_pairs:
                        current.key.answer_variants.extend(extra.answer_variants)
                continue
            close_current()
            # fall through: this line is re-examined in LOOKING_FOR_QUESTION

        # ── LOOKING_FOR_QUESTION
        if state is State.LOOKING_FOR_QUESTION:
            if cls.kind is LineKind.QUESTION_MARKER:
                current = open_block(line, cls)
                state = State.READING_QUESTION_TEXT
                if cls.key_start >= 0 and cls.key_start > 0:
                    apply_key(line, current, cls.key_payload)
            continue

        if current is None:
            # Unreachable by construction (the states below only exist with
            # an open block), but the import must never crash on a state it
            # did not anticipate -- so recover instead of asserting.
            state = State.LOOKING_FOR_QUESTION
            continue

        if cls.kind is LineKind.BLANK:
            continue

        # ── A key phrase closes the body from any in-question state.
        if cls.kind is LineKind.KEY:
            note_line(line)
            apply_key(line, current, cls.key_payload)
            continue

        # ── A table cell that is not an option is the left-hand column of a
        # matching question: the prompt an option gets matched *to*. This is
        # read off the geometry rather than guessed from the text, which is
        # what makes it right even where the table printed the prompt
        # *after* the option beside it -- a table broken across a page break
        # does exactly that, and no reading-order rule can recover it.
        #
        # Requires the block to have opened with a stem of its own, so a
        # plain question typeset inside a table keeps its stem as its stem.
        if line.from_cell and cls.kind is not LineKind.OPTION and current.text_lines:
            note_line(line)
            item = line.text.strip()
            if len(item) >= _MIN_LEFT_ITEM_LENGTH:
                current.match_left_items.append(item)
                current.matching_hint = True
            continue

        # ── READING_QUESTION_TEXT
        if state is State.READING_QUESTION_TEXT:
            if cls.kind is LineKind.OPTION:
                options = split_options_in_line(line.text)
                if options:
                    apply_option_marks(options, line.marked)
                    note_line(line)
                    current.options.extend(options)
                    state = State.READING_OPTIONS
                    continue
            # Rule A used to end here, refusing every numeric marker in this
            # state so that a matching question's own "1. 2. 3." prompt list
            # could not shred it. The numbering check does that job far more
            # precisely: a prompt list restarts at 1 and so cannot continue
            # the variant's sequence, while a genuine next question always
            # does. What this recovers is the question that follows one
            # whose options never parsed -- previously swallowed whole,
            # since nothing else in this state could close a block, which is
            # how every four-question matching tail in the reference file
            # arrived as a single question.
            if cls.kind is LineKind.QUESTION_MARKER and (
                cls.explicit
                or (
                    continues_numbering(cls, tolerate_gap=True)
                    and not prompt_list_started
                    # A marker with no separator at all ("6 моль") is shaped
                    # like the continuation of the stem above it, so it has
                    # to clear the extra bar §4.1 sets. One that was
                    # properly punctuated needs only the numbering.
                    and (not cls.weak or current.matching_hint or len(current.text_lines) >= 2)
                )
            ):
                close_current()
                current = open_block(line, cls)
                state = State.READING_QUESTION_TEXT
                continue
            # Rule A: a bare numeric marker here is part of this question's
            # own list, not a new question.
            note_line(line)
            body = line.text[: cls.key_start] if cls.key_start > 0 else line.text
            append_text(current, body)
            if cls.key_start > 0:
                apply_key(line, current, cls.key_payload)
            continue

        # ── READING_OPTIONS
        if cls.kind is LineKind.OPTION:
            options = split_options_in_line(line.text, last_option_index())
            if not options and len(current.options) >= 2:
                # A matching question reprints its options once per prompt.
                # The reprint carries nothing new, and appending it to the
                # last option's text is the one outcome that loses data.
                if repeats_a_collected_option(line.text, current.options):
                    note_line(line)
                    continue
                # The run went backwards. That is a printing order, not a
                # reason to lose the option -- see split_out_of_order_option.
                options = split_out_of_order_option(
                    line.text, [option.label for option in current.options]
                )
            if options:
                apply_option_marks(options, line.marked)
                note_line(line)
                current.options.extend(options)
                continue

        if cls.kind is LineKind.QUESTION_MARKER:
            starts_new = cls.explicit or (
                # A matching question used to be unclosable by a numeric
                # marker, so the four consecutive matching items that end
                # every variant of the reference file arrived as one block
                # of 33 options. It can now be closed by a number that
                # continues the sequence, as long as no prompt list has
                # claimed the numbering first.
                #
                # The gap is tolerated here for the same reason it is below:
                # when a question loses its own marker in typesetting, the
                # *next* one is the only thing that can close the block, and
                # refusing it because it skipped a number costs every
                # question to the end of the variant rather than the one
                # that was actually damaged.
                (continues_numbering(cls, tolerate_gap=True) and not prompt_list_started)
                if current.matching_hint
                # "at least two options" stands in for "this question
                # plainly ended", and fails in both directions on a real
                # file: a question printed with one surviving option
                # swallows the next question whole, while a numbered
                # preamble between two questions is read as three. A number
                # that continues the sequence settles the first case
                # directly; one that goes backwards settles the second.
                else (
                    not goes_backwards(cls)
                    and (continues_numbering(cls, tolerate_gap=True) or len(current.options) >= 2)
                )
            )
            if starts_new:
                close_current()
                current = open_block(line, cls)
                state = State.READING_QUESTION_TEXT
                continue

        # Anything else continues the last option across a wrapped line.
        note_line(line)
        body = (line.text[: cls.key_start] if cls.key_start > 0 else line.text).strip()
        if body:
            if current.options:
                current.options[-1].text = f"{current.options[-1].text} {body}".strip()
            else:
                append_text(current, body)
        if cls.key_start > 0:
            apply_key(line, current, cls.key_payload)

    close_current()
    return blocks


# ─────────────────────────────────────────────────────────────────────────
# Stage 3: classification and confidence
# ─────────────────────────────────────────────────────────────────────────


def extract_numbered_items(text: str) -> dict[str, str]:
    """The ``1. ... 2. ...`` prompt list inside a matching question's stem."""
    items: dict[str, str] = {}
    for raw_line in text.split("\n"):
        item = _NUMBERED_ITEM_RE.match(raw_line.strip())
        if item:
            items[item.group(1)] = item.group(2).strip()
    return items


def determine_qtype(
    text: str,
    options: list[ParsedOption],
    key: KeyResult | None,
    match_left_items: list[str] | None = None,
) -> str:
    """Most specific signal wins; see the import contract for the ordering."""
    pairs = key.match_pairs if key else []
    variants = key.answer_variants if key else []

    if pairs:
        return "matching"
    # Prompts recovered from a table are as good a signal as a numbered
    # list, and better evidence than the hint word on its own: the table
    # only reconstructs when the options actually repeated.
    if match_left_items and options:
        return "matching"
    if _MATCH_HINT_RE.search(text) and extract_numbered_items(text) and options:
        return "matching"

    # A key naming exactly one letter outranks the "more than five options"
    # heuristic -- a 6-option item with "Ответ: B" is single choice.
    if len(variants) > 1 or _MULTI_HINT_RE.search(text) or (len(options) > 5 and len(variants) != 1):
        if options:
            return "multiple_choice"
    # A key naming exactly one letter is proof of single choice, so it is
    # allowed the full 2..6 options the question form permits. Without a key
    # we fall back to the narrower 2..5 shape -- and still type the question
    # rather than dumping it into "unknown", so the teacher has something to
    # correct rather than something to rebuild.
    if len(variants) == 1 and 2 <= len(options) <= 6:
        return "single_choice"
    if not variants and 2 <= len(options) <= 5:
        return "single_choice"
    if not options and key and key.answer_text:
        return "short_answer"
    return "unknown"


# Past this, a stem has almost certainly absorbed something that is not the
# question -- an editing note, a worked solution, the preamble of the group
# it belongs to. Not cleaned automatically: every automatic rule for
# deciding which sentence is surplus also deletes real question text on some
# other file, and a question with an extra paragraph is repairable while a
# question missing its condition is not.
_LONG_TEXT_CHARS = 400
_MANY_SENTENCES = 3
_NUMERIC_OPTION_RE = re.compile(r"^[\d\s.,;:%°/×·+\-−()]+$")


def _is_numeric_option(text: str) -> bool:
    return bool(text.strip()) and bool(_NUMERIC_OPTION_RE.fullmatch(text.strip()))


def derive_flags(
    text: str,
    options: list[ParsedOption],
    qtype: str,
    key_source: str,
    answer_variants: list[str] | None,
    match_left_items: list[str],
) -> list[str]:
    """Everything about this question the teacher should be told, named.

    Replaces a single "needs review" boolean, which could say that
    something was wrong but never what -- leaving the teacher to open all
    two thousand questions to find the eleven with no options. The
    distinction the names carry is whether the question is *savable*
    (BLOCKING_FLAGS) or merely worth a glance.
    """
    flags: list[str] = []

    if key_source == "none":
        flags.append(FLAG_MISSING_KEY)

    if qtype in ("single_choice", "multiple_choice", "matching", "unknown"):
        if not options:
            flags.append(FLAG_MISSING_OPTIONS)
        elif len(options) == 1:
            flags.append(FLAG_SINGLE_OPTION_ONLY)

    labels = [option.label for option in options]
    if len(labels) != len(set(labels)):
        flags.append(FLAG_DUPLICATE_OPTION_LABEL)

    # A key that names an option this question does not have is worse than
    # no key: saved unchecked it marks the wrong answer correct.
    if answer_variants and options and not set(answer_variants) & set(labels):
        flags.append(FLAG_KEY_OPTION_MISMATCH)

    # A matching question needs prompts to match *against*. They come
    # either from the table (match_left_items) or, when the question
    # numbered them itself, from the stem -- only having neither is a fault.
    if qtype == "matching" and not match_left_items and not extract_numbered_items(text):
        flags.append(FLAG_MATCHING_LEFT_EMPTY)

    numeric = [_is_numeric_option(option.text) for option in options]
    if len(options) > 2 and any(numeric) and not all(numeric):
        flags.append(FLAG_MIXED_OPTION_TYPES)

    if len(text) > _LONG_TEXT_CHARS or len(re.findall(r"[.!?]\s", text)) >= _MANY_SENTENCES:
        flags.append(FLAG_LONG_TEXT)

    return flags


def score_confidence(
    text: str, options: list[ParsedOption], key: KeyResult | None, qtype: str
) -> tuple[float, bool]:
    has_text = bool(text.strip())
    has_options = bool(options)
    has_key = key is not None and not key.is_empty()

    # A short answer having no options is the shape of the type, not a
    # parsing shortfall, so it is not penalized for it.
    if qtype == "short_answer" and has_key and has_text:
        return 0.9, False
    if has_text and has_options and has_key and qtype != "unknown":
        return 0.9, False
    if has_text and (has_options or has_key):
        return 0.4, True
    if has_text:
        return 0.3, True
    return 0.0, True


# ─────────────────────────────────────────────────────────────────────────
# Stage 4: finalization (never raises)
# ─────────────────────────────────────────────────────────────────────────


def _question_number(block: QuestionBlock) -> int | None:
    """The number the block was printed under, or None if it had no marker."""
    try:
        return int(block.number) if block.number is not None else None
    except (TypeError, ValueError):
        return None


def _block_text(block: QuestionBlock) -> str:
    """Everything the block was assembled from -- stem, options and key.

    Used for the language vote as well as for ``raw_text``: a stem can be
    neutral ("2 + 2 = ?") while its options or its "Жауабы:" are not.
    """
    return "\n".join(block.raw_lines).strip()


def _finalize_block(
    block: QuestionBlock, sequence: int, segment: VariantSegment, variant_language: str = DEFAULT_LANGUAGE
) -> ParsedQuestion:
    question_id = f"q_{sequence}"
    raw_text = _block_text(block)
    line_range = [block.first_line, block.last_line]

    try:
        rebuild_matching_table(block)
        recover_unstarted_options(block)
        # Printed order is not meaningful -- an option's label is. A file
        # that typeset "A) C) D) B)" means the same four answers as one that
        # typeset them in order, and the teacher should see B in B's place.
        # Skipped when a label repeats, because then the labels are not
        # trustworthy enough to sort on and the printed order is the better
        # of two bad orders.
        labels = [option.label for option in block.options]
        if len(labels) == len(set(labels)):
            block.options.sort(key=lambda option: _letter_index(option.label))
        text = "\n".join(block.text_lines).strip()
        key = block.key
        key_source = "text" if key is not None and not key.is_empty() else "none"

        # A colour mark stands in for a written key when the file has none.
        # Synthesizing a KeyResult here rather than special-casing further
        # down means typing, confidence and letter resolution all treat a
        # highlighted answer exactly like a printed "Ответ:".
        if key_source == "none":
            marked = [option.label for option in block.options if option.marked]
            if marked:
                key = KeyResult(answer_variants=marked)
                key_source = "highlight"

        qtype = determine_qtype(text, block.options, key, block.match_left_items)
        confidence, needs_review = score_confidence(text, block.options, key, qtype)

        answer_variants: list[str] | None = None
        if key and key.answer_variants:
            resolved = [_resolve_key_letter(letter, block.options) for letter in key.answer_variants]
            # Unresolvable letters still come back canonicalized, so the key
            # and the option labels are quoted in one alphabet even when
            # they could not be matched up.
            answer_variants = [label for label in resolved if label] or [
                canonical_letter(letter) or letter for letter in key.answer_variants
            ]

        match_pairs: list[ParsedMatchRef] = []
        if key and key.match_pairs:
            for pair in key.match_pairs:
                label = _resolve_key_letter(pair.right, block.options) or _canonical_label(
                    _letter_index(pair.right)
                )
                match_pairs.append(ParsedMatchRef(left=pair.left, right=label))

        flags = block.flags + derive_flags(
            text, block.options, qtype, key_source, answer_variants, block.match_left_items
        )

        # A question printed with exactly one option is one whose wrong
        # answers were lost in editing, and the surviving option is
        # overwhelmingly the right one -- so it is filled in rather than
        # left blank. Never silently: the flag stays, review stays on, and
        # the confidence says plainly that this is a guess worth checking.
        if FLAG_SINGLE_OPTION_ONLY in flags and not answer_variants:
            answer_variants = [block.options[0].label]
            confidence = min(confidence, 0.5)

        return ParsedQuestion(
            id=question_id,
            raw_line_range=line_range,
            qtype=qtype,
            text=text or raw_text,
            variant_id=segment.variant_id,
            variant_label=segment.label,
            question_number=_question_number(block),
            # Classified from the block's raw text -- options and answer key
            # included, since a stem can be neutral while its options are not.
            language=question_language(raw_text, variant_language),
            options=block.options,
            match_left_items=block.match_left_items,
            match_pairs=match_pairs,
            answer_variants=answer_variants,
            answer_text=key.answer_text if key else None,
            confidence=confidence,
            needs_review=needs_review or bool(BLOCKING_FLAGS.intersection(flags)),
            flags=sorted(set(flags)),
            parse_error=None,
            raw_text=raw_text,
            key_source=key_source,
        )
    except Exception as exc:  # noqa: BLE001 -- one bad block must not sink the import
        return ParsedQuestion(
            id=question_id,
            raw_line_range=line_range,
            qtype="unknown",
            text=raw_text,
            variant_id=segment.variant_id,
            variant_label=segment.label,
            question_number=_question_number(block),
            # The block could not be read, so its own signal is not to be
            # trusted -- fall back to the variant's language.
            language=variant_language,
            options=[],
            match_pairs=[],
            answer_variants=None,
            answer_text=None,
            confidence=0.0,
            needs_review=True,
            flags=[FLAG_MISSING_KEY, FLAG_MISSING_OPTIONS],
            parse_error=f"{type(exc).__name__}: {exc}",
            raw_text=raw_text,
        )


EMPTY_TEXT_WARNING = "Текст не извлечён из файла — возможно, скан без OCR"

# Past this many variants or lines the file is almost certainly not an exam
# paper. It is still parsed -- refusing to would lose a teacher's upload
# over a heuristic -- but the anomaly is logged and surfaced.
_MANY_VARIANTS = 200
_MANY_LINES = 100_000


def parse_ent_pdf_questions(
    text: str,
    marks: dict[int, tuple[str, ...]] | None = None,
    cells: frozenset[int] | None = None,
) -> ParseResult:
    """Entry point. Returns questions plus diagnostics, and never raises --
    a total failure comes back as an empty result carrying the error.

    Each variant is walked under its own ``try/except``, so a file of fifty
    variants with one broken block returns the other forty-nine in full,
    plus whatever the broken one yielded before it failed, plus a
    ``variant_errors`` entry naming it.

    ``marks`` and ``cells`` come from :func:`extract_pdf_text` and are
    optional: passing plain text parses exactly as before, which is what the
    tests and any non-PDF caller rely on.
    """
    warnings: list[str] = []
    try:
        lines = join_wrapped_lines(preprocess(text, marks, cells))
    except Exception as exc:  # noqa: BLE001
        logger.exception("ENT PDF import: normalization failed")
        return ParseResult(
            questions=[],
            stats=ParseStats(parse_errors=[f"{type(exc).__name__}: {exc}"]),
        )

    if not any(line.text.strip() for line in lines):
        # Said out loud rather than returned as a bare empty list: an empty
        # answer with no explanation reads as "your questions are bad"
        # when the real problem is that the PDF has no text layer at all.
        return ParseResult(stats=ParseStats(total_lines=len(lines)), warnings=[EMPTY_TEXT_WARNING])

    if len(lines) > _MANY_LINES:
        logger.warning("ENT PDF import: unusually large document, %d lines", len(lines))

    duplicate_headers = 0
    try:
        segments, duplicate_headers = split_variants(lines)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ENT PDF import: variant segmentation failed, parsing as one variant")
        warnings.append(f"Не удалось разделить файл на варианты: {type(exc).__name__}")
        segments = [VariantSegment(variant_id=0, label=None, lines=lines)]

    if len(segments) > _MANY_VARIANTS:
        logger.warning("ENT PDF import: %d variants detected, continuing segment by segment", len(segments))
        warnings.append(f"В файле найдено необычно много вариантов: {len(segments)}")

    questions: list[ParsedQuestion] = []
    variant_errors: list[VariantParseError] = []
    blocks_detected = 0

    for segment in segments:
        blocks: list[QuestionBlock] = []
        try:
            run_fsm(segment.lines, blocks)
        except Exception as exc:  # noqa: BLE001 -- one variant must not sink the file
            logger.exception("ENT PDF import: variant %s failed to parse", segment.variant_id)
            variant_errors.append(
                VariantParseError(
                    variant_id=segment.variant_id,
                    variant_label=segment.label,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
        blocks_detected += len(blocks)
        # Decided once per variant, from the questions it actually yielded,
        # and handed to every one of them -- so a question with no signal of
        # its own inherits what its neighbours prove instead of falling back
        # to the global default.
        variant_language = detect_variant_language(_block_text(block) for block in blocks)
        for block in blocks:
            questions.append(_finalize_block(block, len(questions) + 1, segment, variant_language))

    by_flag: dict[str, int] = {}
    for question in questions:
        for flag in question.flags:
            by_flag[flag] = by_flag.get(flag, 0) + 1

    return ParseResult(
        questions=questions,
        stats=ParseStats(
            total_lines=len(lines),
            total_blocks_detected=blocks_detected,
            needs_review_count=sum(1 for q in questions if q.needs_review),
            parse_errors=[q.parse_error for q in questions if q.parse_error],
            variants_detected=len(segments),
            variant_errors=variant_errors,
            by_flag=dict(sorted(by_flag.items(), key=lambda item: -item[1])),
            duplicate_variant_headers=duplicate_headers,
        ),
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────────────────
# Adapter: parser output -> the shape the teacher's preview edits and saves
# ─────────────────────────────────────────────────────────────────────────

_DOMAIN_QTYPE = {
    "single_choice": "single",
    "multiple_choice": "multiple",
    "matching": "matching",
    "short_answer": "short_answer",
    # The DB enum has no "unknown"; the preview shows it as single choice
    # with needs_review set, and `detected_qtype` keeps the parser's real
    # verdict visible.
    "unknown": "single",
}


@dataclass
class ImportPayload:
    """A ParsedQuestion expressed the way EntQuestionIn expects it, so the
    preview screen can post it straight to /bulk-create."""

    qtype: str
    detected_qtype: str
    text: str
    max_score: int
    choices: list[tuple[str, bool]] = field(default_factory=list)
    # (label, raw_label) for each entry of `choices`, in the same order --
    # kept alongside rather than inside, because `choices` is the exact
    # shape EntQuestionIn saves and must not grow fields it would reject.
    # Both lists are built in one pass and never reordered afterwards.
    choice_labels: list[tuple[str, str]] = field(default_factory=list)
    match_pairs: list[tuple[str, str]] = field(default_factory=list)
    answer_variants: list[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_review: bool = True
    raw_line_range: list[int] = field(default_factory=list)
    variant_id: int = 0
    variant_label: str | None = None
    question_number: int | None = None
    language: str = DEFAULT_LANGUAGE
    parse_error: str | None = None
    key_source: str = "none"
    # Named faults, so the preview can say *what* to look at rather than
    # colouring two thousand cards the same shade of "check me".
    flags: list[str] = field(default_factory=list)
    # The prompts a matching question's options get matched to. Carried
    # separately from `match_pairs` because the pairing itself is unknown
    # until the teacher supplies the key -- the prompts are what they need
    # to see in order to supply it.
    match_left_items: list[str] = field(default_factory=list)
    # (label, raw_label, text) for the right-hand column of a matching
    # question -- the candidates each prompt is paired with.
    match_options: list[tuple[str, str, str]] = field(default_factory=list)


def to_import_payload(question: ParsedQuestion) -> ImportPayload:
    """Never raises: an unmappable question degrades to an empty, flagged
    single-choice shell rather than breaking the response."""
    try:
        return _to_import_payload(question)
    except Exception as exc:  # noqa: BLE001
        return ImportPayload(
            qtype="single",
            detected_qtype="unknown",
            text=question.raw_text or question.text,
            max_score=1,
            confidence=0.0,
            needs_review=True,
            raw_line_range=question.raw_line_range,
            variant_id=question.variant_id,
            variant_label=question.variant_label,
            question_number=question.question_number,
            language=question.language,
            parse_error=question.parse_error or f"{type(exc).__name__}: {exc}",
            flags=question.flags,
            match_left_items=question.match_left_items,
        )


def _to_import_payload(question: ParsedQuestion) -> ImportPayload:
    qtype = _DOMAIN_QTYPE.get(question.qtype, "single")
    confidence, needs_review = question.confidence, question.needs_review

    choices: list[tuple[str, bool]] = []
    choice_labels: list[tuple[str, str]] = []
    pairs: list[tuple[str, str]] = []
    variants: list[str] = []
    match_options: list[tuple[str, str, str]] = []

    if qtype in ("single", "multiple"):
        correct = set(question.answer_variants or [])
        flags = [option.label in correct for option in question.options]
        if not any(flags) and question.options:
            # No key at all: mark the minimum that keeps the item valid for
            # /bulk-create. It is already needs_review, and the teacher
            # confirms every answer in the preview before anything is saved.
            wanted = 2 if qtype == "multiple" else 1
            flags = [index < wanted for index in range(len(question.options))]
        choices = [(option.text, flag) for option, flag in zip(question.options, flags)]
        choice_labels = [
            (option.label, option.raw_label or option.label) for option in question.options
        ]
    elif qtype == "matching":
        prompts = extract_numbered_items(question.text)
        answers = {option.label: option.text for option in question.options}
        pairs = [
            (prompts[pair.left], answers[pair.right])
            for pair in question.match_pairs
            if pair.left in prompts and pair.right in answers
        ]
        if not pairs:
            # Fall back to pairing the two lists by order of appearance --
            # structurally plausible, never trusted.
            pairs = [
                (prompt, option.text)
                for prompt, option in zip(prompts.values(), question.options)
            ]
        # The right-hand column travels in a field of its own rather than in
        # `choices`. It has to travel: without it a "Сопоставьте" card
        # arrives showing its prompts and nothing to attach them to, and the
        # teacher cannot answer it at all. But it is not an answer, and
        # EntQuestionIn rejects `choices` on a matching question -- so
        # putting it there would cost the property that an imported question
        # can be posted straight back, which is the one thing keeping the
        # preview's "confident" badge honest.
        match_options = [
            (option.label, option.raw_label or option.label, option.text)
            for option in question.options
        ]
    elif qtype == "short_answer":
        variants = [v.strip() for v in re.split(r"[,/]", question.answer_text or "") if v.strip()]

    max_score = 2 if qtype in ("multiple", "matching") else 1

    # Consistency gate: if the mapped payload could not survive
    # EntQuestionIn's validation, the parse was not as good as it scored.
    correct_count = sum(1 for _, is_correct in choices if is_correct)
    inconsistent = (
        (qtype == "single" and (not 2 <= len(choices) <= 6 or correct_count != 1))
        or (qtype == "multiple" and (not 2 <= len(choices) <= 8 or correct_count < 2))
        or (qtype == "matching" and len(pairs) < 2)
        or (qtype == "short_answer" and not variants)
    )
    if inconsistent and confidence > 0.4:
        confidence, needs_review = 0.4, True
    if question.qtype == "unknown":
        needs_review = True

    return ImportPayload(
        qtype=qtype,
        detected_qtype=question.qtype,
        text=question.text,
        max_score=max_score,
        choices=choices,
        choice_labels=choice_labels,
        match_pairs=pairs,
        answer_variants=variants,
        confidence=confidence,
        needs_review=needs_review,
        raw_line_range=question.raw_line_range,
        variant_id=question.variant_id,
        variant_label=question.variant_label,
        question_number=question.question_number,
        language=question.language,
        parse_error=question.parse_error,
        key_source=question.key_source,
        flags=question.flags,
        match_left_items=question.match_left_items,
        match_options=match_options,
    )


# ─────────────────────────────────────────────────────────────────────────
# PDF text extraction
# ─────────────────────────────────────────────────────────────────────────


def _to_rgb(colour: object) -> tuple[float, float, float] | None:
    """Normalizes a PDF colour operand to RGB.

    PDF colours arrive as 1 component (grey), 3 (RGB) or 4 (CMYK) depending
    on the colour space the producer chose, so every consumer here has to
    go through this rather than indexing the tuple directly.
    """
    if colour is None:
        return None
    if isinstance(colour, (int, float)):
        components: tuple[float, ...] = (float(colour),)
    else:
        try:
            components = tuple(float(c) for c in colour)  # type: ignore[union-attr]
        except (TypeError, ValueError):
            return None

    if len(components) == 1:
        grey = components[0]
        return (grey, grey, grey)
    if len(components) == 3:
        return (components[0], components[1], components[2])
    if len(components) == 4:
        cyan, magenta, yellow, black = components
        return ((1 - cyan) * (1 - black), (1 - magenta) * (1 - black), (1 - yellow) * (1 - black))
    return None


def is_marking_colour(colour: object) -> bool:
    """True for a colour a human chose to draw attention with.

    Deliberately rejects everything on the grey axis: body text is black,
    table rules and shaded header cells are grey, and treating those as
    marks would flag every option on the page. A mark has to be actually
    colourful (yellow, red, green) and not near-black.
    """
    rgb = _to_rgb(colour)
    if rgb is None:
        return False
    lowest, highest = min(rgb), max(rgb)
    return (highest - lowest) >= _MIN_MARK_SATURATION and highest >= _MIN_MARK_BRIGHTNESS


def _marking_regions(page: object) -> list[tuple[float, float, float, float]]:
    """Every (x0, top, x1, bottom) box on the page that marks something.

    Covers the three ways a key gets marked in a digital PDF: the reader's
    highlighter tool (an annotation), a coloured rectangle drawn under the
    text, and an ellipse or freehand stroke drawn around it.
    """
    regions: list[tuple[float, float, float, float]] = []

    for annot in getattr(page, "annots", None) or []:
        subtype = str((annot.get("data") or {}).get("Subtype") or "")
        if not any(kind in subtype for kind in _MARK_ANNOT_SUBTYPES):
            continue
        try:
            regions.append((annot["x0"], annot["top"], annot["x1"], annot["bottom"]))
        except (KeyError, TypeError):
            continue

    for shape in list(getattr(page, "rects", None) or []) + list(getattr(page, "curves", None) or []):
        if not (
            is_marking_colour(shape.get("non_stroking_color"))
            or is_marking_colour(shape.get("stroking_color"))
        ):
            continue
        try:
            regions.append((shape["x0"], shape["top"], shape["x1"], shape["bottom"]))
        except (KeyError, TypeError):
            continue

    return regions


def _char_is_marked(char: dict, regions: list[tuple[float, float, float, float]]) -> bool:
    # Coloured ink is a mark in its own right; otherwise the glyph has to
    # sit inside a highlight/box/ellipse. Testing the glyph's centre rather
    # than its corners keeps a box that clips its text slightly from
    # dropping the first and last letters.
    if is_marking_colour(char.get("non_stroking_color")):
        return True
    try:
        mid_x = (char["x0"] + char["x1"]) / 2
        mid_y = (char["top"] + char["bottom"]) / 2
    except (KeyError, TypeError):
        return False
    return any(x0 <= mid_x <= x1 and top <= mid_y <= bottom for x0, top, x1, bottom in regions)


def _marked_runs(line: dict, regions: list[tuple[float, float, float, float]]) -> tuple[str, ...]:
    """The marked stretches of one physical line, as substrings of its text.

    Works in text offsets rather than concatenated glyphs because
    pdfplumber's ``chars`` carry no space characters -- joining them
    directly would turn "second option" into "secondoption" and break the
    matching in :func:`apply_option_marks`.
    """
    text = line.get("text") or ""
    chars = line.get("chars") or []
    if not text or not chars:
        return ()

    marked: list[int] = []
    cursor = 0
    for char in chars:
        glyph = char.get("text") or ""
        if not glyph:
            continue
        at = text.find(glyph, cursor)
        if at < 0:
            continue
        cursor = at + len(glyph)
        if _char_is_marked(char, regions):
            marked.append(at)

    if not marked:
        return ()

    # Stitch adjacent hits back together, bridging the inter-word spaces
    # that carry no glyph of their own; a wider gap means a separate mark.
    runs: list[str] = []
    start = previous = marked[0]
    for offset in marked[1:]:
        if offset - previous > _MARK_GAP_TOLERANCE:
            runs.append(text[start : previous + 1])
            start = offset
        previous = offset
    runs.append(text[start : previous + 1])
    return tuple(run.strip() for run in runs if run.strip())


# ── Ruled two-column option tables ──────────────────────────────────────
#
# A "Сопоставьте" item is typeset as a ruled table: the left cell holds the
# prompt, the right column holds the option run. Text extraction reads a
# table row back in *x* order, which interleaves the two columns on every
# physical line --
#
#     A) Никель Катализатор, применяемый для B) Бензол получения полиэтилена
#
# -- and once that string exists neither half is recoverable, because the
# boundary between "Никель" and "Катализатор," is invisible in the text:
# no regex can know where the option ended and the prompt resumed. The
# columns are still present in the *geometry*, so they are read column-first
# here, before the text is flattened, and everything downstream then sees
# the shape it already handles -- prompt lines, then A) B) C) D).
#
# This is the one place in the pipeline that looks at layout to decide
# reading order. It is confined to tables that are demonstrably option
# tables (see below) precisely so the rest of the document keeps parsing
# from text alone.

# How many options it takes to believe the right-hand column is an option
# run rather than data that happens to start with a capital letter.
_MIN_TABLE_OPTIONS = 2


def _cell_lines(cell: str | None) -> list[str]:
    return [part.strip() for part in (cell or "").split("\n") if part.strip()]


def column_ordered_table(
    rows: list[list[str | None]], prompts: list[str] | None = None
) -> list[str] | None:
    """A ruled option table's cells, prompts first and options after.

    The shape this recovers is the one the rest of the parser already
    expects of a matching question -- stem, then the prompts, then ``A)``
    through ``D)`` -- so nothing downstream has to know tables exist.

    Returns ``None`` for any table the reordering would *damage*, which is
    the important half of the contract: a single-column box (this file rules
    one around some question stems), or a table whose right-hand column is
    not an option run at all -- a data table inside a question, whose rows
    mean what they mean only when read across. Those keep the ordinary x
    order, exactly as before.

    ``prompts`` is the left-hand column already split into items by
    :func:`left_column_prompts`, which can tell two prompts from one wrapped
    prompt because it still has the geometry. Without it the cell's own line
    breaks are used, which is right only when the cell holds a single item.
    """
    if not rows or max((len(row) for row in rows), default=0) < 2:
        return None

    options: list[str] = []
    for row in rows:
        for entry in _cell_lines(row[-1]):
            # The right-hand column is a *list*: one cell routinely holds
            # all four options, one per typeset line. A line that does not
            # open a new option is the previous one's wrapped tail.
            if options and not _OPTION_START_RE.match(entry):
                options[-1] = f"{options[-1]} {entry}"
            else:
                options.append(entry)

    # The evidence that this is a prompt/options table rather than data: the
    # right-hand column reads as a run of option markers. A data table fails
    # on its first cell and keeps its reading order.
    if len(options) < _MIN_TABLE_OPTIONS or not all(_OPTION_START_RE.match(o) for o in options):
        return None

    if prompts is None:
        prompts = [" ".join(_cell_lines(row[0])) for row in rows]
    return [prompt for prompt in prompts if prompt] + options


# A wrapped line sits about 1.2 line heights below the one it continues; a
# new prompt is pushed down the cell to meet the option it pairs with and
# lands at three or more. The two populations in the reference file are
# 1.15-1.3 and 3.7-6.1, so anywhere between them does -- 2 is the midpoint
# in log terms and needs no per-document calibration.
_PROMPT_GAP_RATIO = 2.0


def left_column_prompts(page: object, table: object) -> list[str] | None:
    """The left-hand column of a table, one entry per prompt.

    Exists because the extracted *text* of that column is genuinely
    ambiguous and no rule over it can be right in both directions:

        "Этиленгликоль"                     -- two prompts, one line each
        "Глицерин"

        "Катализатор, применяемый для"      -- one prompt, three lines
        "получения полиэтилена при низком"
        "давлении"

    Same shape, opposite meaning, and the file has hundreds of each. What
    tells them apart is not in the characters but in the leading, so it is
    read here while the geometry still exists. Returns ``None`` if the
    layout cannot be read, which drops the caller back to the cell's own
    line breaks.
    """
    try:
        columns = list(getattr(table, "columns", None) or [])
        x0, top, _, bottom = (float(value) for value in table.bbox)
        if len(columns) < 2:
            return None
        divider = float(columns[1].bbox[0])
        if divider <= x0:
            return None
        lines = page.crop((x0, top, divider, bottom)).extract_text_lines(  # type: ignore[attr-defined]
            y_tolerance=_LINE_Y_TOLERANCE
        )
    except Exception:  # noqa: BLE001 -- fall back to the text, never fail the page
        logger.exception("ENT PDF import: could not measure a table's left column")
        return None

    prompts: list[str] = []
    previous_top: float | None = None
    for line in lines:
        text = (line.get("text") or "").strip()
        if not text:
            continue
        try:
            line_top = float(line["top"])
            height = float(line["bottom"]) - line_top
        except (KeyError, TypeError, ValueError):
            return None
        continues = (
            prompts
            and previous_top is not None
            and height > 0
            and (line_top - previous_top) <= _PROMPT_GAP_RATIO * height
        )
        if continues:
            prompts[-1] = f"{prompts[-1]} {text}"
        else:
            prompts.append(text)
        previous_top = line_top
    return prompts


def _option_tables(page: object) -> list[tuple[tuple[float, float, float, float], list[str]]]:
    """Every table on the page that must be read column-first, with its box."""
    found: list[tuple[tuple[float, float, float, float], list[str]]] = []
    for table in getattr(page, "find_tables", lambda: [])() or []:
        try:
            rows = table.extract() or []
            bbox = tuple(float(v) for v in table.bbox)
        except Exception:  # noqa: BLE001 -- a malformed table must not sink the page
            logger.exception("ENT PDF import: could not read a table, leaving it as text")
            continue
        ordered = column_ordered_table(rows, left_column_prompts(page, table))
        if ordered and len(bbox) == 4:
            found.append((bbox, ordered))  # type: ignore[arg-type]
    return found


def _line_inside(line: dict, bbox: tuple[float, float, float, float]) -> bool:
    """Whether a text line belongs to a table that will re-emit it itself.

    Tested on the line's vertical *midpoint* so a row whose glyphs overshoot
    the rule by a point is still claimed by its table -- leaving it to the
    ordinary path would print it twice, once interleaved and once in
    column order.
    """
    x0, top, x1, bottom = bbox
    try:
        middle = (float(line["top"]) + float(line["bottom"])) / 2
    except (KeyError, TypeError, ValueError):
        return False
    return top <= middle <= bottom and float(line.get("x1", 0)) > x0 and float(line.get("x0", 0)) < x1


def extract_pdf_text(data: bytes) -> PdfExtract:
    """Reads the text layer plus whatever the teacher marked by colour.

    ``marks`` is keyed by line number within ``text`` so the parser can
    stay purely textual: geometry is resolved here, once, and everything
    downstream just asks which runs of a given line were marked.

    Ruled two-column option tables are the one exception to "read the page
    top to bottom": their cells are emitted column-first (see
    :func:`column_ordered_table`), spliced back in at the table's own
    vertical position so the document's order is otherwise untouched.
    """
    import pdfplumber

    pages_text: list[str] = []
    extracted_chars = 0
    marks: dict[int, tuple[str, ...]] = {}
    cells: set[int] = set()
    line_number = 0

    with pdfplumber.open(BytesIO(data)) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise PdfTooLargeError(
                f"В файле {len(pdf.pages)} страниц — больше допустимых {MAX_PDF_PAGES}"
            )
        for page in pdf.pages:
            if extracted_chars > MAX_EXTRACTED_CHARS:
                raise PdfTooLargeError("Из файла извлечено слишком много текста")
            try:
                regions = _marking_regions(page)
                lines = page.extract_text_lines(y_tolerance=_LINE_Y_TOLERANCE)
                tables = _option_tables(page)
            except Exception:  # noqa: BLE001 -- fall back to plain text for this page
                logger.exception("ENT PDF import: could not read layout of a page, using plain text")
                page_text = page.extract_text() or ""
                pages_text.append(page_text)
                line_number += len(page_text.split("\n"))
                continue

            # (vertical position, tie-break, text, marked runs, is a cell).
            # Built as one list and sorted so a table's column-ordered lines
            # land exactly where the table sat, between the question above
            # and the one below it.
            entries: list[tuple[float, int, str, tuple[str, ...], bool]] = []

            for bbox, texts in tables:
                # Marks inside the table are recovered from the lines it
                # replaces: the cells carry no chars of their own once
                # extracted, but a highlighted option is still the same
                # string, so a run that survives as a substring is re-attached.
                claimed = [line for line in lines if _line_inside(line, bbox)]
                runs = [run for line in claimed for run in _marked_runs(line, regions)]
                for offset, text in enumerate(texts):
                    matched = tuple(run for run in runs if run and run in text)
                    entries.append((bbox[1], offset, text, matched, True))

            for line in lines:
                if any(_line_inside(line, bbox) for bbox, _ in tables):
                    continue
                entries.append(
                    (
                        float(line.get("top") or 0.0),
                        0,
                        line.get("text") or "",
                        # Runs directly, with no `regions` guard: coloured ink
                        # is a mark on its own and leaves no region behind.
                        _marked_runs(line, regions),
                        False,
                    )
                )

            entries.sort(key=lambda entry: (entry[0], entry[1]))
            for _, _, text, runs, is_cell in entries:
                pages_text.append(text)
                extracted_chars += len(text)
                if runs:
                    marks[line_number] = runs
                if is_cell:
                    cells.add(line_number)
                line_number += 1

    return PdfExtract(text="\n".join(pages_text), marks=marks, cells=frozenset(cells))
