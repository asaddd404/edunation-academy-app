from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrashItem(Base):
    """A deleted lesson or section, parked for 30 days. The row itself stays
    where it is in the database (moved into the hidden trash course), so
    restoring brings back its video, tests, homework and every student's
    results as they were. This record remembers where it came from."""

    __tablename__ = "trash_items"
    __table_args__ = (
        CheckConstraint("kind IN ('lesson', 'section')", name="ck_trash_items_kind"),
        UniqueConstraint("kind", "object_id", name="uq_trash_items_object"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    object_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True)
    section_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    lesson_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
