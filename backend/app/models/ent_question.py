import enum
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EntQuestionType(str, enum.Enum):
    single = "single"
    multiple = "multiple"
    matching = "matching"
    short_answer = "short_answer"


class EntLanguage(str, enum.Enum):
    """Language a question is written in — the ЕНТ is sat in one or the other,
    never both, so this is what a simulation filters the bank by.

    A native Postgres enum rather than a plain string: the value is only ever
    read back in a `WHERE` clause, so a typo ('RU', 'kz') would not fail
    anywhere — it would silently make the question invisible to every
    simulation.
    """

    ru = "ru"
    kk = "kk"


class EntQuestion(Base):
    __tablename__ = "ent_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("ent_subjects.id", ondelete="CASCADE"), nullable=False)
    qtype: Mapped[EntQuestionType] = mapped_column(
        Enum(EntQuestionType, name="ent_question_type", native_enum=True), nullable=False
    )
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Russian unless the import (or the teacher) says otherwise: the whole bank
    # predates this column, and 0013 backfills it to the same value.
    language: Mapped[EntLanguage] = mapped_column(
        Enum(EntLanguage, name="ent_language", native_enum=True),
        nullable=False,
        default=EntLanguage.ru,
        server_default=EntLanguage.ru.value,
    )
    # Optional illustration (graph, diagram, map, formula screenshot) -- some
    # ЕНТ questions are unanswerable without one.
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subject: Mapped["EntSubject"] = relationship(back_populates="questions")
    created_by: Mapped["User | None"] = relationship()
    choices: Mapped[list["EntChoice"]] = relationship(
        back_populates="question", order_by="EntChoice.order_index", cascade="all, delete-orphan"
    )
    match_pairs: Mapped[list["EntMatchPair"]] = relationship(
        back_populates="question", order_by="EntMatchPair.order_index", cascade="all, delete-orphan"
    )
    answer_variants: Mapped[list["EntAnswerVariant"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("max_score IN (1, 2)", name="ck_ent_question_max_score"),
        # Every simulation start filters by subject *and* language (and, for a
        # quota-configured subject, by qtype on top). Composite rather than a
        # lone index on `language`, which has two values and would be ignored
        # by the planner on its own; leading with subject_id keeps the same
        # index serving the subject-only queries the bank screen makes.
        Index("ix_ent_questions_subject_language", "subject_id", "language", "qtype"),
    )

    @property
    def has_image(self) -> bool:
        return self.image_path is not None


class EntChoice(Base):
    """Options for qtype in (single, multiple)."""

    __tablename__ = "ent_choices"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("ent_questions.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    question: Mapped["EntQuestion"] = relationship(back_populates="choices")


class EntMatchPair(Base):
    """Correct prompt/answer pairs for qtype == matching. Each row already
    encodes its own correct pairing; the frontend shuffles answer_text
    across a question's pairs when rendering, and the student's submission
    references pair ids, not text, so grading never touches free text."""

    __tablename__ = "ent_match_pairs"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("ent_questions.id", ondelete="CASCADE"), nullable=False)
    prompt_text: Mapped[str] = mapped_column(String(300), nullable=False)
    answer_text: Mapped[str] = mapped_column(String(300), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    question: Mapped["EntQuestion"] = relationship(back_populates="match_pairs")


class EntAnswerVariant(Base):
    """Accepted text answers for qtype == short_answer (allows alternate
    spellings/synonyms to all count as correct)."""

    __tablename__ = "ent_answer_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("ent_questions.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)

    question: Mapped["EntQuestion"] = relationship(back_populates="answer_variants")
