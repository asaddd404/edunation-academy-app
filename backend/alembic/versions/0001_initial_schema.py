"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

role_enum = sa.Enum("student", "teacher", "admin", name="role_enum")
application_status_enum = sa.Enum("pending", "approved", "rejected", name="application_status_enum")


def upgrade() -> None:
    # No explicit CREATE TYPE here: op.create_table() below creates each
    # embedded Enum column's type as part of the CREATE TABLE DDL. Doing it
    # twice collides -- the implicit creation triggered by create_table
    # doesn't check first for a type this migration already created.
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("role", role_enum, nullable=False, server_default="student"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_users_phone", "users", ["phone"])
    op.create_index("ix_users_phone", "users", ["phone"])

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_categories_slug", "categories", ["slug"])
    op.create_index("ix_categories_slug", "categories", ["slug"])

    op.create_table(
        "teacher_categories",
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", application_status_enum, nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Only one *pending* application per (student, category) at a time —
    # autogenerate can't produce partial indexes, so this is hand-written.
    op.create_index(
        "uq_pending_application_per_student_category",
        "applications",
        ["student_id", "category_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_pending_application_per_student_category", table_name="applications")
    op.drop_table("applications")
    op.drop_table("teacher_categories")
    op.drop_index("ix_categories_slug", table_name="categories")
    op.drop_constraint("uq_categories_slug", "categories", type_="unique")
    op.drop_table("categories")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_constraint("uq_users_phone", "users", type_="unique")
    op.drop_table("users")
    # Dropping "applications"/"users" above already drops their enum
    # columns' types as part of the DROP TABLE DDL.
