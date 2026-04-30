"""Add source + test_case_run_id to task_runs

Lets autotest runs land in the same `task_runs` table the chat turn
pipeline uses so the report card can show them alongside chat turns
(with an AUTOTEST chip in the UI). The optional ``test_case_run_id``
back-reference lets the trajectory drawer lazily fetch the originating
test's verdict/judge fields without a separate index.

Revision ID: 013
Revises: 012
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "task_runs",
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="chat",
        ),
    )
    op.add_column(
        "task_runs",
        sa.Column(
            "test_case_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_task_runs_test_case_run_id",
        "task_runs",
        "test_case_runs",
        ["test_case_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(
        "fk_task_runs_test_case_run_id",
        "task_runs",
        type_="foreignkey",
    )
    op.drop_column("task_runs", "test_case_run_id")
    op.drop_column("task_runs", "source")
