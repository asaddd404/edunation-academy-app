"""lessons, tests, homework

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

homework_status_enum = sa.Enum("submitted", "accepted", "revision_requested", name="homework_status_enum")


def upgrade() -> None:
    # No explicit CREATE TYPE: op.create_table() below creates it as part of
    # the "homework_submissions" table's DDL (see 0001 for why a separate
    # explicit create collides with that).
    op.create_table(
        "sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sections_category_id", "sections", ["category_id"])

    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("video_url", sa.String(length=500), nullable=True),
        sa.Column("homework_assignment", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_lessons_section_id", "lessons", ["section_id"])

    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_questions_lesson_id", "questions", ["lesson_id"])

    op.create_table(
        "choices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_choices_question_id", "choices", ["question_id"])

    op.create_table(
        "test_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_test_attempts_student_lesson", "test_attempts", ["student_id", "lesson_id"])

    op.create_table(
        "homework_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text_answer", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("file_original_name", sa.String(length=255), nullable=True),
        sa.Column("status", homework_status_enum, nullable=False, server_default="submitted"),
        sa.Column("teacher_feedback", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "uq_homework_submission_student_lesson",
        "homework_submissions",
        ["student_id", "lesson_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("homework_submissions")
    op.drop_index("ix_test_attempts_student_lesson", table_name="test_attempts")
    op.drop_table("test_attempts")
    op.drop_index("ix_choices_question_id", table_name="choices")
    op.drop_table("choices")
    op.drop_index("ix_questions_lesson_id", table_name="questions")
    op.drop_table("questions")
    op.drop_index("ix_lessons_section_id", table_name="lessons")
    op.drop_table("lessons")
    op.drop_index("ix_sections_category_id", table_name="sections")
    op.drop_table("sections")
    # "homework_submissions" was already dropped above, taking its enum
    # column's type with it.
