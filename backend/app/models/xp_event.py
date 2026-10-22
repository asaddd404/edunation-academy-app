import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class XpSource(str, enum.Enum):
    ent = "ent"
    lesson_test = "lesson_test"
    section_test = "section_test"


class XpEvent(Base):
    """One XP award -- the ledger every leaderboard is summed from.

    `source_id` is the id of the thing that earned it: an ent_simulations
    row for `ent`, a test_attempts row for the two course-test sources. The
    unique key on (source, source_id) is what makes an award idempotent: a
    second attempt to credit the same simulation or attempt -- a retried
    request, a double-click that got past the row lock -- hits the
    constraint instead of the student's total.

    `student_ratings.total_xp` is the running sum of this table per student,
    kept so the all-time board never has to re-aggregate it.
    """

    __tablename__ = "xp_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # A plain string under a CHECK rather than a native enum: a new source is
    # then one constraint swap, not an ALTER TYPE that cannot run inside a
    # transaction on older Postgres.
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["User"] = relationship()

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_xp_events_source"),
        CheckConstraint("source IN ('ent', 'lesson_test', 'section_test')", name="ck_xp_events_source"),
        CheckConstraint("xp >= 0", name="ck_xp_events_xp_non_negative"),
        # The week/month boards aggregate everything since a cutoff.
        Index("ix_xp_events_created_at", "created_at"),
        Index("ix_xp_events_student_id", "student_id"),
    )
