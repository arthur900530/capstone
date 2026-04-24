"""Add task_runs table for per-employee metrics

Revision ID: 005
Revises: 004
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "employee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("task_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prompt_preview", sa.Text, nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("n_tool_calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("n_trials", sa.Integer, nullable=False, server_default="1"),
        sa.Column("n_reflections", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "tool_histogram",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_task_runs_employee_started",
        "task_runs",
        ["employee_id", "started_at"],
    )
    op.create_index(
        "ix_task_runs_session",
        "task_runs",
        ["session_id", "task_index"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_task_runs_session", table_name="task_runs")
    op.drop_index("ix_task_runs_employee_started", table_name="task_runs")
    op.drop_table("task_runs")
