"""ent subject qtype quotas

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ent_subjects", sa.Column("single_choice_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "ent_subjects", sa.Column("multiple_choice_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("ent_subjects", sa.Column("matching_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "ent_subjects", sa.Column("short_answer_count", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    op.drop_column("ent_subjects", "short_answer_count")
    op.drop_column("ent_subjects", "matching_count")
    op.drop_column("ent_subjects", "multiple_choice_count")
    op.drop_column("ent_subjects", "single_choice_count")
