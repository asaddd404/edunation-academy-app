from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EntSubject(Base):
    __tablename__ = "ent_subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Quota-based simulation structure: how many questions of each qtype a
    # generated simulation should draw from this subject. All 0 (the
    # default) means "unconfigured" -- start_simulation falls back to its
    # legacy flat questions_per_subject sampling for that subject.
    single_choice_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    multiple_choice_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matching_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    short_answer_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Nullable so the subject (and its question bank) survives if the
    # creating teacher's account is later removed.
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_by: Mapped["User | None"] = relationship()
    questions: Mapped[list["EntQuestion"]] = relationship(
        back_populates="subject", order_by="EntQuestion.order_index", cascade="all, delete-orphan"
    )
