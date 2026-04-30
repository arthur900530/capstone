"""SQLAlchemy ORM models for the skill marketplace and digital employees."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    BigInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ── Skills ────────────────────────────────────────────────────────────────────


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    long_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="builtin"
    )  # builtin | user | community
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft"
    )  # draft | pending_review | published | rejected | archived | superseded
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="public"
    )
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_cloud_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    canonical_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skill_versions.id", use_alter=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    versions: Mapped[list[SkillVersion]] = relationship(
        back_populates="skill", foreign_keys="SkillVersion.skill_id"
    )
    tags: Mapped[list[SkillTag]] = relationship(
        secondary="skill_tag_map", back_populates="skills"
    )
    installations: Mapped[list[SkillInstallation]] = relationship(back_populates="skill")


# ── Versions ──────────────────────────────────────────────────────────────────


class SkillVersion(Base):
    __tablename__ = "skill_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id"), nullable=False
    )
    version_label: Mapped[str] = mapped_column(String(30), nullable=False, default="1.0")
    skill_md: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    skill: Mapped[Skill] = relationship(
        back_populates="versions", foreign_keys=[skill_id]
    )
    files: Mapped[list[SkillFile]] = relationship(back_populates="version")


# ── Files ─────────────────────────────────────────────────────────────────────


class SkillFile(Base):
    __tablename__ = "skill_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    skill_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skill_versions.id"), nullable=False
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Relationships
    version: Mapped[SkillVersion] = relationship(back_populates="files")


# ── Tags ──────────────────────────────────────────────────────────────────────


class SkillTag(Base):
    __tablename__ = "skill_tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)

    skills: Mapped[list[Skill]] = relationship(
        secondary="skill_tag_map", back_populates="tags"
    )


class SkillTagMap(Base):
    __tablename__ = "skill_tag_map"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skill_tags.id"), primary_key=True
    )


# ── Installations ─────────────────────────────────────────────────────────────


class SkillInstallation(Base):
    __tablename__ = "skill_installations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False, default="user")
    scope_id: Mapped[str] = mapped_column(String(120), nullable=False, default="default")
    installed_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skill_versions.id"), nullable=False
    )
    install_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="installed"
    )
    installed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    skill: Mapped[Skill] = relationship(back_populates="installations")


# ── Submissions ───────────────────────────────────────────────────────────────


class SkillSubmission(Base):
    __tablename__ = "skill_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    submission_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="authored"
    )
    source_skill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id"), nullable=True
    )
    proposed_name: Mapped[str] = mapped_column(String(200), nullable=False)
    proposed_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_skill_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="uploaded"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    files: Mapped[list[SubmissionFile]] = relationship(back_populates="submission")
    similarity_results: Mapped[list[SkillSimilarityResult]] = relationship(
        back_populates="submission"
    )
    policy_decisions: Mapped[list[SkillPolicyDecision]] = relationship(
        back_populates="submission"
    )


class SubmissionFile(Base):
    __tablename__ = "submission_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skill_submissions.id"), nullable=False
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    submission: Mapped[SkillSubmission] = relationship(back_populates="files")


# ── Similarity & Policy ──────────────────────────────────────────────────────


class SkillSimilarityResult(Base):
    __tablename__ = "skill_similarity_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skill_submissions.id"), nullable=False
    )
    existing_skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id"), nullable=False
    )
    name_similarity: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    content_similarity: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    overall_overlap_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    decision_recommendation: Mapped[str] = mapped_column(
        String(30), nullable=False, default="accept"
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    submission: Mapped[SkillSubmission] = relationship(back_populates="similarity_results")


class SkillPolicyDecision(Base):
    __tablename__ = "skill_policy_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skill_submissions.id"), nullable=False
    )
    decision_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_skill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id"), nullable=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    submission: Mapped[SkillSubmission] = relationship(back_populates="policy_decisions")


# ── Digital Employees ────────────────────────────────────────────────────────


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    # Job title / role (e.g. "Equity Research Analyst"). Optional — legacy rows
    # predate the column and so we default to an empty string rather than NULL.
    position: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # Short free-form hint the user typed in the creation wizard; kept for the
    # post-creation "System Prompt" tab so they can see and edit the original
    # intent alongside the LLM-expanded ``task`` it produced.
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    task: Mapped[str] = mapped_column(Text, nullable=False, default="")
    plugin_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    skill_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="openai/gpt-4o")
    use_reflexion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_trials: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    chat_session_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    files: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    task_runs: Mapped[list["TaskRun"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


# ── Task Runs (per-employee metrics) ─────────────────────────────────────────


class TaskRun(Base):
    """One row per user-turn an employee handled.

    Written when a chat turn finishes so the report card can aggregate real
    behavioral metrics (tool calls, trials, latency, tool mix) per employee
    without having to re-walk the in-memory chat transcript on every read.
    """

    __tablename__ = "task_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    task_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_trials: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    n_reflections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_histogram: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raw_events: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    trajectory_annotations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Passive 1–5 rating the user can leave on the agent's terminal answer.
    # Nullable so "unrated" is distinct from any numeric score.
    user_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_rating_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    employee: Mapped[Employee] = relationship(back_populates="task_runs")

    __table_args__ = (
        UniqueConstraint("session_id", "task_index", name="ix_task_runs_session"),
    )


# ── Auto Test Cases ──────────────────────────────────────────────────────────


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Optional: when set, this test case is targeting one specific skill's
    # workflow. The verifier loads ``backend/skills/<slug>/workflow.json``
    # for this skill (if present) and includes it in the LLM-judge prompt
    # so the verdict can score per-step adherence.
    skill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    success_criteria: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hard_failure_signals: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expected_tool_families: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    max_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=20000)
    generated_by_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    employee: Mapped[Employee] = relationship()
    skill: Mapped["Skill | None"] = relationship(lazy="joined")
    runs: Mapped[list["TestCaseRun"]] = relationship(
        back_populates="test_case", cascade="all, delete-orphan"
    )


class TestCaseRun(Base):
    __tablename__ = "test_case_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False, default="error")
    verdict_source: Mapped[str] = mapped_column(String(30), nullable=False, default="deterministic")
    judge_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deterministic_checks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Per-step adherence to the expected workflow as returned by the LLM
    # judge: ``{"steps": [{"path": [int, ...], "satisfied": bool, "evidence": str}]}``.
    # The deterministic ``workflow_completion`` rollup is derived from this
    # at read time; we deliberately don't persist that derived field.
    workflow_alignment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    test_case: Mapped[TestCase] = relationship(back_populates="runs")
