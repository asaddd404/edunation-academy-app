"""Tests drawn from a question bank; ЕНТ questions archived instead of deleted

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL = every question in the bank, in the teacher's order (as before).
    op.add_column("lessons", sa.Column("questions_per_attempt", sa.Integer(), nullable=True))
    op.add_column("sections", sa.Column("questions_per_attempt", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_lessons_questions_per_attempt", "lessons", "questions_per_attempt IS NULL OR questions_per_attempt BETWEEN 1 AND 200")
    op.create_check_constraint("ck_sections_questions_per_attempt", "sections", "questions_per_attempt IS NULL OR questions_per_attempt BETWEEN 1 AND 200")
    # The questions one attempt was given, in display order. NULL for
    # attempts started before this column (they used the whole bank).
    op.add_column("test_attempts", sa.Column("question_ids", postgresql.JSONB(), nullable=True))
    # A question some attempt already drew is archived, not deleted, so past
    # results keep it. Archived questions leave the bank and new draws.
    op.add_column("ent_questions", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("ent_questions", "archived_at")
    op.drop_column("test_attempts", "question_ids")
    op.drop_constraint("ck_sections_questions_per_attempt", "sections", type_="check")
    op.drop_constraint("ck_lessons_questions_per_attempt", "lessons", type_="check")
    op.drop_column("sections", "questions_per_attempt")
    op.drop_column("lessons", "questions_per_attempt")
