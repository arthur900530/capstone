"""Add user_rating + user_rating_at to task_runs for passive per-answer ratings

Revision ID: 008
Revises: 007
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "task_runs",
        sa.Column("user_rating", sa.Integer, nullable=True),
    )
    op.add_column(
        "task_runs",
        sa.Column("user_rating_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_task_runs_user_rating_range",
        "task_runs",
        "user_rating IS NULL OR (user_rating BETWEEN 1 AND 5)",
    )


def downgrade():
    op.drop_constraint(
        "ck_task_runs_user_rating_range", "task_runs", type_="check"
    )
    op.drop_column("task_runs", "user_rating_at")
    op.drop_column("task_runs", "user_rating")
