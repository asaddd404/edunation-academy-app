"""Auto-checked homework built from tasks (see app.core.homework_tasks).

Lives beside the older free-form homework (models/homework.py: one text/file
submission graded by hand), which stays as it is for lessons that use it.

- HomeworkTask: one task of a lesson's homework, as the teacher wrote it,
  answer key included. Never sent to a student as is.
- HomeworkAttempt: one sitting. Fixes which tasks the student got and in what
  arrangement, collects answers, and is graded once on submit.
- HomeworkRecord: one row per (lesson, student) for everything that outlives
  a single attempt -- the student's variant, a personal deadline extension,
  the teacher's grades for essay/file tasks and any decision on the work.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

HOMEWORK_TASK_TYPES = ("gaps", "single", "multi", "short", "match", "tf", "order", "essay", "file")


class HomeworkTask(Base):
    __tablename__ = "homework_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # Type-specific content and answer key, validated by
    # app.core.homework_tasks.normalize_task before it is ever stored.
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "type IN (" + ", ".join(f"'{t}'" for t in HOMEWORK_TASK_TYPES) + ")",
            name="ck_homework_task_type",
        ),
        # An essay's points are the sum of up to ten criteria, so the ceiling
        # is above a single task's 100.
        CheckConstraint("points BETWEEN 1 AND 1000", name="ck_homework_task_points"),
    )


class HomeworkAttempt(Base):
    __tablename__ = "homework_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="in_progress", server_default="in_progress")
    # The tasks this sitting shows, in order, and how each was arranged
    # (option order, shuffled right-hand sides) -- fixed at start.
    task_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    layout: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {task_id: answer}, cleaned per type. Autosaved during the attempt, so a
    # sitting that runs out of time is graded on what was saved in time.
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # None: no time limit and no deadline to stop at.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Filled on submit. auto_*: the instantly graded tasks; manual_max: what
    # the teacher's essay/file tasks are worth.
    auto_earned: Mapped[float | None] = mapped_column(Float, nullable=True)
    auto_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    manual_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    # {task_id: {"earned", "max", "items": [...]}} -- per-task verdicts for
    # the review, the class's problem spots and the copy signals.
    results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # How many times the page lost focus during the sitting (another tab or
    # app). Only a hint for the teacher, never a penalty.
    away_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('in_progress', 'submitted')", name="ck_homework_attempt_status"),
        Index("ix_homework_attempts_lesson_student", "lesson_id", "student_id"),
        # One open sitting per student per lesson: two racing "start" calls
        # can't leave a second one behind.
        Index(
            "uq_homework_attempts_open",
            "lesson_id",
            "student_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
            sqlite_where=text("status = 'in_progress'"),
        ),
    )


class HomeworkRecord(Base):
    __tablename__ = "homework_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # The student's own subset of tasks when the teacher gives each student
    # a variant. Drawn once and kept across attempts.
    variant_task_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # A "retake" from the teacher: attempts submitted before this moment no
    # longer count (for the attempt limit or the best result), and the
    # student gets a freshly drawn variant. The previous values are kept so
    # the decision can be undone until the student starts again.
    attempts_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_variant: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    extended_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # {task_id: {"earned", "criteria": [ids], "attempt_id"}} for essay/file tasks.
    manual_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # The teacher's final word, when they used one: a grade (0 = annulled)
    # that replaces the computed one, with an optional note to the student.
    override_grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    teacher_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("lesson_id", "student_id", name="uq_homework_record_lesson_student"),
        CheckConstraint("override_grade IS NULL OR override_grade BETWEEN 0 AND 100", name="ck_homework_record_grade"),
        CheckConstraint("decision IS NULL OR decision IN ('keep', 'zero', 'edit', 'retake')", name="ck_homework_record_decision"),
    )


__all__ = ["HomeworkAttempt", "HomeworkRecord", "HomeworkTask", "HOMEWORK_TASK_TYPES"]
