"""xp ledger, and course tests as start/submit sessions

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-22

Two changes that land together because the second depends on the first.

xp_events is the ledger every leaderboard is now summed from. Until now the
only XP source was the ЕНТ simulator, and the week/month boards summed
ent_simulations directly; course tests are about to become a second source,
so the boards need one table that covers both. Every submitted simulation is
copied in here with the XP it was frozen with, so the boards read the same
numbers after this migration as before it, and student_ratings.total_xp
(already the lifetime sum of exactly those values) stays correct unchanged.
The unique (source, source_id) key is what makes an award idempotent.

test_attempts gains the columns of a real session: a status, when it was
started and submitted, the answers given and the detailed result. Existing
rows were all single-shot submissions, so they become `completed` with the
creation time standing in for both timestamps; their score/passed are kept,
and the new detail columns stay NULL because the data to fill them was never
recorded. score/passed become nullable -- an open attempt has neither --
with a CHECK that a completed one always does.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

attempt_status = postgresql.ENUM("in_progress", "completed", name="test_attempt_status", create_type=False)


def upgrade() -> None:
    op.create_table(
        "xp_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "source_id", name="uq_xp_events_source"),
        sa.CheckConstraint("source IN ('ent', 'lesson_test', 'section_test')", name="ck_xp_events_source"),
        sa.CheckConstraint("xp >= 0", name="ck_xp_events_xp_non_negative"),
    )
    op.create_index("ix_xp_events_created_at", "xp_events", ["created_at"])
    op.create_index("ix_xp_events_student_id", "xp_events", ["student_id"])

    op.execute(
        """
        INSERT INTO xp_events (student_id, source, source_id, xp, created_at)
        SELECT student_id, 'ent', id, COALESCE(xp_earned, 0), submitted_at
        FROM ent_simulations
        WHERE status = 'submitted' AND submitted_at IS NOT NULL
        """
    )

    attempt_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "test_attempts",
        sa.Column("status", attempt_status, nullable=False, server_default="completed"),
    )
    # The server default above exists only to fill the existing rows; new
    # attempts start open, which is what the model's default says.
    op.alter_column("test_attempts", "status", server_default="in_progress")
    op.add_column("test_attempts", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("test_attempts", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE test_attempts SET started_at = created_at, submitted_at = created_at")
    op.alter_column("test_attempts", "started_at", nullable=False, server_default=sa.func.now())

    for name in ("earned_points", "max_points", "correct_count", "question_count", "duration_seconds", "xp_earned"):
        op.add_column("test_attempts", sa.Column(name, sa.Integer(), nullable=True))
    op.add_column("test_attempts", sa.Column("answers", postgresql.JSONB(), nullable=True))

    op.alter_column("test_attempts", "score", existing_type=sa.Integer(), nullable=True)
    op.alter_column("test_attempts", "passed", existing_type=sa.Boolean(), nullable=True)
    op.create_check_constraint(
        "ck_test_attempt_completed_has_result",
        "test_attempts",
        "status = 'in_progress' OR (score IS NOT NULL AND passed IS NOT NULL AND submitted_at IS NOT NULL)",
    )

    op.create_index("ix_test_attempts_lesson_status", "test_attempts", ["lesson_id", "status"])
    op.create_index("ix_test_attempts_section_status", "test_attempts", ["section_id", "status"])
    op.create_index(
        "uq_test_attempts_open_lesson",
        "test_attempts",
        ["student_id", "lesson_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress' AND lesson_id IS NOT NULL"),
    )
    op.create_index(
        "uq_test_attempts_open_section",
        "test_attempts",
        ["student_id", "section_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress' AND section_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_test_attempts_open_section", table_name="test_attempts")
    op.drop_index("uq_test_attempts_open_lesson", table_name="test_attempts")
    op.drop_index("ix_test_attempts_section_status", table_name="test_attempts")
    op.drop_index("ix_test_attempts_lesson_status", table_name="test_attempts")
    op.drop_constraint("ck_test_attempt_completed_has_result", "test_attempts", type_="check")

    # Open attempts have no result to keep; the old schema cannot hold them.
    op.execute("DELETE FROM test_attempts WHERE status = 'in_progress'")
    op.alter_column("test_attempts", "passed", existing_type=sa.Boolean(), nullable=False)
    op.alter_column("test_attempts", "score", existing_type=sa.Integer(), nullable=False)

    op.drop_column("test_attempts", "answers")
    for name in ("xp_earned", "duration_seconds", "question_count", "correct_count", "max_points", "earned_points"):
        op.drop_column("test_attempts", name)
    op.drop_column("test_attempts", "submitted_at")
    op.drop_column("test_attempts", "started_at")
    op.drop_column("test_attempts", "status")
    attempt_status.drop(op.get_bind(), checkfirst=True)

    # Course-test XP has no home without the ledger: take it back out of the
    # running totals so student_ratings again equals the ЕНТ-only sum.
    op.execute(
        """
        UPDATE student_ratings r
        SET total_xp = r.total_xp - t.xp
        FROM (
            SELECT student_id, SUM(xp) AS xp FROM xp_events
            WHERE source <> 'ent' GROUP BY student_id
        ) t
        WHERE r.student_id = t.student_id
        """
    )
    op.drop_index("ix_xp_events_student_id", table_name="xp_events")
    op.drop_index("ix_xp_events_created_at", table_name="xp_events")
    op.drop_table("xp_events")
