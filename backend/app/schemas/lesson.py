from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.ent_question import EntQuestionType
from app.schemas.homework import HomeworkSubmissionOut
from app.schemas.limits import OptionalRichText, OptionalShortText, ShortText


class LessonIn(BaseModel):
    title: ShortText
    # Rich text: a serialized TipTap document, so the ceiling covers the JSON
    # envelope as well as the prose the teacher wrote.
    description: OptionalRichText = None
    video_url: OptionalShortText = None
    homework_assignment: OptionalRichText = None


class LessonUpdateIn(BaseModel):
    title: OptionalShortText = None
    description: OptionalRichText = None
    homework_assignment: OptionalRichText = None


class LessonTeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    section_id: int
    title: str
    description: str | None
    video_url: str | None
    homework_assignment: str | None
    order_index: int
    created_at: datetime
    video_status: str
    video_duration_seconds: int | None
    video_error: str | None


class LessonSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    order_index: int
    is_unlocked: bool = False
    is_passed: bool = False
    video_status: str = "none"
    # Filled in only by the teacher's course-builder listing, so a lesson's
    # readiness (video / questions / homework) is visible without expanding
    # every row. The student-facing paths leave the defaults, which costs
    # them nothing.
    question_count: int = 0
    has_homework: bool = False


class VideoTicketOut(BaseModel):
    playback_path: str


class LessonContentImageOut(BaseModel):
    """Relative upload path of a freshly stored rich-text image. The frontend
    writes this straight into the document's image node, so it must match
    what `app.core.rich_content` later looks for when hunting orphans."""

    path: str


class ChoiceOut(BaseModel):
    id: int
    text: str


class MatchItemOut(BaseModel):
    id: int
    text: str


class QuestionOut(BaseModel):
    """Student-facing view of a question -- never exposes which choice/pair
    is correct. Built manually (see content.build_student_question), not via
    model_validate, since matching requires shuffling the answer side."""

    id: int
    qtype: EntQuestionType
    text: str
    max_score: int
    order_index: int
    choices: list[ChoiceOut] = []
    match_prompts: list[MatchItemOut] = []
    match_answers: list[MatchItemOut] = []


class LessonDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    section_id: int
    title: str
    description: str | None
    video_url: str | None
    homework_assignment: str | None
    order_index: int
    created_at: datetime
    is_unlocked: bool = False
    is_passed: bool = False
    questions: list[QuestionOut] = []
    my_homework: HomeworkSubmissionOut | None = None
    video_status: str
    video_duration_seconds: int | None
