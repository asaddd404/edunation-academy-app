from datetime import datetime, timedelta

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.config import settings
from app.models.homework import HomeworkStatusEnum
from app.schemas.limits import OptionalMediumText


PREVIEWABLE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def file_kind(name: str | None) -> Literal["image", "pdf", "document"] | None:
    """How the review screen can show an attachment: images and PDFs are
    previewed in the page, anything else (.docx, .txt) is download-only."""
    if not name:
        return None
    extension = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension in PREVIEWABLE_IMAGE_EXTENSIONS:
        return "image"
    if extension == ".pdf":
        return "pdf"
    return "document"


class HomeworkReviewIn(BaseModel):
    status: HomeworkStatusEnum
    feedback: OptionalMediumText = None
    grade: int | None = Field(default=None, ge=0, le=100)

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
    # Read from the row to derive the fields below; never sent to clients.
    file_path: str | None = Field(default=None, exclude=True)
    file_deleted_at: datetime | None = None
    status: HomeworkStatusEnum
    teacher_feedback: str | None
    grade: int | None = None
    reviewed_at: datetime | None
    created_at: datetime
    submitted_at: datetime
    updated_at: datetime
    student_name: str | None = None
    student_phone: str | None = None
    lesson_title: str | None = None
    category_id: int | None = None
    category_name: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def file_kind(self) -> Literal["image", "pdf", "document"] | None:
        return None if self.file_deleted else file_kind(self.file_original_name)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def file_deleted(self) -> bool:
        """Removed by the retention policy (app/core/retention.py)."""
        return self.file_deleted_at is not None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def file_retention_days(self) -> int:
        """How long after review attachments are kept -- for the warning on
        the review screen, so it cannot drift from the server's setting."""
        return settings.homework_file_retention_days

    @computed_field  # type: ignore[prop-decorator]
    @property
    def file_expires_at(self) -> datetime | None:
        """When the attachment of reviewed work will be deleted."""
        if self.file_path is None or self.status == HomeworkStatusEnum.submitted or self.reviewed_at is None:
            return None
        return self.reviewed_at + timedelta(days=settings.homework_file_retention_days)
