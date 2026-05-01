"""Add workflow_step column to test_cases.

Stores the LLM-inferred workflow phase label for each test case (e.g.
'entity_lookup', 'risk_scoring', 'report_writing'). Nullable so existing
rows are unaffected — the UI treats NULL as "Other".

Revision ID: 013
Revises: 012
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "test_cases",
        sa.Column("workflow_step", sa.String(80), nullable=True),
    )


def downgrade():
    op.drop_column("test_cases", "workflow_step")
