"""per-user daily active-time tracking

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_daily_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("total_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "date", name="uq_user_daily_activity_user_date"),
    )


def downgrade() -> None:
    op.drop_table("user_daily_activity")
