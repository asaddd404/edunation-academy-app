from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class EntSubjectIn(BaseModel):
    name: str
    slug: str | None = None


class EntSubjectQuotasIn(BaseModel):
    """Per-qtype question counts for a generated simulation. All 0 means
    "unconfigured" -- start_simulation then falls back to its legacy flat
    questions_per_subject sampling for that subject."""

    single_choice_count: int = 0
    multiple_choice_count: int = 0
    matching_count: int = 0
    short_answer_count: int = 0

    @model_validator(mode="after")
    def _validate(self) -> "EntSubjectQuotasIn":
        for value in (
            self.single_choice_count,
            self.multiple_choice_count,
            self.matching_count,
            self.short_answer_count,
        ):
            if not (0 <= value <= 100):
                raise ValueError("Количество вопросов по типу должно быть от 0 до 100")
        return self


class EntSubjectUpdateIn(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    single_choice_count: int | None = None
    multiple_choice_count: int | None = None
    matching_count: int | None = None
    short_answer_count: int | None = None

    @model_validator(mode="after")
    def _validate(self) -> "EntSubjectUpdateIn":
        for value in (
            self.single_choice_count,
            self.multiple_choice_count,
            self.matching_count,
            self.short_answer_count,
        ):
            if value is not None and not (0 <= value <= 100):
                raise ValueError("Количество вопросов по типу должно быть от 0 до 100")
        return self


class EntSubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    question_count: int = 0
    single_choice_count: int = 0
    multiple_choice_count: int = 0
    matching_count: int = 0
    short_answer_count: int = 0
    ru_count: int = 0
    kk_count: int = 0
