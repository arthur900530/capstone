"""Add full-text search indexes.

Revision ID: 002
Revises: 001
Create Date: 2026-04-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pg_trgm extension for fuzzy matching
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Add tsvector column to skills
    op.add_column("skills", sa.Column("search_vector", sa.Text, nullable=True))

    # GIN index for trigram similarity on display_name and slug
    op.execute(
        "CREATE INDEX ix_skills_name_trgm ON skills USING gin (display_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_skills_slug_trgm ON skills USING gin (slug gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_skills_desc_trgm ON skills USING gin (short_description gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_skills_desc_trgm")
    op.execute("DROP INDEX IF EXISTS ix_skills_slug_trgm")
    op.execute("DROP INDEX IF EXISTS ix_skills_name_trgm")
    op.drop_column("skills", "search_vector")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
