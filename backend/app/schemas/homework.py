from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.homework import HomeworkStatusEnum
from app.schemas.limits import OptionalMediumText


class HomeworkReviewIn(BaseModel):
    status: HomeworkStatusEnum
    feedback: OptionalMediumText = None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: HomeworkStatusEnum) -> HomeworkStatusEnum:
        if v == HomeworkStatusEnum.submitted:
            raise ValueError("Статус решения должен быть accepted или revision_requested")
        return v


class HomeworkSubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lesson_id: int
    student_id: int
    text_answer: str | None
    file_original_name: str | None
    status: HomeworkStatusEnum
    teacher_feedback: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    student_name: str | None = None
    lesson_title: str | None = None
