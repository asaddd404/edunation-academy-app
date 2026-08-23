"""drop an index 0015 added on top of an identical one

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-23

0015 added ix_ent_simulation_questions_simulation on
ent_simulation_questions(simulation_id). Migration 0004 had already created
ix_ent_simulation_questions_simulation_id on the same table and the same
column, so the two are byte-for-byte the same index under different names.

The mistake was reading the ORM models as the source of truth for which
indexes exist. They are not: 0002 and 0004 create indexes that no model
declares, so a table can be well indexed in the database while looking
bare in the code. The fix for that is in the model, alongside this.

A duplicate index is not free -- every insert and update maintains both --
so it goes. The older name stays, because 0004's downgrade references it.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_ent_simulation_questions_simulation")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ent_simulation_questions_simulation "
            "ON ent_simulation_questions (simulation_id)"
        )
