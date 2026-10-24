"""homework: a grade, and when the work was (last) submitted

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-24

grade is the teacher's mark, 0-100 points, optional (a teacher may accept
or return work without one). submitted_at is when the student last sent the
work: created_at is the *first* submission, and a reworked homework is sent
again into the same row, so the review queue showed the original date for a
resubmission. Existing rows get created_at, the only time known for them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("homework_submissions", sa.Column("grade", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        "ck_homework_submissions_grade_range", "homework_submissions", "grade IS NULL OR grade BETWEEN 0 AND 100"
    )
    op.add_column(
        "homework_submissions",
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.execute("UPDATE homework_submissions SET submitted_at = created_at")
    op.alter_column("homework_submissions", "submitted_at", nullable=False)


def downgrade() -> None:
    op.drop_column("homework_submissions", "submitted_at")
    op.drop_constraint("ck_homework_submissions_grade_range", "homework_submissions", type_="check")
    op.drop_column("homework_submissions", "grade")
