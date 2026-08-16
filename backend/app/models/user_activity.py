from datetime import date as date_

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserDailyActivity(Base):
    """One row per user per calendar day, incremented 60s at a time by
    `POST /activity/ping` while the client tab is visible. The server owns
    the increment (not client-supplied), so a stuck/buggy tab can't inflate
    it beyond real elapsed time."""

    __tablename__ = "user_daily_activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    total_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_daily_activity_user_date"),)
