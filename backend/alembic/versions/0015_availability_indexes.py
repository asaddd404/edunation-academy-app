"""indexes for the queries on the request path

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-23

Every index here backs a query that runs while a user waits and that had no
index at all, so each was a sequential scan over a table that only grows.
That is a denial-of-service vector rather than a performance nit: the cost of
issuing the request stays constant for the caller while the cost of serving
it rises with the data, so the same page that is fine today takes the site
down at ten times the rows.

Built CONCURRENTLY: a plain CREATE INDEX takes a lock that blocks writes to
the table for the duration, which on ent_simulation_questions would stall
every student mid-exam. That is also why each statement runs outside a
transaction -- Postgres refuses CONCURRENTLY inside one.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (name, table, columns) -- IF NOT EXISTS so a re-run after a failed
# CONCURRENTLY build (which leaves an invalid index behind) is not fatal.
INDEXES = [
    ("ix_ent_simulations_student_started", "ent_simulations", "student_id, started_at"),
    ("ix_ent_simulations_status_submitted", "ent_simulations", "status, submitted_at"),
    ("ix_ent_simulation_questions_simulation", "ent_simulation_questions", "simulation_id"),
    ("ix_student_ratings_total_xp", "student_ratings", "total_xp DESC"),
    ("ix_test_attempts_student_passed", "test_attempts", "student_id, passed"),
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, columns in INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({columns})")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _table, _columns in reversed(INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
