"""section-level tests

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id", ondelete="CASCADE"), nullable=True))
    op.alter_column("questions", "lesson_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("ix_questions_section_id", "questions", ["section_id"])
    op.create_check_constraint(
        "ck_question_exactly_one_owner",
        "questions",
        "(lesson_id IS NOT NULL AND section_id IS NULL) OR (lesson_id IS NULL AND section_id IS NOT NULL)",
    )

    op.add_column("test_attempts", sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id", ondelete="CASCADE"), nullable=True))
    op.alter_column("test_attempts", "lesson_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("ix_test_attempts_student_section", "test_attempts", ["student_id", "section_id"])
    op.create_check_constraint(
        "ck_test_attempt_exactly_one_scope",
        "test_attempts",
        "(lesson_id IS NOT NULL AND section_id IS NULL) OR (lesson_id IS NULL AND section_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_test_attempt_exactly_one_scope", "test_attempts", type_="check")
    op.drop_index("ix_test_attempts_student_section", table_name="test_attempts")
    op.alter_column("test_attempts", "lesson_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("test_attempts", "section_id")

    op.drop_constraint("ck_question_exactly_one_owner", "questions", type_="check")
    op.drop_index("ix_questions_section_id", table_name="questions")
    op.alter_column("questions", "lesson_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("questions", "section_id")
