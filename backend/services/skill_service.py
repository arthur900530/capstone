"""Skill CRUD service — all DB access for skills goes through here.

Every public function returns plain dicts matching the legacy API shape so
the frontend keeps working without changes.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Skill, SkillVersion, SkillFile


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _skill_to_dict(skill: Skill, version: SkillVersion | None = None) -> dict:
    """Convert ORM objects to the dict shape the frontend expects."""
    files = []
    definition = ""
    if version:
        definition = version.skill_md
        files = [
            {
                "name": f.path,
                "size": f.size_bytes,
                "type": f.mime_type,
            }
            for f in version.files
        ]

    return {
        "id": skill.slug,
        "name": skill.display_name,
        "description": skill.short_description,
        "type": skill.source_type,
        "files": files,
        "definition": definition,
        "created_at": skill.created_at.isoformat() if skill.created_at else "",
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else "",
        # New marketplace fields (frontend ignores these until it's ready)
        "status": skill.status,
        "is_builtin": skill.is_builtin,
        "is_cloud_only": skill.is_cloud_only,
        "slug": skill.slug,
        "version": version.version_label if version else "1.0",
    }


async def _get_skill_with_version(
    session: AsyncSession, slug: str
) -> tuple[Skill, SkillVersion | None]:
    """Fetch a skill by slug with its current version + files eagerly loaded."""
    result = await session.execute(
        select(Skill).where(Skill.slug == slug)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        return None, None

    version = None
    if skill.canonical_version_id:
        result = await session.execute(
            select(SkillVersion)
            .options(selectinload(SkillVersion.files))
            .where(SkillVersion.id == skill.canonical_version_id)
        )
        version = result.scalar_one_or_none()

    return skill, version


# ── Public API ────���───────────────────────────────��───────────────────────────


async def list_skills(session: AsyncSession) -> list[dict]:
    """Return all skills sorted by creation time (matches GET /api/skills)."""
    result = await session.execute(
        select(Skill).order_by(Skill.created_at)
    )
    skills = result.scalars().all()

    out = []
    for skill in skills:
        version = None
        if skill.canonical_version_id:
            vr = await session.execute(
                select(SkillVersion)
                .options(selectinload(SkillVersion.files))
                .where(SkillVersion.id == skill.canonical_version_id)
            )
            version = vr.scalar_one_or_none()
        out.append(_skill_to_dict(skill, version))
    return out


async def get_skill(session: AsyncSession, skill_id: str) -> dict | None:
    """Fetch one skill by slug. Returns None if not found."""
    skill, version = await _get_skill_with_version(session, skill_id)
    if not skill:
        return None
    return _skill_to_dict(skill, version)


async def create_skill(
    session: AsyncSession,
    name: str,
    description: str = "",
    definition: str = "",
    files: list[dict] | None = None,
) -> dict:
    """Create a new user skill. Returns the dict for the API response."""
    slug = f"user_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"

    skill = Skill(
        slug=slug,
        display_name=name,
        short_description=description,
        source_type="user",
        status="published",
        is_builtin=False,
        is_cloud_only=False,
    )
    session.add(skill)
    await session.flush()

    version = SkillVersion(
        skill_id=skill.id,
        version_label="1.0",
        skill_md=definition,
        content_hash=_hash(definition) if definition else "",
        is_current=True,
    )
    session.add(version)
    await session.flush()

    skill.canonical_version_id = version.id

    # Store file metadata
    if files:
        for f in files:
            session.add(SkillFile(
                skill_version_id=version.id,
                path=f.get("name", ""),
                file_name=f.get("name", "").split("/")[-1],
                mime_type=f.get("type"),
                size_bytes=f.get("size"),
            ))

    await session.flush()

    # Re-fetch version with files eagerly loaded
    vr = await session.execute(
        select(SkillVersion)
        .options(selectinload(SkillVersion.files))
        .where(SkillVersion.id == version.id)
    )
    version = vr.scalar_one_or_none()
    return _skill_to_dict(skill, version)


async def update_skill(
    session: AsyncSession,
    skill_id: str,
    name: str | None = None,
    description: str | None = None,
    definition: str | None = None,
) -> dict | None:
    """Update skill metadata. Creates a new version if definition changed."""
    skill, version = await _get_skill_with_version(session, skill_id)
    if not skill:
        return None

    if name is not None:
        skill.display_name = name
    if description is not None:
        skill.short_description = description

    # If definition changed, create a new version
    if definition is not None and version and definition != version.skill_md:
        version.is_current = False
        new_version = SkillVersion(
            skill_id=skill.id,
            skill_md=definition,
            content_hash=_hash(definition),
            is_current=True,
        )
        session.add(new_version)
        await session.flush()
        skill.canonical_version_id = new_version.id
        version = new_version
    elif definition is not None and version:
        # Same content, just touch the timestamp
        pass

    skill.updated_at = datetime.now(timezone.utc)
    await session.flush()

    # Re-fetch version with files
    if skill.canonical_version_id:
        vr = await session.execute(
            select(SkillVersion)
            .options(selectinload(SkillVersion.files))
            .where(SkillVersion.id == skill.canonical_version_id)
        )
        version = vr.scalar_one_or_none()

    return _skill_to_dict(skill, version)


async def delete_skill(session: AsyncSession, skill_id: str) -> bool:
    """Delete a user skill. Returns False if not found or builtin."""
    result = await session.execute(select(Skill).where(Skill.slug == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        return False
    if skill.is_builtin:
        return False

    # Delete versions and files (cascade would be cleaner but let's be explicit)
    versions = await session.execute(
        select(SkillVersion).where(SkillVersion.skill_id == skill.id)
    )
    for v in versions.scalars().all():
        files = await session.execute(
            select(SkillFile).where(SkillFile.skill_version_id == v.id)
        )
        for f in files.scalars().all():
            await session.delete(f)
        await session.delete(v)

    await session.delete(skill)
    return True


async def add_files(
    session: AsyncSession, skill_id: str, files: list[dict]
) -> dict | None:
    """Add file metadata to the current version."""
    skill, version = await _get_skill_with_version(session, skill_id)
    if not skill or not version:
        return None

    existing_paths = {f.path for f in version.files}
    for f in files:
        name = f.get("name", "")
        if name not in existing_paths:
            session.add(SkillFile(
                skill_version_id=version.id,
                path=name,
                file_name=name.split("/")[-1],
                mime_type=f.get("type"),
                size_bytes=f.get("size"),
            ))
            existing_paths.add(name)

    skill.updated_at = datetime.now(timezone.utc)
    await session.flush()

    # Re-fetch version with updated files
    vr = await session.execute(
        select(SkillVersion)
        .options(selectinload(SkillVersion.files))
        .where(SkillVersion.id == version.id)
    )
    version = vr.scalar_one_or_none()
    return _skill_to_dict(skill, version)


async def remove_file(
    session: AsyncSession, skill_id: str, filename: str
) -> dict | None:
    """Remove a file from the current version."""
    skill, version = await _get_skill_with_version(session, skill_id)
    if not skill or not version:
        return None

    for f in version.files:
        if f.path == filename:
            await session.delete(f)
            break

    skill.updated_at = datetime.now(timezone.utc)
    await session.flush()

    # Re-fetch
    vr = await session.execute(
        select(SkillVersion)
        .options(selectinload(SkillVersion.files))
        .where(SkillVersion.id == version.id)
    )
    version = vr.scalar_one_or_none()
    return _skill_to_dict(skill, version)


async def get_file_content(
    session: AsyncSession, skill_id: str, filename: str
) -> dict | None:
    """Return file content dict or None."""
    skill, version = await _get_skill_with_version(session, skill_id)
    if not skill or not version:
        return None

    for f in version.files:
        if f.path == filename:
            content = f.content or f"# {filename}\n\n(File content placeholder)"
            return {"filename": filename, "content": content}

    return None


async def get_skill_for_materialization(
    session: AsyncSession, skill_id: str
) -> dict | None:
    """Return definition + file contents for agent runtime materialization."""
    skill, version = await _get_skill_with_version(session, skill_id)
    if not skill or not version:
        return None

    return {
        "id": skill.slug,
        "definition": version.skill_md,
        "files": {
            f.path: (f.content or "") for f in version.files
        },
    }
