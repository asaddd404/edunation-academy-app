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
_NUMBER_MARKER_RE = re.compile(r"^\s*(\d{1,3})(?:[.)]|\s*-)\s+(?=\S)")
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

# Option marker opening a line. Lowercase is allowed here (some PDFs use
# "а) б) в)") but NOT mid-line -- see split_options_in_line.
_OPTION_START_RE = re.compile(rf"^\s*([{_OPTION_LETTER_CLASS}])[).\-]\s+(?=\S)")
# Option marker *inside* a line: must follow whitespace and be uppercase.
_OPTION_MIDLINE_RE = re.compile(rf"(?<=\s)([{_OPTION_LETTERS}])[).\-]\s+(?=\S)")

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


@dataclass(frozen=True)
class PdfExtract:
    """What :func:`extract_pdf_text` recovers from a file."""

    text: str
    # Line number within `text` -> the marked stretches of that line.
    marks: dict[int, tuple[str, ...]] = field(default_factory=dict)


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
    # "ru" / "kk". Inherited from the variant unless this question overrules
    # it on a strong signal of its own -- see question_language().
    language: str = DEFAULT_LANGUAGE
    options: list[ParsedOption] = field(default_factory=list)
    match_pairs: list[ParsedMatchRef] = field(default_factory=list)
    answer_variants: list[str] | None = None
    answer_text: str | None = None
    confidence: float = 0.0
    needs_review: bool = True
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
    return _TABLE_PIPE_RE.sub("", normalized)


