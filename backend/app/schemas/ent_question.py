from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.ent_question import EntLanguage, EntQuestionType
from app.schemas.limits import MAX_BULK_QUESTIONS
# The ЕНТ tables have the same column widths as the course-question ones
# (ent_questions.text 1000, choices 500, pairs and variants 300), so the same
# bounds apply; the generic limits were wider and let text through to a 500.
from app.schemas.question import ChoiceText, CourseQuestionText, PairText, VariantText


class EntChoiceIn(BaseModel):
    text: ChoiceText
    is_correct: bool = False


# The passage of a context question: a paragraph or two of source text.
ContextText = Annotated[str, Field(max_length=5000)]

# A matching question may offer this many answers in all (pairs plus
# distractors): enough for "2 prompts, 4 answers" and the ЕНТ's own layouts.
MAX_MATCH_ROWS = 10


class EntMatchPairIn(BaseModel):
    # None (or blank) makes the row a distractor: an answer with no prompt,
    # offered on the right but the correct pair of nothing.
    prompt_text: Annotated[str | None, Field(default=None, max_length=300)] = None
    answer_text: PairText

    @field_validator("prompt_text")
    @classmethod
    def _blank_is_none(cls, v: str | None) -> str | None:
        return v if v and v.strip() else None


class EntQuestionIn(BaseModel):
    qtype: EntQuestionType
    text: CourseQuestionText
    # Only for qtype == context: the passage the question is about.
    context_text: ContextText | None = None
    # Typed as the enum so anything else is rejected here, at the API
    # boundary, rather than at the DB one. Defaulted rather than required:
    # every client that predates the ru/kk split keeps working, and Russian
    # is what those clients were sending.
    language: EntLanguage = EntLanguage.ru
    max_score: int = 1
    choices: list[EntChoiceIn] = []
    match_pairs: list[EntMatchPairIn] = []
    answer_variants: list[VariantText] = []

    @model_validator(mode="after")
    def _validate(self) -> "EntQuestionIn":
        if self.max_score not in (1, 2):
            raise ValueError("Баллы за вопрос — 1 или 2")

        if self.qtype in (EntQuestionType.single, EntQuestionType.context):
            if not (2 <= len(self.choices) <= 6):
                raise ValueError("Вопрос с одним ответом должен содержать от 2 до 6 вариантов")
            if sum(1 for c in self.choices if c.is_correct) != 1:
                raise ValueError("Ровно один вариант должен быть правильным")
            if self.qtype == EntQuestionType.context:
                if not (self.context_text and self.context_text.strip()):
                    raise ValueError("Добавьте текст, на основе которого задан вопрос")
                self.context_text = self.context_text.strip()
            self._require_only(choices=True)
        elif self.qtype == EntQuestionType.multiple:
            if not (2 <= len(self.choices) <= 8):
                raise ValueError("Вопрос с несколькими ответами должен содержать от 2 до 8 вариантов")
            if not (1 <= sum(1 for c in self.choices if c.is_correct) <= 3):
                raise ValueError("Правильных вариантов должно быть от 1 до 3")
            if self.max_score != 2:
                raise ValueError("Вопрос с несколькими ответами должен давать 2 балла (частичная защита)")
            self._require_only(choices=True)
        elif self.qtype == EntQuestionType.matching:
            prompts = sum(1 for p in self.match_pairs if p.prompt_text)
            if prompts < 2:
                raise ValueError("Сопоставление должно содержать минимум 2 пары")
            if len(self.match_pairs) > MAX_MATCH_ROWS:
                raise ValueError(f"В сопоставлении не больше {MAX_MATCH_ROWS} вариантов ответа")
            if self.max_score != 2:
                raise ValueError("Вопрос на сопоставление должен давать 2 балла (частичная защита)")
            self._require_only(match_pairs=True)
        elif self.qtype == EntQuestionType.short_answer:
            if not self.answer_variants or not any(v.strip() for v in self.answer_variants):
                raise ValueError("Нужен хотя бы один правильный ответ")
            self._require_only(answer_variants=True)
        return self

    def _require_only(self, choices: bool = False, match_pairs: bool = False, answer_variants: bool = False) -> None:
        if not choices and self.choices:
            raise ValueError("Поле choices не используется для этого типа вопроса")
        if not match_pairs and self.match_pairs:
            raise ValueError("Поле match_pairs не используется для этого типа вопроса")
        if not answer_variants and self.answer_variants:
            raise ValueError("Поле answer_variants не используется для этого типа вопроса")
        if self.qtype != EntQuestionType.context:
            self.context_text = None


class EntChoiceTeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    is_correct: bool
    order_index: int


class EntMatchPairTeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # None for a distractor.
    prompt_text: str | None
    answer_text: str
    order_index: int


class EntAnswerVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str


class EntQuestionTeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    qtype: EntQuestionType
    text: str
    context_text: str | None = None
    language: EntLanguage
    has_image: bool = False
    max_score: int
    order_index: int
    choices: list[EntChoiceTeacherOut] = []
    match_pairs: list[EntMatchPairTeacherOut] = []
    answer_variants: list[EntAnswerVariantOut] = []


class EntBulkDeleteIn(BaseModel):
    # The router enforces the real batch cap (MAX_BULK_DELETE_BATCH) after
    # de-duplicating; this bound only stops a multi-megabyte id list being
    # parsed into memory first.
    question_ids: Annotated[list[int], Field(max_length=MAX_BULK_QUESTIONS)]

    @model_validator(mode="after")
    def _validate(self) -> "EntBulkDeleteIn":
        if not self.question_ids:
            raise ValueError("Список вопросов пуст")
        return self


class EntBulkDeleteSkip(BaseModel):
    id: int
    reason: str


class EntBulkDeleteOut(BaseModel):
    deleted: list[int]
    failed: list[EntBulkDeleteSkip]
