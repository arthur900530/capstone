"""Initial skill marketplace schema.

Revision ID: 001
Revises: None
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── skill_versions (created first so skills can FK to it) ────────────
    op.create_table(
        "skill_versions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("skill_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version_label", sa.String(30), nullable=False, server_default="1.0"),
        sa.Column("skill_md", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )

    # ── skills ───────────────────────────────────────────────────────────
    op.create_table(
        "skills",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("slug", sa.String(120), unique=True, nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("short_description", sa.Text, nullable=False, server_default=""),
        sa.Column("long_description", sa.Text, nullable=True),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="builtin"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="public"),
        sa.Column("is_builtin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_cloud_only", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("canonical_version_id", UUID(as_uuid=True), sa.ForeignKey("skill_versions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Now add the FK from skill_versions.skill_id -> skills.id
    op.create_foreign_key("fk_skill_versions_skill", "skill_versions", "skills", ["skill_id"], ["id"])

    # ── skill_files ──────────────────────────────────────────────────────
    op.create_table(
        "skill_files",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("skill_version_id", UUID(as_uuid=True), sa.ForeignKey("skill_versions.id"), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("storage_uri", sa.Text, nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── skill_tags + join ────────────────────────────────────────────────
    op.create_table(
        "skill_tags",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(60), unique=True, nullable=False),
    )

    op.create_table(
        "skill_tag_map",
        sa.Column("skill_id", UUID(as_uuid=True), sa.ForeignKey("skills.id"), primary_key=True),
        sa.Column("tag_id", UUID(as_uuid=True), sa.ForeignKey("skill_tags.id"), primary_key=True),
    )

    # ── skill_installations ──────────────────────────────────────────────
    op.create_table(
        "skill_installations",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("skill_id", UUID(as_uuid=True), sa.ForeignKey("skills.id"), nullable=False),
        sa.Column("scope_type", sa.String(30), nullable=False, server_default="user"),
        sa.Column("scope_id", sa.String(120), nullable=False, server_default="default"),
        sa.Column("installed_version_id", UUID(as_uuid=True), sa.ForeignKey("skill_versions.id"), nullable=False),
        sa.Column("install_status", sa.String(20), nullable=False, server_default="installed"),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── skill_submissions ────────────────────────────────────────────────
    op.create_table(
        "skill_submissions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("submission_type", sa.String(30), nullable=False, server_default="authored"),
        sa.Column("source_skill_id", UUID(as_uuid=True), sa.ForeignKey("skills.id"), nullable=True),
        sa.Column("proposed_name", sa.String(200), nullable=False),
        sa.Column("proposed_description", sa.Text, nullable=True),
        sa.Column("proposed_skill_md", sa.Text, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="uploaded"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── submission_files ─────────────────────────────────────────────────
    op.create_table(
        "submission_files",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("submission_id", UUID(as_uuid=True), sa.ForeignKey("skill_submissions.id"), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
    )

    # ── skill_similarity_results ─────────────────────────────────────────
    op.create_table(
        "skill_similarity_results",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("submission_id", UUID(as_uuid=True), sa.ForeignKey("skill_submissions.id"), nullable=False),
        sa.Column("existing_skill_id", UUID(as_uuid=True), sa.ForeignKey("skills.id"), nullable=False),
        sa.Column("name_similarity", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("content_similarity", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("overall_overlap_score", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("decision_recommendation", sa.String(30), nullable=False, server_default="accept"),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── skill_policy_decisions ───────────────────────────────────────────
    op.create_table(
        "skill_policy_decisions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("submission_id", UUID(as_uuid=True), sa.ForeignKey("skill_submissions.id"), nullable=False),
        sa.Column("decision_type", sa.String(30), nullable=False),
        sa.Column("target_skill_id", UUID(as_uuid=True), sa.ForeignKey("skills.id"), nullable=True),
        sa.Column("decision_reason", sa.Text, nullable=True),
        sa.Column("system_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("skill_policy_decisions")
    op.drop_table("skill_similarity_results")
    op.drop_table("submission_files")
    op.drop_table("skill_submissions")
    op.drop_table("skill_installations")
    op.drop_table("skill_tag_map")
    op.drop_table("skill_tags")
    op.drop_table("skill_files")
    op.drop_table("skills")
    op.drop_table("skill_versions")
