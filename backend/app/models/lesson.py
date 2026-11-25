import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VideoStatusEnum(str, enum.Enum):
    none = "none"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    homework_assignment: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video_status: Mapped[VideoStatusEnum] = mapped_column(
        Enum(VideoStatusEnum, name="video_status_enum", native_enum=True),
        default=VideoStatusEnum.none,
        server_default=VideoStatusEnum.none.value,
        nullable=False,
    )
    video_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # A PowerPoint file shown next to the video through Microsoft's Office
    # viewer (see app.core.presentation). The stored name is a fresh uuid per
    # upload, so a replaced file gets a new URL and the viewer's cache of the
    # old one is never shown again.
    presentation_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    presentation_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    presentation_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Settings of the auto-checked homework (models/homework_auto.py). All
    # optional: no opening date = open at once, no deadline = hand in any
    # time, no time limit = untimed, max_attempts None = unlimited,
    # tasks_per_student None = everyone gets every task.
    hw_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hw_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hw_time_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hw_max_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True, default=3, server_default="3")
    hw_tasks_per_student: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Mini-test: how many questions one attempt draws from the bank (NULL =
    # all of them, in the teacher's order).
    questions_per_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)

    section: Mapped["Section"] = relationship(back_populates="lessons")
    # See Section.lessons: nulling questions.lesson_id would break the
    # exactly-one-owner CHECK, so deletion is left to the FK cascade.
    questions: Mapped[list["Question"]] = relationship(
        back_populates="lesson", order_by="Question.order_index", cascade="all, delete-orphan", passive_deletes=True
    )
