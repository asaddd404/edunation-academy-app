"""ent simulator: subject/question bank + timed/untimed simulations

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ent_question_type_enum = sa.Enum("single", "multiple", "matching", "short_answer", name="ent_question_type")
ent_simulation_status_enum = sa.Enum("in_progress", "submitted", name="ent_simulation_status")


def upgrade() -> None:
    ent_question_type_enum.create(op.get_bind(), checkfirst=True)
    ent_simulation_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "ent_subjects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_ent_subjects_slug", "ent_subjects", ["slug"])
    op.create_index("ix_ent_subjects_slug", "ent_subjects", ["slug"])

    op.create_table(
        "ent_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("ent_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("qtype", ent_question_type_enum, nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("max_score IN (1, 2)", name="ck_ent_question_max_score"),
    )
    op.create_index("ix_ent_questions_subject_id", "ent_questions", ["subject_id"])

    op.create_table(
        "ent_choices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("ent_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_ent_choices_question_id", "ent_choices", ["question_id"])

    op.create_table(
        "ent_match_pairs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("ent_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prompt_text", sa.String(length=300), nullable=False),
        sa.Column("answer_text", sa.String(length=300), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_ent_match_pairs_question_id", "ent_match_pairs", ["question_id"])

    op.create_table(
        "ent_answer_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("ent_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.String(length=300), nullable=False),
    )
    op.create_index("ix_ent_answer_variants_question_id", "ent_answer_variants", ["question_id"])

    op.create_table(
        "ent_simulations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_timed", sa.Boolean(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("status", ent_simulation_status_enum, nullable=False, server_default="in_progress"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_expired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("total_score", sa.Integer(), nullable=True),
        sa.Column("max_score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "(is_timed = false AND duration_minutes IS NULL) OR (is_timed = true AND duration_minutes IS NOT NULL)",
            name="ck_ent_simulation_duration",
        ),
    )
    op.create_index("ix_ent_simulations_student_id", "ent_simulations", ["student_id"])

    op.create_table(
        "ent_simulation_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "simulation_id", sa.Integer(), sa.ForeignKey("ent_simulations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("ent_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer_data", postgresql.JSONB(), nullable=True),
        sa.Column("score_awarded", sa.Integer(), nullable=True),
    )
    op.create_index("ix_ent_simulation_questions_simulation_id", "ent_simulation_questions", ["simulation_id"])


def downgrade() -> None:
    op.drop_index("ix_ent_simulation_questions_simulation_id", table_name="ent_simulation_questions")
    op.drop_table("ent_simulation_questions")

    op.drop_index("ix_ent_simulations_student_id", table_name="ent_simulations")
    op.drop_table("ent_simulations")

    op.drop_index("ix_ent_answer_variants_question_id", table_name="ent_answer_variants")
    op.drop_table("ent_answer_variants")

    op.drop_index("ix_ent_match_pairs_question_id", table_name="ent_match_pairs")
    op.drop_table("ent_match_pairs")

    op.drop_index("ix_ent_choices_question_id", table_name="ent_choices")
    op.drop_table("ent_choices")

    op.drop_index("ix_ent_questions_subject_id", table_name="ent_questions")
    op.drop_table("ent_questions")

    op.drop_index("ix_ent_subjects_slug", table_name="ent_subjects")
    op.drop_constraint("uq_ent_subjects_slug", "ent_subjects", type_="unique")
    op.drop_table("ent_subjects")

    ent_simulation_status_enum.drop(op.get_bind(), checkfirst=True)
    ent_question_type_enum.drop(op.get_bind(), checkfirst=True)
