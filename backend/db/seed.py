"""Seed existing filesystem skills into PostgreSQL.

Usage:
    cd backend && python -m db.seed
"""

import asyncio
import hashlib
import mimetypes
import os
import re
from pathlib import Path

import yaml
from sqlalchemy import select

from db.engine import async_session
from db.models import Skill, SkillVersion, SkillFile, SkillTag, SkillTagMap

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from markdown body. Returns (meta, body)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1]) or {}
                return meta, parts[2].strip()
            except yaml.YAMLError:
                pass
    return {}, text


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


async def seed_from_filesystem():
    """Walk backend/skills/ and insert into the DB. Idempotent (skips existing slugs)."""
    if not SKILLS_DIR.is_dir():
        print(f"Skills directory not found: {SKILLS_DIR}")
        return

    async with async_session() as session:
        # Get existing slugs to skip
        result = await session.execute(select(Skill.slug))
        existing_slugs = {row[0] for row in result.all()}

        seeded = 0
        skipped = 0

        for entry in sorted(os.listdir(SKILLS_DIR)):
            skill_path = SKILLS_DIR / entry
            skill_md_path = skill_path / "SKILL.md"
            if not skill_path.is_dir() or not skill_md_path.is_file():
                continue

            slug = entry  # directory name is the slug
            if slug in existing_slugs:
                skipped += 1
                continue

            # Read and parse SKILL.md
            skill_md_text = skill_md_path.read_text()
            meta, _body = _parse_frontmatter(skill_md_text)

            display_name = meta.get("name", slug)
            # Capitalize if it looks like a slug
            if "-" in display_name and display_name == display_name.lower():
                display_name = " ".join(w.capitalize() for w in display_name.split("-"))

            description = meta.get("description", "")
            is_user = slug.startswith("user-") or slug.startswith("user_")
            source_type = "user" if is_user else "builtin"

            # Create skill
            skill = Skill(
                slug=slug,
                display_name=display_name,
                short_description=description,
                source_type=source_type,
                status="published",
                is_builtin=not is_user,
                is_cloud_only=False,
            )
            session.add(skill)
            await session.flush()  # get skill.id

            # Create version
            version = SkillVersion(
                skill_id=skill.id,
                version_label="1.0",
                skill_md=skill_md_text,
                content_hash=_content_hash(skill_md_text),
                is_current=True,
            )
            session.add(version)
            await session.flush()  # get version.id

            # Link canonical version
            skill.canonical_version_id = version.id

            # Walk files
            for root, _dirs, filenames in os.walk(skill_path):
                for fname in filenames:
                    fpath = Path(root) / fname
                    rel_path = str(fpath.relative_to(skill_path))
                    try:
                        content = fpath.read_text()
                    except (UnicodeDecodeError, OSError):
                        content = None

                    session.add(SkillFile(
                        skill_version_id=version.id,
                        path=rel_path,
                        file_name=fname,
                        mime_type=mimetypes.guess_type(str(fpath))[0],
                        size_bytes=fpath.stat().st_size,
                        content=content,
                        content_hash=_content_hash(content) if content else "",
                    ))

            # Extract tags from frontmatter
            tags = meta.get("triggers", [])
            if isinstance(tags, list):
                for tag_name in tags:
                    tag_name = str(tag_name).strip().lower()
                    if not tag_name:
                        continue
                    # Get or create tag
                    result = await session.execute(
                        select(SkillTag).where(SkillTag.name == tag_name)
                    )
                    tag = result.scalar_one_or_none()
                    if not tag:
                        tag = SkillTag(name=tag_name)
                        session.add(tag)
                        await session.flush()
                    session.add(SkillTagMap(skill_id=skill.id, tag_id=tag.id))

            seeded += 1

        await session.commit()
        print(f"Seed complete: {seeded} added, {skipped} already existed.")


if __name__ == "__main__":
    asyncio.run(seed_from_filesystem())
