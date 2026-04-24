"""Add position column to employees

Revision ID: 004
Revises: 003
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "employees",
        sa.Column(
            "position",
            sa.String(120),
            nullable=False,
            server_default="",
        ),
    )


def downgrade():
    op.drop_column("employees", "position")