def preprocess(text: str, marks: dict[int, tuple[str, ...]] | None = None) -> list[Line]:
    """Normalizes typography and newlines, collapses intra-line whitespace
    runs, drops whole-line scaffolding, and numbers what survives.

    Line numbers are assigned *after* cleaning so that a question's
    ``raw_line_range`` points at lines the teacher can actually be shown.
    ``marks`` is keyed by the line's number *before* cleaning, and is
    carried onto the surviving Line so the two numbering schemes never have
    to be reconciled anywhere else. Normalization is line-count preserving,
    so that key stays valid.
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


def join_wrapped_lines(lines: list[Line]) -> list[Line]:
    """Glues each wrapped continuation onto the line it belongs to and
    renumbers the result, so ``raw_line_range`` counts the lines a teacher
    sees in the preview rather than the PDF's physical rows.

    Colour marks are concatenated along with the text: a highlight that
    spanned a wrap has to keep covering the joined option.
    """
    merged: list[Line] = []
    for line in lines:
        if merged and _continues_previous(merged[-1].text, line.text):
            previous = merged[-1]
            merged[-1] = Line(
                index=previous.index,
                text=f"{previous.text} {line.text.strip()}".strip(),
                marked=previous.marked + line.marked,
            )
            continue
        merged.append(Line(index=len(merged), text=line.text, marked=line.marked))
    return merged


# ─────────────────────────────────────────────────────────────────────────
# Stage 2c: segmentation into exam variants
# ─────────────────────────────────────────────────────────────────────────


def split_variants(lines: list[Line]) -> list[VariantSegment]:
    """Cuts the document at each "Вариант №N" trigger.

    Two properties matter more than the cutting itself: anything *before*
    the first trigger becomes variant 0 rather than being dropped (plenty
    of files put their first block above the first header), and each
    segment keeps its lines' original numbering, so a question's
    ``raw_line_range`` still points into the whole document.
    """
    segments: list[VariantSegment] = []
    current = VariantSegment(variant_id=0, label=None, lines=[])
    seen = 0

    for line in lines:
        trigger = _VARIANT_TRIGGER_RE.match(line.text.strip())
        if not trigger:
            current.lines.append(line)
            continue

        if any(existing.text.strip() for existing in current.lines):
            segments.append(current)
        seen += 1
        digits = next((group for group in trigger.groups() if group), "")
        current = VariantSegment(
            variant_id=int(digits) if digits else seen,
            label=line.text.strip(),
            lines=[],
        )

    if any(existing.text.strip() for existing in current.lines) or not segments:
        segments.append(current)
    return segments


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

    head_index = _letter_index(head.group(1))
    if head_index < 0:
        return []

    # (label_index, raw_letter, marker_start, text_start)
    marks: list[tuple[int, str, int, int]] = [(head_index, head.group(1), head.start(1), head.end())]
    for candidate in _OPTION_MIDLINE_RE.finditer(stripped, head.end()):
        index = _letter_index(candidate.group(1))
        if index == marks[-1][0] + 1:
            marks.append((index, candidate.group(1), candidate.start(1), candidate.end()))

    if len(marks) == 1 and not _continues_the_run(head_index, previous_index):
        return []

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
        block = QuestionBlock(number=cls.number, first_line=line.index, last_line=line.index)
        if cls.body.strip():
            block.text_lines.append(cls.body.strip())
        block.raw_lines.append(line.text)
        block.matching_hint = bool(_MATCH_HINT_RE.search(cls.body))
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
            if cls.kind is LineKind.QUESTION_MARKER and cls.explicit:
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
            if options:
                apply_option_marks(options, line.marked)
                note_line(line)
                current.options.extend(options)
                continue

        if cls.kind is LineKind.QUESTION_MARKER:
            starts_new = cls.explicit or (not current.matching_hint and len(current.options) >= 2)
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


def determine_qtype(text: str, options: list[ParsedOption], key: KeyResult | None) -> str:
    """Most specific signal wins; see the import contract for the ordering."""
    pairs = key.match_pairs if key else []
    variants = key.answer_variants if key else []

    if pairs:
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

        qtype = determine_qtype(text, block.options, key)
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

        return ParsedQuestion(
            id=question_id,
            raw_line_range=line_range,
            qtype=qtype,
            text=text or raw_text,
            variant_id=segment.variant_id,
            variant_label=segment.label,
            # Classified from the block's raw text -- options and answer key
            # included, since a stem can be neutral while its options are not.
            language=question_language(raw_text, variant_language),
            options=block.options,
            match_pairs=match_pairs,
            answer_variants=answer_variants,
            answer_text=key.answer_text if key else None,
            confidence=confidence,
            needs_review=needs_review,
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
            # The block could not be read, so its own signal is not to be
            # trusted -- fall back to the variant's language.
            language=variant_language,
            options=[],
            match_pairs=[],
            answer_variants=None,
            answer_text=None,
            confidence=0.0,
            needs_review=True,
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
    text: str, marks: dict[int, tuple[str, ...]] | None = None
) -> ParseResult:
    """Entry point. Returns questions plus diagnostics, and never raises --
    a total failure comes back as an empty result carrying the error.

    Each variant is walked under its own ``try/except``, so a file of fifty
    variants with one broken block returns the other forty-nine in full,
    plus whatever the broken one yielded before it failed, plus a
    ``variant_errors`` entry naming it.

    ``marks`` comes from :func:`extract_pdf_text` and is optional: passing
    plain text parses exactly as before, which is what the tests and any
    non-PDF caller rely on.
    """
    warnings: list[str] = []
    try:
        lines = join_wrapped_lines(preprocess(text, marks))
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

    try:
        segments = split_variants(lines)
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

    return ParseResult(
        questions=questions,
        stats=ParseStats(
            total_lines=len(lines),
            total_blocks_detected=blocks_detected,
            needs_review_count=sum(1 for q in questions if q.needs_review),
            parse_errors=[q.parse_error for q in questions if q.parse_error],
            variants_detected=len(segments),
            variant_errors=variant_errors,
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
    language: str = DEFAULT_LANGUAGE
    parse_error: str | None = None
    key_source: str = "none"


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
            language=question.language,
            parse_error=question.parse_error or f"{type(exc).__name__}: {exc}",
        )


def _to_import_payload(question: ParsedQuestion) -> ImportPayload:
    qtype = _DOMAIN_QTYPE.get(question.qtype, "single")
    confidence, needs_review = question.confidence, question.needs_review

    choices: list[tuple[str, bool]] = []
    choice_labels: list[tuple[str, str]] = []
    pairs: list[tuple[str, str]] = []
    variants: list[str] = []

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
        language=question.language,
        parse_error=question.parse_error,
        key_source=question.key_source,
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


def extract_pdf_text(data: bytes) -> PdfExtract:
    """Reads the text layer plus whatever the teacher marked by colour.

    ``marks`` is keyed by line number within ``text`` so the parser can
    stay purely textual: geometry is resolved here, once, and everything
    downstream just asks which runs of a given line were marked.
    """
    import pdfplumber

    pages_text: list[str] = []
    marks: dict[int, tuple[str, ...]] = {}
    line_number = 0

    with pdfplumber.open(BytesIO(data)) as pdf:
        for page in pdf.pages:
            try:
                regions = _marking_regions(page)
                lines = page.extract_text_lines()
            except Exception:  # noqa: BLE001 -- fall back to plain text for this page
                logger.exception("ENT PDF import: could not read layout of a page, using plain text")
                page_text = page.extract_text() or ""
                pages_text.append(page_text)
                line_number += len(page_text.split("\n"))
                continue

            for line in lines:
                text = line.get("text") or ""
                pages_text.append(text)
                # Runs directly, with no `regions` guard: coloured ink is a
                # mark on its own and leaves no region behind.
                runs = _marked_runs(line, regions)
                if runs:
                    marks[line_number] = runs
                line_number += 1

    return PdfExtract(text="\n".join(pages_text), marks=marks)
