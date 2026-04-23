"""Add trajectory_annotations to task_runs for cached LLM workflow induction

Revision ID: 007
Revises: 006
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "task_runs",
        sa.Column("trajectory_annotations", JSONB, nullable=True),
    )


def downgrade():
    op.drop_column("task_runs", "trajectory_annotations")
