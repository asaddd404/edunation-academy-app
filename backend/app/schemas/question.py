from pydantic import BaseModel, ConfigDict, model_validator

from app.models.ent_question import EntQuestionType
from app.schemas.limits import MediumText, QuestionText


class ChoiceIn(BaseModel):
    text: MediumText
    is_correct: bool = False


class MatchPairIn(BaseModel):
    prompt_text: MediumText
    answer_text: MediumText


class QuestionIn(BaseModel):
    qtype: EntQuestionType = EntQuestionType.single
    text: QuestionText
    max_score: int = 1
    choices: list[ChoiceIn] = []
    match_pairs: list[MatchPairIn] = []
    answer_variants: list[MediumText] = []

    @model_validator(mode="after")
    def _validate(self) -> "QuestionIn":
        if self.max_score not in (1, 2):
            raise ValueError("Баллы за вопрос — 1 или 2")

        if self.qtype == EntQuestionType.single:
            if not (2 <= len(self.choices) <= 6):
                raise ValueError("Вопрос с одним ответом должен содержать от 2 до 6 вариантов")
            if sum(1 for c in self.choices if c.is_correct) != 1:
                raise ValueError("Ровно один вариант ответа должен быть правильным")
            self._require_only(choices=True)
        elif self.qtype == EntQuestionType.multiple:
            if not (2 <= len(self.choices) <= 8):
                raise ValueError("Вопрос с несколькими ответами должен содержать от 2 до 8 вариантов")
            if sum(1 for c in self.choices if c.is_correct) < 2:
                raise ValueError("Минимум два варианта должны быть правильными")
            if self.max_score != 2:
                raise ValueError("Вопрос с несколькими ответами должен давать 2 балла (частичная защита)")
            self._require_only(choices=True)
        elif self.qtype == EntQuestionType.matching:
            if len(self.match_pairs) < 2:
                raise ValueError("Сопоставление должно содержать минимум 2 пары")
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


class ChoiceTeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    is_correct: bool
    order_index: int


class MatchPairTeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prompt_text: str
    answer_text: str
    order_index: int


class AnswerVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str


class QuestionTeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lesson_id: int | None
    section_id: int | None
    qtype: EntQuestionType
    text: str
    max_score: int
    order_index: int
    choices: list[ChoiceTeacherOut] = []
    match_pairs: list[MatchPairTeacherOut] = []
    answer_variants: list[AnswerVariantOut] = []
