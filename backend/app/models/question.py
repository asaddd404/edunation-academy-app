from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Exactly one of lesson_id/section_id is set — a question belongs either
    # to a lesson's mini-test or to its section's end-of-module test, never
    # both. Kept as two nullable FKs (rather than a polymorphic owner_id)
    # so each still has a real, indexed foreign key.
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=True)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lesson: Mapped["Lesson | None"] = relationship(back_populates="questions")
    section: Mapped["Section | None"] = relationship(back_populates="test_questions")
    choices: Mapped[list["Choice"]] = relationship(back_populates="question", order_by="Choice.order_index")

    __table_args__ = (
        CheckConstraint(
            "(lesson_id IS NOT NULL AND section_id IS NULL) OR (lesson_id IS NULL AND section_id IS NOT NULL)",
            name="ck_question_exactly_one_owner",
        ),
    )


class Choice(Base):
    __tablename__ = "choices"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    question: Mapped["Question"] = relationship(back_populates="choices")
