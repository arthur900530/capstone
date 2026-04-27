"""Add employee governance package fields

Revision ID: 010
Revises: 009
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "employees",
        sa.Column("governance_package", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "employees",
        sa.Column("governance_approval_notes", sa.Text(), nullable=False, server_default=""),
    )


def downgrade():
    op.drop_column("employees", "governance_approval_notes")
    op.drop_column("employees", "governance_package")
