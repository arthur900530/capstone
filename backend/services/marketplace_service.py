"""Marketplace browsing, search, install/uninstall service."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, func, or_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Skill, SkillVersion, SkillInstallation, SkillTag, SkillTagMap


def _skill_to_marketplace_dict(skill: Skill, version: SkillVersion | None = None, installed: bool = False) -> dict:
    """Convert to marketplace card shape."""
    files = []
    definition = ""
    if version:
        definition = version.skill_md
        files = [
            {"name": f.path, "size": f.size_bytes, "type": f.mime_type}
            for f in version.files
        ]

    return {
        "id": skill.slug,
        "slug": skill.slug,
        "name": skill.display_name,
        "description": skill.short_description,
        "long_description": skill.long_description or "",
        "type": skill.source_type,
        "status": skill.status,
        "is_builtin": skill.is_builtin,
        "is_cloud_only": not installed and skill.is_cloud_only,
        "is_installed": installed,
        "files": files,
        "definition": definition,
        "version": version.version_label if version else "1.0",
        "tags": [t.name for t in skill.tags] if skill.tags else [],
        "created_at": skill.created_at.isoformat() if skill.created_at else "",
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else "",
        "published_at": skill.published_at.isoformat() if skill.published_at else None,
    }


async def browse_skills(
    session: AsyncSession,
    q: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    tag: str | None = None,
    is_installed: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Paginated marketplace browse with optional filters and search."""
    query = select(Skill).options(selectinload(Skill.tags))

    # Filters
    if status:
        query = query.where(Skill.status == status)
    if source_type:
        query = query.where(Skill.source_type == source_type)
    if tag:
        query = query.join(SkillTagMap).join(SkillTag).where(SkillTag.name == tag)

    # Text search (simple ILIKE for now, tsvector added later)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                Skill.display_name.ilike(pattern),
                Skill.short_description.ilike(pattern),
                Skill.slug.ilike(pattern),
            )
        )

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar() or 0

    # Paginate
    query = query.order_by(Skill.updated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    skills = result.scalars().unique().all()

    items = []
    for skill in skills:
        version = None
        if skill.canonical_version_id:
            vr = await session.execute(
                select(SkillVersion)
                .options(selectinload(SkillVersion.files))
                .where(SkillVersion.id == skill.canonical_version_id)
            )
            version = vr.scalar_one_or_none()
        installed = await is_installed(session, skill.id)
        items.append(_skill_to_marketplace_dict(skill, version, installed=installed))

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_marketplace_skill(session: AsyncSession, slug: str) -> dict | None:
    """Full detail for a single marketplace skill."""
    result = await session.execute(
        select(Skill).options(selectinload(Skill.tags)).where(Skill.slug == slug)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        return None

    version = None
    if skill.canonical_version_id:
        vr = await session.execute(
            select(SkillVersion)
            .options(selectinload(SkillVersion.files))
            .where(SkillVersion.id == skill.canonical_version_id)
        )
        version = vr.scalar_one_or_none()

    installed = await is_installed(session, skill.id)
    return _skill_to_marketplace_dict(skill, version, installed=installed)


async def install_skill(session: AsyncSession, slug: str, scope_id: str = "default") -> dict | None:
    """Mark a skill as installed for the given scope (does not mutate global skill record)."""
    result = await session.execute(select(Skill).where(Skill.slug == slug))
    skill = result.scalar_one_or_none()
    if not skill or not skill.canonical_version_id:
        return None

    # Check if already installed for this scope
    existing = await session.execute(
        select(SkillInstallation)
        .where(SkillInstallation.skill_id == skill.id, SkillInstallation.scope_id == scope_id)
    )
    if not existing.scalar_one_or_none():
        session.add(SkillInstallation(
            skill_id=skill.id,
            scope_type="user",
            scope_id=scope_id,
            installed_version_id=skill.canonical_version_id,
            install_status="installed",
        ))
        await session.flush()
    return {"ok": True, "slug": slug}


async def uninstall_skill(session: AsyncSession, slug: str, scope_id: str = "default") -> dict | None:
    """Remove installation record for the given scope (does not mutate global skill record)."""
    result = await session.execute(select(Skill).where(Skill.slug == slug))
    skill = result.scalar_one_or_none()
    if not skill:
        return None

    installs = await session.execute(
        select(SkillInstallation)
        .where(SkillInstallation.skill_id == skill.id, SkillInstallation.scope_id == scope_id)
    )
    for inst in installs.scalars().all():
        await session.delete(inst)
    await session.flush()
    return {"ok": True, "slug": slug}


async def is_installed(session: AsyncSession, skill_id, scope_id: str = "default") -> bool:
    """Check if a skill is installed for the given scope."""
    result = await session.execute(
        select(SkillInstallation)
        .where(SkillInstallation.skill_id == skill_id, SkillInstallation.scope_id == scope_id)
    )
    return result.scalar_one_or_none() is not None
