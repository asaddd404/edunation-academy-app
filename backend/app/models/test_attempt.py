import enum
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TestAttemptStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"


class TestAttempt(Base):
    """A sitting of a lesson mini-test or a section test.

    Created by `start` (which fixes `started_at` and is the scope the
    matching-answer tokens are minted for), finished once by `submit`. The
    result columns are NULL until then, which is also why the progress
    queries -- filtering on `passed IS TRUE` -- never count an open attempt.
    """

    __tablename__ = "test_attempts"
    # Keeps pytest from mistaking this class for a test case.
    __test__ = False

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Same lesson_id/section_id discriminator as Question — a mini-test
    # attempt or a section-test attempt, never both.
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=True)
    status: Mapped[TestAttemptStatus] = mapped_column(
        Enum(TestAttemptStatus, name="test_attempt_status", native_enum=True),
        nullable=False,
        default=TestAttemptStatus.in_progress,
        server_default=TestAttemptStatus.in_progress.value,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Percentage of points earned, 0-100.
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    earned_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Questions answered for full credit, out of question_count.
    correct_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # What this attempt actually added to the student's XP -- frozen at
    # submit, like EntSimulation.xp_earned, so a later formula change never
    # rewrites history. Zero for a retake that did not beat the best result.
    xp_earned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # {question_id: answer_data}, stored with matching answers already
    # translated from tokens back to row ids.
    answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["User"] = relationship()
    lesson: Mapped["Lesson | None"] = relationship()
    section: Mapped["Section | None"] = relationship()

    __table_args__ = (
        CheckConstraint(
            "(lesson_id IS NOT NULL AND section_id IS NULL) OR (lesson_id IS NULL AND section_id IS NOT NULL)",
            name="ck_test_attempt_exactly_one_scope",
        ),
        CheckConstraint(
            "status = 'in_progress' OR (score IS NOT NULL AND passed IS NOT NULL AND submitted_at IS NOT NULL)",
            name="ck_test_attempt_completed_has_result",
        ),
        # Every lesson page computes the student's progress from their own
        # attempts (see core.progress). Filtered by student_id and passed,
        # on a table that only ever grows.
        Index("ix_test_attempts_student_passed", "student_id", "passed"),
        # Created by migrations 0002/0003 and declared here so the models stay
        # an honest inventory of what exists (see 0016).
        Index("ix_test_attempts_student_lesson", "student_id", "lesson_id"),
        Index("ix_test_attempts_student_section", "student_id", "section_id"),
        # Per-lesson / per-section leaderboards read every finished attempt
        # of one test, across students.
        Index("ix_test_attempts_lesson_status", "lesson_id", "status"),
        Index("ix_test_attempts_section_status", "section_id", "status"),
        # At most one open attempt per student per test, so two racing
        # `start` calls cannot leave a second session behind.
        Index(
            "uq_test_attempts_open_lesson",
            "student_id",
            "lesson_id",
            unique=True,
            postgresql_where=text("status = 'in_progress' AND lesson_id IS NOT NULL"),
            sqlite_where=text("status = 'in_progress' AND lesson_id IS NOT NULL"),
        ),
        Index(
            "uq_test_attempts_open_section",
            "student_id",
            "section_id",
            unique=True,
            postgresql_where=text("status = 'in_progress' AND section_id IS NOT NULL"),
            sqlite_where=text("status = 'in_progress' AND section_id IS NOT NULL"),
        ),
    )
