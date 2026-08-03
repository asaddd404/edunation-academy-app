"""ent question / simulation language (ru, kk)

Added in three steps rather than one `nullable=False` column so the
migration is safe on a non-empty production table:

  1. add the column NULLABLE -- nothing to validate, no table rewrite that
     could fail halfway on existing rows;
  2. backfill every existing row to 'ru' -- the bank predates the split and
     is Russian by construction;
  3. only then set NOT NULL (plus a server default, so a client that
     doesn't know about the column still inserts a valid row).

The enum type is created explicitly with `checkfirst`, and the column type
carries `create_type=False`, so `add_column` can never try to CREATE TYPE a
second time.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_LANGUAGE = "ru"

language_enum = postgresql.ENUM("ru", "kk", name="ent_language", create_type=False)


def upgrade() -> None:
    language_enum.create(op.get_bind(), checkfirst=True)

    for table in ("ent_questions", "ent_simulations"):
        op.add_column(table, sa.Column("language", language_enum, nullable=True))
        op.execute(f"UPDATE {table} SET language = '{LEGACY_LANGUAGE}' WHERE language IS NULL")
        op.alter_column(table, "language", nullable=False, server_default=LEGACY_LANGUAGE)

    # Serves `subject_id = ? AND language = ?` and, for a quota-configured
    # subject, `... AND qtype = ?` -- i.e. exactly the queries a simulation
    # start runs, one per selected subject. A standalone index on `language`
    # would not be used: two values over the whole bank is not selective.
    op.create_index(
        "ix_ent_questions_subject_language",
        "ent_questions",
        ["subject_id", "language", "qtype"],
    )


def downgrade() -> None:
    op.drop_index("ix_ent_questions_subject_language", table_name="ent_questions")
    op.drop_column("ent_simulations", "language")
    op.drop_column("ent_questions", "language")
    language_enum.drop(op.get_bind(), checkfirst=True)
