"""ЕНТ: profile subjects, context questions, matching distractors

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-14

* ent_subjects.is_profile -- a profile subject's simulation always has the
  fixed 40-question ЕНТ structure (25 single, 5 context, 5 matching,
  5 multiple) instead of its configurable quotas.
* ent_question_type 'context' and ent_questions.context_text -- a
  single-choice question asked about a passage of text (questions 26-30).
* ent_match_pairs.prompt_text nullable -- a row with no prompt is a
  distractor: an extra answer on the right that pairs with nothing, so a
  matching question can offer more answers than it has prompts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allowed inside the migration's transaction on Postgres 12+, as long as
    # nothing in the same transaction uses the new value -- nothing here does.
    op.execute("ALTER TYPE ent_question_type ADD VALUE IF NOT EXISTS 'context'")
    op.add_column("ent_questions", sa.Column("context_text", sa.Text(), nullable=True))
    op.add_column(
        "ent_subjects", sa.Column("is_profile", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.alter_column("ent_match_pairs", "prompt_text", existing_type=sa.String(300), nullable=True)


def downgrade() -> None:
    # Distractors have no place in the old shape, and context questions turn
    # back into the single-choice questions they are underneath.
    op.execute("DELETE FROM ent_match_pairs WHERE prompt_text IS NULL")
    op.alter_column("ent_match_pairs", "prompt_text", existing_type=sa.String(300), nullable=False)
    op.drop_column("ent_subjects", "is_profile")
    op.execute("UPDATE ent_questions SET qtype = 'single' WHERE qtype = 'context'")
    op.drop_column("ent_questions", "context_text")
    # Postgres cannot drop an enum value; 'context' stays in the type, unused.
