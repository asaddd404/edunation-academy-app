"""lesson video processing fields

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

video_status_enum = sa.Enum("none", "processing", "ready", "failed", name="video_status_enum")


def upgrade() -> None:
    video_status_enum.create(op.get_bind())
    op.add_column(
        "lessons",
        sa.Column("video_status", video_status_enum, nullable=False, server_default="none"),
    )
    op.add_column("lessons", sa.Column("video_duration_seconds", sa.Integer(), nullable=True))
    op.add_column("lessons", sa.Column("video_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lessons", "video_error")
    op.drop_column("lessons", "video_duration_seconds")
    op.drop_column("lessons", "video_status")
    video_status_enum.drop(op.get_bind())
