from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StudentRating(Base):
    """One row per student — a running aggregate kept in sync by
    core.rating.apply_simulation_xp each time an ЕНТ simulation is
    submitted, so the leaderboard never has to re-sum every attempt."""

    __tablename__ = "student_ratings"

    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    total_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    simulations_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_simulation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["User"] = relationship()
