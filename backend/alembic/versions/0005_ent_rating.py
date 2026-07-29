"""ent rating: xp on simulations + student_ratings leaderboard aggregate

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ent_simulations", sa.Column("xp_earned", sa.Integer(), nullable=True))

    op.create_table(
        "student_ratings",
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("total_xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("simulations_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_score", sa.Integer(), nullable=True),
        sa.Column("last_simulation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_student_ratings_total_xp", "student_ratings", ["total_xp"])


def downgrade() -> None:
    op.drop_index("ix_student_ratings_total_xp", table_name="student_ratings")
    op.drop_table("student_ratings")

    op.drop_column("ent_simulations", "xp_earned")
