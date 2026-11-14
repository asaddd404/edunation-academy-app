from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.ent_question import EntQuestionType

from app.schemas.limits import CatalogName, OptionalCatalogName, OptionalSlug


class EntSubjectIn(BaseModel):
    name: CatalogName
    slug: OptionalSlug = None


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
    name: OptionalCatalogName = None
    is_active: bool | None = None
    is_profile: bool | None = None
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
    is_profile: bool = False
    created_at: datetime
    question_count: int = 0
    single_choice_count: int = 0
    multiple_choice_count: int = 0
    matching_count: int = 0
    short_answer_count: int = 0
    ru_count: int = 0
    kk_count: int = 0


class EntStructureBlockOut(BaseModel):
    """One block of a simulation: `needed` questions of `qtype`. `have` and
    `off_format` are per language ("ru", "kk")."""

    qtype: EntQuestionType
    # Question numbers in the attempt (profile subjects only: 1-25, 26-30, ...).
    first_number: int | None = None
    last_number: int | None = None
    needed: int
    # Questions a simulation can draw for this block.
    have: dict[str, int]
    # Same type, but not in the profile format -- never drawn.
    off_format: dict[str, int]


class EntSubjectStructureOut(BaseModel):
    is_profile: bool
    blocks: list[EntStructureBlockOut]
    # Questions of a type the structure does not use at all.
    unused: dict[str, int]
