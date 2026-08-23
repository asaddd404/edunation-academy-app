from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TestAttempt(Base):
    __tablename__ = "test_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Same lesson_id/section_id discriminator as Question — a mini-test
    # attempt or a section-test attempt, never both.
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["User"] = relationship()
    lesson: Mapped["Lesson | None"] = relationship()
    section: Mapped["Section | None"] = relationship()

    __table_args__ = (
        CheckConstraint(
            "(lesson_id IS NOT NULL AND section_id IS NULL) OR (lesson_id IS NULL AND section_id IS NOT NULL)",
            name="ck_test_attempt_exactly_one_scope",
        ),
        # Every lesson page computes the student's progress from their own
        # attempts (see core.progress). Filtered by student_id and passed,
        # on a table that only ever grows.
        Index("ix_test_attempts_student_passed", "student_id", "passed"),
    )
