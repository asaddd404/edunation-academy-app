"""Trash: deleted lessons and sections are kept 30 days and can be restored

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The hidden course deleted sections and lessons are parked in.
    op.add_column("categories", sa.Column("is_trash", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "trash_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        # Where it came from. The course going away takes the record with it;
        # the sweep then removes whatever is left parked without a record.
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lesson_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('lesson', 'section')", name="ck_trash_items_kind"),
        sa.UniqueConstraint("kind", "object_id", name="uq_trash_items_object"),
    )
    op.create_index("ix_trash_items_category_id", "trash_items", ["category_id"])


def downgrade() -> None:
    # Anything still in the trash is lost on downgrade: it cannot be put
    # back without the records, so it is removed for real (FK cascades).
    op.execute(
        "DELETE FROM lessons WHERE section_id IN (SELECT s.id FROM sections s JOIN categories c ON c.id = s.category_id WHERE c.is_trash)"
    )
    op.execute("DELETE FROM sections WHERE category_id IN (SELECT id FROM categories WHERE is_trash)")
    op.execute("DELETE FROM categories WHERE is_trash")
    op.drop_index("ix_trash_items_category_id", table_name="trash_items")
    op.drop_table("trash_items")
    op.drop_column("categories", "is_trash")
