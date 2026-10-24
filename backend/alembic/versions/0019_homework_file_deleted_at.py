"""homework: when the attached file was removed by the retention policy

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-24

Attachments of reviewed homework are deleted from disk a few days after the
review (app/core/retention.py). The row keeps the answer text, grade, status
and the file's original name; file_path is cleared and this records when the
file went, so the screens can say "файл удалён по истечении срока хранения"
instead of offering a download that 404s.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("homework_submissions", sa.Column("file_deleted_at", sa.DateTime(timezone=True), nullable=True))
    # The sweep's own query: reviewed work that still has a file, by review time.
    op.create_index(
        "ix_homework_submissions_retention",
        "homework_submissions",
        ["reviewed_at"],
        postgresql_where=sa.text("file_path IS NOT NULL AND status <> 'submitted'"),
    )


def downgrade() -> None:
    op.drop_index("ix_homework_submissions_retention", table_name="homework_submissions")
    op.drop_column("homework_submissions", "file_deleted_at")
