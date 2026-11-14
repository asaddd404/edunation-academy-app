"""Lesson presentation: a PowerPoint file shown next to the video

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lessons", sa.Column("presentation_path", sa.String(length=255), nullable=True))
    op.add_column("lessons", sa.Column("presentation_name", sa.String(length=255), nullable=True))
    op.add_column("lessons", sa.Column("presentation_size", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("lessons", "presentation_size")
    op.drop_column("lessons", "presentation_name")
    op.drop_column("lessons", "presentation_path")
