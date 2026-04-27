"""Add test_cases and test_case_runs tables.

Revision ID: 010
Revises: 009
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "test_cases",
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
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("success_criteria", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "hard_failure_signals",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("expected_tool_families", JSONB, nullable=True),
        sa.Column("max_latency_ms", sa.Integer(), nullable=False, server_default="20000"),
        sa.Column("generated_by_model", sa.String(120), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_test_cases_employee_created",
        "test_cases",
        ["employee_id", "created_at"],
    )

    op.create_table(
        "test_case_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "test_case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("test_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verdict", sa.String(20), nullable=False, server_default="error"),
        sa.Column(
            "verdict_source",
            sa.String(30),
            nullable=False,
            server_default="deterministic",
        ),
        sa.Column("judge_rationale", sa.Text(), nullable=True),
        sa.Column("judge_evidence_quote", sa.Text(), nullable=True),
        sa.Column("judge_confidence", sa.Float(), nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("agent_session_id", sa.String(80), nullable=True),
        sa.Column("deterministic_checks", JSONB, nullable=True),
    )
    op.create_index(
        "ix_test_case_runs_case_started",
        "test_case_runs",
        ["test_case_id", "started_at"],
    )


def downgrade():
    op.drop_index("ix_test_case_runs_case_started", table_name="test_case_runs")
    op.drop_table("test_case_runs")
    op.drop_index("ix_test_cases_employee_created", table_name="test_cases")
    op.drop_table("test_cases")
