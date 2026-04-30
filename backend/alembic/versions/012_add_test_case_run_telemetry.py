"""Add run_telemetry column to test_case_runs.

Stores per-run telemetry: tool call count, tools used, and verifier token
consumption. Nullable so existing rows are unaffected.

Revision ID: 012
Revises: 011
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "test_case_runs",
        sa.Column("run_telemetry", JSONB, nullable=True),
    )


def downgrade():
    op.drop_column("test_case_runs", "run_telemetry")
