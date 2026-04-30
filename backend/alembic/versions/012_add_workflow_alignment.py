"""Add skill_id to test_cases + workflow_alignment to test_case_runs

Revision ID: 012
Revises: 011
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "test_cases",
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_test_cases_skill_id",
        "test_cases",
        "skills",
        ["skill_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_test_cases_skill_id",
        "test_cases",
        ["skill_id"],
    )

    op.add_column(
        "test_case_runs",
        sa.Column(
            "workflow_alignment",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("test_case_runs", "workflow_alignment")
    op.drop_index("ix_test_cases_skill_id", table_name="test_cases")
    op.drop_constraint("fk_test_cases_skill_id", "test_cases", type_="foreignkey")
    op.drop_column("test_cases", "skill_id")
