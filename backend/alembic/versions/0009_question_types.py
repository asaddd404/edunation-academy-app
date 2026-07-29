"""rich question types for lesson/section tests

Reuses the ent_question_type enum (created in 0004) for the course
questions table too -- both share the same qtype/max_score/choices/
match_pairs/answer_variants shape and grading rules.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False: this enum already exists (migration 0004) -- never
# let add_column try to (re)create it.
question_type_enum = sa.Enum(
    "single", "multiple", "matching", "short_answer", name="ent_question_type", create_type=False
)


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("qtype", question_type_enum, nullable=False, server_default="single"),
    )
    op.add_column("questions", sa.Column("max_score", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_question_max_score", "questions", "max_score IN (1, 2)")

    op.create_table(
        "match_pairs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prompt_text", sa.String(length=300), nullable=False),
        sa.Column("answer_text", sa.String(length=300), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_match_pairs_question_id", "match_pairs", ["question_id"])

    op.create_table(
        "answer_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.String(length=300), nullable=False),
    )
    op.create_index("ix_answer_variants_question_id", "answer_variants", ["question_id"])


def downgrade() -> None:
    op.drop_index("ix_answer_variants_question_id", table_name="answer_variants")
    op.drop_table("answer_variants")
    op.drop_index("ix_match_pairs_question_id", table_name="match_pairs")
    op.drop_table("match_pairs")

    op.drop_constraint("ck_question_max_score", "questions", type_="check")
    op.drop_column("questions", "max_score")
    op.drop_column("questions", "qtype")
