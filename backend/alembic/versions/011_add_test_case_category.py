"""Add category and subcategory columns to test_cases.

Revision ID: 011
Revises: 010
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows predate the comprehensive-suite generator and should keep
    # their adversarial framing — backfill them as ``edge`` so badges and
    # exports remain accurate.
    op.add_column(
        "test_cases",
        sa.Column(
            "category",
            sa.String(20),
            nullable=False,
            server_default="edge",
        ),
    )
    op.add_column(
        "test_cases",
        sa.Column("subcategory", sa.String(80), nullable=True),
    )


def downgrade():
    op.drop_column("test_cases", "subcategory")
    op.drop_column("test_cases", "category")
