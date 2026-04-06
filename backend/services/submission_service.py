"""Skill submission workflow — create, review, and policy decisions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    Skill,
    SkillVersion,
    SkillSubmission,
    SkillSimilarityResult,
    SkillPolicyDecision,
)


def _submission_to_dict(sub: SkillSubmission) -> dict:
    return {
        "id": str(sub.id),
        "proposed_name": sub.proposed_name,
        "proposed_description": sub.proposed_description,
        "proposed_skill_md": sub.proposed_skill_md,
        "submission_type": sub.submission_type,
        "status": sub.status,
        "created_at": sub.created_at.isoformat() if sub.created_at else "",
        "updated_at": sub.updated_at.isoformat() if sub.updated_at else "",
        "reviewed_at": sub.reviewed_at.isoformat() if sub.reviewed_at else None,
        "similarity_results": [
            {
                "existing_skill_slug": "",  # filled below
                "name_similarity": float(r.name_similarity),
                "content_similarity": float(r.content_similarity),
                "overall_overlap_score": float(r.overall_overlap_score),
                "decision_recommendation": r.decision_recommendation,
                "rationale": r.rationale,
            }
            for r in sub.similarity_results
        ] if sub.similarity_results else [],
    }


async def create_submission(
    session: AsyncSession,
    name: str,
    description: str = "",
    skill_md: str = "",
    submission_type: str = "authored",
) -> dict:
    """Create a new skill submission."""
    sub = SkillSubmission(
        proposed_name=name,
        proposed_description=description,
        proposed_skill_md=skill_md,
        submission_type=submission_type,
        status="uploaded",
    )
    session.add(sub)
    await session.flush()
    return _submission_to_dict(sub)


async def list_submissions(
    session: AsyncSession, status: str | None = None
) -> list[dict]:
    """List submissions, optionally filtered by status."""
    query = (
        select(SkillSubmission)
        .options(selectinload(SkillSubmission.similarity_results))
        .order_by(SkillSubmission.created_at.desc())
    )
    if status:
        query = query.where(SkillSubmission.status == status)

    result = await session.execute(query)
    subs = result.scalars().all()

    out = []
    for sub in subs:
        d = _submission_to_dict(sub)
        # Fill in skill slugs for similarity results
        for i, sr in enumerate(sub.similarity_results or []):
            skill_result = await session.execute(
                select(Skill.slug).where(Skill.id == sr.existing_skill_id)
            )
            row = skill_result.first()
            if row:
                d["similarity_results"][i]["existing_skill_slug"] = row[0]
        out.append(d)
    return out


async def get_submission(session: AsyncSession, submission_id: str) -> dict | None:
    """Get a single submission by ID with similarity results."""
    import uuid as _uuid
    try:
        sid = _uuid.UUID(submission_id)
    except ValueError:
        return None

    result = await session.execute(
        select(SkillSubmission)
        .options(selectinload(SkillSubmission.similarity_results))
        .where(SkillSubmission.id == sid)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return None

    d = _submission_to_dict(sub)
    for i, sr in enumerate(sub.similarity_results or []):
        skill_result = await session.execute(
            select(Skill.slug).where(Skill.id == sr.existing_skill_id)
        )
        row = skill_result.first()
        if row:
            d["similarity_results"][i]["existing_skill_slug"] = row[0]
    return d


async def make_decision(
    session: AsyncSession,
    submission_id: str,
    decision: str,
    reason: str = "",
) -> dict | None:
    """Apply a policy decision (accept, discard, keep_both) to a submission."""
    import uuid as _uuid
    try:
        sid = _uuid.UUID(submission_id)
    except ValueError:
        return None

    result = await session.execute(
        select(SkillSubmission).where(SkillSubmission.id == sid)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return None

    valid_decisions = {"accept", "discard", "keep_both", "merge"}
    if decision not in valid_decisions:
        return None

    # Record decision
    session.add(SkillPolicyDecision(
        submission_id=sub.id,
        decision_type=decision,
        decision_reason=reason,
    ))

    now = datetime.now(timezone.utc)

    if decision == "accept":
        # Create a published skill from the submission
        slug = sub.proposed_name.lower().replace(" ", "-")
        slug = "".join(c for c in slug if c.isalnum() or c == "-")[:60]

        skill = Skill(
            slug=slug,
            display_name=sub.proposed_name,
            short_description=sub.proposed_description or "",
            source_type="user",
            status="published",
            is_builtin=False,
            is_cloud_only=False,
            published_at=now,
        )
        session.add(skill)
        await session.flush()

        if sub.proposed_skill_md:
            version = SkillVersion(
                skill_id=skill.id,
                skill_md=sub.proposed_skill_md,
                is_current=True,
            )
            session.add(version)
            await session.flush()
            skill.canonical_version_id = version.id

        sub.status = "accepted"
    elif decision == "discard":
        sub.status = "discarded"
    elif decision == "keep_both":
        sub.status = "kept_both"
        # Same as accept — create a new skill
        slug = sub.proposed_name.lower().replace(" ", "-")
        slug = "".join(c for c in slug if c.isalnum() or c == "-")[:60]

        skill = Skill(
            slug=slug,
            display_name=sub.proposed_name,
            short_description=sub.proposed_description or "",
            source_type="user",
            status="published",
            is_builtin=False,
            is_cloud_only=False,
            published_at=now,
        )
        session.add(skill)
        await session.flush()

        if sub.proposed_skill_md:
            version = SkillVersion(
                skill_id=skill.id,
                skill_md=sub.proposed_skill_md,
                is_current=True,
            )
            session.add(version)
            await session.flush()
            skill.canonical_version_id = version.id

        sub.status = "kept_both"

    sub.reviewed_at = now
    sub.updated_at = now
    await session.flush()

    return {"ok": True, "decision": decision, "submission_id": submission_id}
