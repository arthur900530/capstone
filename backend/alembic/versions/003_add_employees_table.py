"""Add employees table

Revision ID: 003
Revises: 002
Create Date: 2026-04-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "employees",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("task", sa.Text, nullable=False, server_default=""),
        sa.Column("plugin_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("skill_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("model", sa.String(120), nullable=False, server_default="openai/gpt-5.5-2026-04-23"),
        sa.Column("use_reflexion", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("max_trials", sa.Integer, nullable=False, server_default="3"),
        sa.Column("confidence_threshold", sa.Float, nullable=False, server_default="0.7"),
        sa.Column("chat_session_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("files", JSONB, nullable=False, server_default="[]"),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("employees")
