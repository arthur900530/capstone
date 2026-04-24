"""Add description column to employees

Revision ID: 009
Revises: 008
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "employees",
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade():
    op.drop_column("employees", "description")
