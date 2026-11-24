"""Auto-checked homework: tasks, attempts, per-student records, lesson settings

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TYPES = ("gaps", "single", "multi", "short", "match", "tf", "order", "essay", "file")


def upgrade() -> None:
    op.add_column("lessons", sa.Column("hw_opens_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("lessons", sa.Column("hw_deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("lessons", sa.Column("hw_time_limit_minutes", sa.Integer(), nullable=True))
    op.add_column("lessons", sa.Column("hw_max_attempts", sa.Integer(), nullable=True, server_default="3"))
    op.add_column("lessons", sa.Column("hw_tasks_per_student", sa.Integer(), nullable=True))

    op.create_table(
        "homework_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("points", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("type IN (" + ", ".join(f"'{t}'" for t in _TYPES) + ")", name="ck_homework_task_type"),
        sa.CheckConstraint("points BETWEEN 1 AND 1000", name="ck_homework_task_points"),
    )
    op.create_index("ix_homework_tasks_lesson_id", "homework_tasks", ["lesson_id"])

    op.create_table(
        "homework_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="in_progress"),
        sa.Column("task_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("layout", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tasks_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("answers", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_earned", sa.Float(), nullable=True),
        sa.Column("auto_max", sa.Float(), nullable=True),
        sa.Column("manual_max", sa.Float(), nullable=True),
        sa.Column("results", postgresql.JSONB(), nullable=True),
        sa.Column("away_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.CheckConstraint("status IN ('in_progress', 'submitted')", name="ck_homework_attempt_status"),
    )
    op.create_index("ix_homework_attempts_lesson_student", "homework_attempts", ["lesson_id", "student_id"])
    op.create_index(
        "uq_homework_attempts_open",
        "homework_attempts",
        ["lesson_id", "student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )

    op.create_table(
        "homework_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_task_ids", postgresql.JSONB(), nullable=True),
        sa.Column("attempts_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_variant", postgresql.JSONB(), nullable=True),
        sa.Column("previous_decision", postgresql.JSONB(), nullable=True),
        sa.Column("extended_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manual_scores", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("override_grade", sa.Integer(), nullable=True),
        sa.Column("teacher_comment", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("lesson_id", "student_id", name="uq_homework_record_lesson_student"),
        sa.CheckConstraint("override_grade IS NULL OR override_grade BETWEEN 0 AND 100", name="ck_homework_record_grade"),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('keep', 'zero', 'edit', 'retake')", name="ck_homework_record_decision"
        ),
    )


def downgrade() -> None:
    op.drop_table("homework_records")
    op.drop_index("uq_homework_attempts_open", table_name="homework_attempts")
    op.drop_index("ix_homework_attempts_lesson_student", table_name="homework_attempts")
    op.drop_table("homework_attempts")
    op.drop_index("ix_homework_tasks_lesson_id", table_name="homework_tasks")
    op.drop_table("homework_tasks")
    op.drop_column("lessons", "hw_tasks_per_student")
    op.drop_column("lessons", "hw_max_attempts")
    op.drop_column("lessons", "hw_time_limit_minutes")
    op.drop_column("lessons", "hw_deadline")
    op.drop_column("lessons", "hw_opens_at")
