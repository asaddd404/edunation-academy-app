from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.ent_question import EntQuestionType
from app.models.ent_simulation import EntSimulationStatus
from app.schemas.ent_question import EntAnswerVariantOut, EntChoiceTeacherOut, EntMatchPairTeacherOut


class EntSimulationStartIn(BaseModel):
    subject_ids: list[int]
    questions_per_subject: int = 10
    is_timed: bool
    duration_minutes: int | None = None

    @model_validator(mode="after")
    def _validate(self) -> "EntSimulationStartIn":
        if not self.subject_ids:
            raise ValueError("Выберите хотя бы один предмет")
        if not (1 <= self.questions_per_subject <= 50):
            raise ValueError("Количество вопросов на предмет должно быть от 1 до 50")
        if self.is_timed:
            if self.duration_minutes is None or not (1 <= self.duration_minutes <= 240):
                raise ValueError("Укажите время прохождения от 1 до 240 минут")
        elif self.duration_minutes is not None:
            raise ValueError("Время не указывается для прохождения без ограничения")
        return self


class EntMatchItemOut(BaseModel):
    id: int
    text: str


class EntChoiceOut(BaseModel):
    id: int
    text: str


class EntQuestionStudentOut(BaseModel):
    """Question as shown mid-attempt — never exposes which choice/pair is correct."""

    id: int
    subject_id: int
    subject_name: str
    qtype: EntQuestionType
    text: str
    max_score: int
    choices: list[EntChoiceOut] = []
    match_prompts: list[EntMatchItemOut] = []
    match_answers: list[EntMatchItemOut] = []


class EntSimulationOut(BaseModel):
    id: int
    is_timed: bool
    duration_minutes: int | None
    status: EntSimulationStatus
    started_at: datetime
    expires_at: datetime | None
    remaining_seconds: int | None = None
    questions: list[EntQuestionStudentOut] = []


class EntAnswerIn(BaseModel):
    question_id: int
    choice_id: int | None = None
    choice_ids: list[int] | None = None
    pairs: dict[str, int] | None = None
    text: str | None = None


class EntSimulationSubmitIn(BaseModel):
    answers: list[EntAnswerIn]


class EntSimulationResultAnswerOut(BaseModel):
    question_id: int
    subject_id: int
    subject_name: str
    qtype: EntQuestionType
    text: str
    max_score: int
    score_awarded: int
    is_correct: bool
    given_answer: dict | None
    choices: list[EntChoiceTeacherOut] = []
    match_pairs: list[EntMatchPairTeacherOut] = []
    answer_variants: list[EntAnswerVariantOut] = []


class EntSimulationResultOut(BaseModel):
    id: int
    is_timed: bool
    duration_minutes: int | None
    time_expired: bool
    status: EntSimulationStatus
    started_at: datetime
    submitted_at: datetime | None
    total_score: int
    max_score: int
    xp_earned: int
    answers: list[EntSimulationResultAnswerOut]


class EntSimulationSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_timed: bool
    duration_minutes: int | None
    time_expired: bool
    status: EntSimulationStatus
    started_at: datetime
    submitted_at: datetime | None
    total_score: int | None
    max_score: int | None
    xp_earned: int | None
