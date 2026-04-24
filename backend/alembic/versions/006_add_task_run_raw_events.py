"""Add raw_events to task_runs for trajectory drilldown

Revision ID: 006
Revises: 005
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "task_runs",
        sa.Column("raw_events", JSONB, nullable=True),
    )


def downgrade():
    op.drop_column("task_runs", "raw_events")
