"""Duplicate detection — compares submission text against existing skills."""

from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Skill, SkillVersion, SkillSubmission, SkillSimilarityResult


def _text_similarity(a: str, b: str) -> float:
    """Quick ratio between two strings (0-1)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


async def run_similarity_check(session: AsyncSession, submission_id: str) -> list[dict]:
    """Compare a submission against all published skills and store results."""
    import uuid as _uuid
    try:
        sid = _uuid.UUID(submission_id)
    except ValueError:
        return []

    result = await session.execute(
        select(SkillSubmission).where(SkillSubmission.id == sid)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return []

    # Get all published skills with their current versions
    published = await session.execute(
        select(Skill)
        .where(Skill.status == "published")
        .options(selectinload(Skill.versions))
    )
    skills = published.scalars().all()

    results = []
    for skill in skills:
        # Get current version
        version = None
        if skill.canonical_version_id:
            vr = await session.execute(
                select(SkillVersion).where(SkillVersion.id == skill.canonical_version_id)
            )
            version = vr.scalar_one_or_none()

        name_sim = _text_similarity(sub.proposed_name, skill.display_name)
        content_sim = 0.0
        if version and sub.proposed_skill_md:
            content_sim = _text_similarity(sub.proposed_skill_md, version.skill_md)

        overall = name_sim * 0.3 + content_sim * 0.7

        # Decide recommendation
        if overall > 0.8:
            recommendation = "discard"
        elif overall > 0.5:
            recommendation = "keep_both"
        else:
            recommendation = "accept"

        sim_result = SkillSimilarityResult(
            submission_id=sub.id,
            existing_skill_id=skill.id,
            name_similarity=round(name_sim, 4),
            content_similarity=round(content_sim, 4),
            overall_overlap_score=round(overall, 4),
            decision_recommendation=recommendation,
            rationale=f"Name similarity: {name_sim:.2%}, Content similarity: {content_sim:.2%}",
        )
        session.add(sim_result)
        results.append({
            "existing_skill_slug": skill.slug,
            "name_similarity": round(name_sim, 4),
            "content_similarity": round(content_sim, 4),
            "overall_overlap_score": round(overall, 4),
            "decision_recommendation": recommendation,
        })

    # Update submission status
    sub.status = "duplicate_check_complete"
    await session.flush()

    return results
