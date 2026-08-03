from typing import Any

from pydantic import BaseModel

from app.models.ent_question import EntLanguage, EntQuestionType
from app.schemas.ent_question import EntChoiceIn, EntMatchPairIn


class EntChoiceImportOut(EntChoiceIn):
    """A choice plus the letter it was printed under.

    Extends EntChoiceIn rather than replacing it so the preview can post
    the object straight back to /bulk-create: EntQuestionIn ignores the two
    extra fields. `label` is canonical (always Latin A–H, which is what the
    answer key was matched against); `raw_label` is the glyph actually on
    the page -- Kazakh "Ә)", Cyrillic "Б)" -- so the preview can show the
    teacher what their file says instead of what the parser made of it.
    """

    label: str = ""
    raw_label: str = ""


class EntVariantErrorOut(BaseModel):
    """One "Вариант №N" the parser could not walk. Named individually so a
    50-variant file reports which block to look at."""

    variant_id: int
    variant_label: str | None = None
    error: str


class EntQuestionImportOut(BaseModel):
    """A PDF-extracted question as shown in the teacher's preview screen --
    same shape as EntQuestionIn plus how much the (heuristic, non-LLM)
    parser trusts its own guess, and enough diagnostics to see where in the
    file the guess came from.

    Every field is always present (never omitted) so the preview screen can
    read them without optional chaining on each access.
    """

    qtype: EntQuestionType
    text: str
    # What the detector made of the question. The preview shows it as a flag
    # the teacher can flip, and whatever they leave it on is what
    # /bulk-create saves -- EntQuestionIn reads the same field name.
    language: EntLanguage = EntLanguage.ru
    max_score: int
    choices: list[EntChoiceImportOut] = []
    match_pairs: list[EntMatchPairIn] = []
    answer_variants: list[str] = []
    confidence: float
    needs_review: bool
    # The parser's own verdict, which unlike `qtype` can be "unknown" --
    # EntQuestionType has no such member, so an unrecognized question is
    # presented as `single` for editing while this keeps the truth visible.
    detected_qtype: str
    # [first, last] 0-based line numbers in the cleaned text the block was
    # assembled from, so a teacher can find the source of a bad parse.
    raw_line_range: list[int] = []
    # Which "Вариант №N" of a multi-variant file this came from. 0 with a
    # null label means the document was never split -- either it has one
    # variant or it labels none of them.
    variant_id: int = 0
    variant_label: str | None = None
    parse_error: str | None = None
    # Where the answer came from: "text" (written "Ответ:" in the file),
    # "highlight" (inferred from a colour mark) or "none". The preview
    # shows the highlight case explicitly, since a mis-read colour would
    # otherwise save a wrong answer that looks confidently parsed.
    key_source: str = "none"


class EntPdfImportStats(BaseModel):
    """Import-wide diagnostics, shown to the teacher when something looks off."""

    total_lines: int = 0
    total_blocks_detected: int = 0
    needs_review_count: int = 0
    parse_errors: list[str] = []
    variants_detected: int = 0
    variant_errors: list[EntVariantErrorOut] = []


class EntPdfImportOut(BaseModel):
    subject_id: int
    questions: list[EntQuestionImportOut]
    skipped_count: int
    warnings: list[str] = []
    stats: EntPdfImportStats = EntPdfImportStats()


class EntBulkCreateIn(BaseModel):
    subject_id: int
    # Raw dicts, not EntQuestionIn: a single malformed item must not 422 the
    # whole request before the router gets a chance to skip just that one
    # (see EntBulkCreateOut.skipped).
    questions: list[dict[str, Any]]


class EntBulkCreateSkip(BaseModel):
    index: int
    error: str


class EntBulkCreateOut(BaseModel):
    created_count: int
    skipped: list[EntBulkCreateSkip]
