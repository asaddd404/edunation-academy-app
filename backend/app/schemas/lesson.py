from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.homework import HomeworkSubmissionOut


class LessonIn(BaseModel):
    title: str
    description: str | None = None
    video_url: str | None = None
    homework_assignment: str | None = None


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


class VideoTicketOut(BaseModel):
    playback_path: str


class ChoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    order_index: int
    choices: list[ChoiceOut]


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
