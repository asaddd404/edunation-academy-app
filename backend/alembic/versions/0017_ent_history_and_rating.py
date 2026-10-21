"""keep ЕНТ history intact; rank the leaderboard by best rated score

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-21

Two changes that only make sense together.

ent_questions.archived_at -- deleting or editing a question that an attempt
had drawn used to rewrite that attempt: a delete cascaded the attempt's rows
away, and an edit replaced the choices, so stored answers pointed at ids that
no longer existed. Such questions are now archived (and an edit creates a new
row), so history is never touched.

ent_simulations.counts_for_rating -- the leaderboard now ranks by the best
score of a timed attempt finished within its limit, instead of the sum of XP
over every attempt (which rewarded volume, not results). Backfilled from the
attempts themselves with the same 60-second grace the API applies, and
student_ratings.best_score is recomputed to mean "best rated score".
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ent_questions", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "ent_simulations",
        sa.Column("counts_for_rating", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE ent_simulations
           SET counts_for_rating = true
         WHERE status = 'submitted'
           AND is_timed
           AND expires_at IS NOT NULL
           AND submitted_at <= expires_at + interval '60 seconds'
        """
    )
    op.execute(
        """
        UPDATE student_ratings r
           SET best_score = (
               SELECT max(s.total_score)
                 FROM ent_simulations s
                WHERE s.student_id = r.student_id
                  AND s.counts_for_rating
           )
        """
    )


def downgrade() -> None:
    # best_score goes back to "best of any submitted attempt", its old meaning.
    op.execute(
        """
        UPDATE student_ratings r
           SET best_score = (
               SELECT max(s.total_score)
                 FROM ent_simulations s
                WHERE s.student_id = r.student_id
                  AND s.status = 'submitted'
           )
        """
    )
    op.drop_column("ent_simulations", "counts_for_rating")
    op.drop_column("ent_questions", "archived_at")
