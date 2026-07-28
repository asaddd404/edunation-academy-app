import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HomeworkStatusEnum(str, enum.Enum):
    submitted = "submitted"
    accepted = "accepted"
    revision_requested = "revision_requested"


class HomeworkSubmission(Base):
    __tablename__ = "homework_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    text_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[HomeworkStatusEnum] = mapped_column(
        Enum(HomeworkStatusEnum, name="homework_status_enum", native_enum=True),
        default=HomeworkStatusEnum.submitted,
        nullable=False,
    )
    teacher_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lesson: Mapped["Lesson"] = relationship()
    student: Mapped["User"] = relationship(foreign_keys=[student_id])
    reviewer: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by])

    __table_args__ = (Index("uq_homework_submission_student_lesson", "student_id", "lesson_id", unique=True),)
