"""per-attempt question draws for lesson and section tests

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-21

A lesson or section test can now hold a bank larger than one attempt, and
each attempt draws its own selection (lessons/sections.questions_per_attempt,
NULL = every question, as before). For that the server has to remember what
an attempt drew, so an attempt is created when the test starts and graded
when it is submitted:

- test_attempts.question_ids  -- the drawn questions, in display order;
- test_attempts.submitted_at  -- NULL while in progress;
- test_attempts.score/passed  -- now nullable, NULL until submitted.

Every existing attempt was created on submit, so submitted_at is backfilled
from created_at.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lessons", sa.Column("questions_per_attempt", sa.Integer(), nullable=True))
    op.add_column("sections", sa.Column("questions_per_attempt", sa.Integer(), nullable=True))
    op.add_column("test_attempts", sa.Column("question_ids", postgresql.JSONB(), nullable=True))
    op.add_column("test_attempts", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE test_attempts SET submitted_at = created_at")
    op.alter_column("test_attempts", "score", existing_type=sa.Integer(), nullable=True)
    op.alter_column("test_attempts", "passed", existing_type=sa.Boolean(), nullable=True)


def downgrade() -> None:
    # In-progress attempts have no score to keep.
    op.execute("DELETE FROM test_attempts WHERE submitted_at IS NULL")
    op.alter_column("test_attempts", "passed", existing_type=sa.Boolean(), nullable=False)
    op.alter_column("test_attempts", "score", existing_type=sa.Integer(), nullable=False)
    op.drop_column("test_attempts", "submitted_at")
    op.drop_column("test_attempts", "question_ids")
    op.drop_column("sections", "questions_per_attempt")
    op.drop_column("lessons", "questions_per_attempt")
