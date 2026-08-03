import enum
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.ent_question import EntLanguage


class EntSimulationStatus(str, enum.Enum):
    in_progress = "in_progress"
    submitted = "submitted"


class EntSimulation(Base):
    __tablename__ = "ent_simulations"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_timed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The language the attempt was sat in. Every question drawn into it is in
    # this language today, but it is stored on the attempt as well: reporting
    # ("how do our Kazakh-stream students do?") must not have to infer the
    # answer by joining out to the questions, and a future mixed-language
    # attempt would make that inference wrong.
    language: Mapped[EntLanguage] = mapped_column(
        Enum(EntLanguage, name="ent_language", native_enum=True),
        nullable=False,
        default=EntLanguage.ru,
        server_default=EntLanguage.ru.value,
    )
    status: Mapped[EntSimulationStatus] = mapped_column(
        Enum(EntSimulationStatus, name="ent_simulation_status", native_enum=True),
        default=EntSimulationStatus.in_progress,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when the student submitted a timed simulation after expires_at —
    # the attempt is still graded, but flagged as run over time.
    time_expired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Frozen at submit time by core.rating.apply_simulation_xp — kept on the
    # attempt itself (not recomputed) so a later change to the XP formula
    # never rewrites what a past attempt actually earned.
    xp_earned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["User"] = relationship()
    items: Mapped[list["EntSimulationQuestion"]] = relationship(
        back_populates="simulation", order_by="EntSimulationQuestion.order_index", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "(is_timed = false AND duration_minutes IS NULL) OR (is_timed = true AND duration_minutes IS NOT NULL)",
            name="ck_ent_simulation_duration",
        ),
    )


class EntSimulationQuestion(Base):
    """One question drawn into a simulation attempt. Doubles as the answer
    record — answer_data/score_awarded start NULL and are filled in once,
    at submit time, matching the existing single-shot test-attempt flow."""

    __tablename__ = "ent_simulation_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("ent_simulations.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("ent_questions.id", ondelete="CASCADE"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answer_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    score_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)

    simulation: Mapped["EntSimulation"] = relationship(back_populates="items")
    question: Mapped["EntQuestion"] = relationship()
