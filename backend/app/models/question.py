from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.ent_question import EntQuestionType


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Exactly one of lesson_id/section_id is set — a question belongs either
    # to a lesson's mini-test or to its section's end-of-module test, never
    # both. Kept as two nullable FKs (rather than a polymorphic owner_id)
    # so each still has a real, indexed foreign key.
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=True)
    # Reuses the ent_question_type enum: both models share the exact same
    # qtype/max_score/choices/match_pairs/answer_variants shape and grading
    # rules (see app.core.question_scoring), so one enum serves both.
    qtype: Mapped[EntQuestionType] = mapped_column(
        Enum(EntQuestionType, name="ent_question_type", native_enum=True, create_type=False),
        nullable=False,
        default=EntQuestionType.single,
        server_default=EntQuestionType.single.value,
    )
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lesson: Mapped["Lesson | None"] = relationship(back_populates="questions")
    section: Mapped["Section | None"] = relationship(back_populates="test_questions")
    choices: Mapped[list["Choice"]] = relationship(
        back_populates="question", order_by="Choice.order_index", cascade="all, delete-orphan"
    )
    match_pairs: Mapped[list["MatchPair"]] = relationship(
        back_populates="question", order_by="MatchPair.order_index", cascade="all, delete-orphan"
    )
    answer_variants: Mapped[list["AnswerVariant"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "(lesson_id IS NOT NULL AND section_id IS NULL) OR (lesson_id IS NULL AND section_id IS NOT NULL)",
            name="ck_question_exactly_one_owner",
        ),
        CheckConstraint("max_score IN (1, 2)", name="ck_question_max_score"),
    )


class Choice(Base):
    __tablename__ = "choices"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    question: Mapped["Question"] = relationship(back_populates="choices")


class MatchPair(Base):
    """Correct prompt/answer pairs for qtype == matching. See EntMatchPair
    for the pairing/grading convention this mirrors."""

    __tablename__ = "match_pairs"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    prompt_text: Mapped[str] = mapped_column(String(300), nullable=False)
    answer_text: Mapped[str] = mapped_column(String(300), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    question: Mapped["Question"] = relationship(back_populates="match_pairs")


class AnswerVariant(Base):
    """Accepted text answers for qtype == short_answer."""

    __tablename__ = "answer_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)

    question: Mapped["Question"] = relationship(back_populates="answer_variants")
