"""Skill CRUD router — backward-compatible with in-memory fallback.

When PostgreSQL is available, uses the DB via skill_service.
When DB is unavailable, falls back to the in-memory _SKILLS dict from server.py.
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from skills_ingestor.sessions import get_default_store
from workflow import load_workflow_with_memory_fallback

router = APIRouter(prefix="/api/skills", tags=["skills"])

# Set to True during lifespan if DB is available
_db_available = False


def set_db_available(value: bool):
    global _db_available
    _db_available = value


# ── Request models ────────────────────────────────────────────────────────────


class SkillFileMetadata(BaseModel):
    name: str
    size: int | None = None
    type: str | None = None


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    definition: str = ""
    files: list[SkillFileMetadata] | None = None


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    definition: str | None = None


# ── In-memory fallback helpers ────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_in_memory_stores():
    """Import the in-memory skill stores from server module."""
    import server
    return server._SKILLS, server._FILE_CONTENTS


def _get_session_factory():
    from db.engine import async_session as factory
    return factory


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_skills():
    if _db_available:
        from services import skill_service
        async with _get_session_factory()() as session:
            db_skills = await skill_service.list_skills(session)

        # In --demo mode, the train flow only writes new skills to the
        # in-memory ``server._SKILLS`` dict (it never inserts DB rows so
        # the demo never pollutes persistent state across restarts).
        # Without this merge, freshly trained skills would be invisible
        # in any surface that fetches via this endpoint — most visibly
        # the trajectory drawer's "Compare with workflow" picker. Append
        # any in-memory entry whose slug isn't already represented in
        # the DB result so trained-this-session skills show up alongside
        # the DB-seeded ones, while existing UUID-based assignments stay
        # untouched.
        if os.getenv("DEMO_REPLAY") == "1":
            skills, _ = _get_in_memory_stores()
            existing_slugs = {
                str(s.get("slug") or s.get("id") or "") for s in db_skills
            }
            existing_slugs.discard("")
            extras = [
                skill
                for slug, skill in skills.items()
                if slug not in existing_slugs
            ]
            if extras:
                extras.sort(key=lambda s: str(s.get("created_at", "")))
                return [*db_skills, *extras]
        return db_skills

    skills, _ = _get_in_memory_stores()
    return sorted(skills.values(), key=lambda s: str(s.get("created_at", "")))


@router.get("/{skill_id}")
async def get_skill(skill_id: str):
    if _db_available:
        from services import skill_service
        async with _get_session_factory()() as session:
            result = await skill_service.get_skill(session, skill_id)
        if result:
            return result
        # Demo-mode fallback: ``list_skills`` merges in-memory entries
        # that aren't backed by a DB row, so the picker can hand us a
        # slug-shaped id the DB has never heard of. Resolve it from
        # ``server._SKILLS`` before 404'ing so detail surfaces (skill
        # detail panel, etc.) keep working for trained-this-session
        # skills.
        if os.getenv("DEMO_REPLAY") == "1":
            skills, _ = _get_in_memory_stores()
            if skill_id in skills:
                return skills[skill_id]
        raise HTTPException(status_code=404, detail="Skill not found")

    skills, _ = _get_in_memory_stores()
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skills[skill_id]


@router.post("", status_code=201)
async def create_skill(body: SkillCreate):
    if _db_available:
        from services import skill_service
        file_dicts = [f.model_dump(exclude_none=True) for f in body.files] if body.files else None
        async with _get_session_factory()() as session:
            result = await skill_service.create_skill(
                session, name=body.name, description=body.description,
                definition=body.definition, files=file_dicts,
            )
            await session.commit()
            return result

    skills, _ = _get_in_memory_stores()
    skill_id = f"user_{body.name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    now = _now_iso()
    file_dicts = [f.model_dump(exclude_none=True) for f in body.files] if body.files else []
    skill = {
        "id": skill_id, "name": body.name, "description": body.description,
        "type": "user", "files": file_dicts, "definition": body.definition,
        "created_at": now, "updated_at": now,
    }
    skills[skill_id] = skill
    return skill


@router.patch("/{skill_id}")
async def update_skill(skill_id: str, body: SkillUpdate):
    if _db_available:
        from services import skill_service
        async with _get_session_factory()() as session:
            result = await skill_service.update_skill(
                session, skill_id, name=body.name,
                description=body.description, definition=body.definition,
            )
            if not result:
                raise HTTPException(status_code=404, detail="Skill not found")
            await session.commit()
            return result

    skills, _ = _get_in_memory_stores()
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill = skills[skill_id]
    if body.name is not None:
        skill["name"] = body.name
    if body.description is not None:
        skill["description"] = body.description
    if body.definition is not None:
        skill["definition"] = body.definition
    skill["updated_at"] = _now_iso()
    return skill


@router.post("/{skill_id}/files")
async def add_skill_files(skill_id: str, files: list[SkillFileMetadata]):
    if _db_available:
        from services import skill_service
        async with _get_session_factory()() as session:
            result = await skill_service.add_files(
                session, skill_id, [f.model_dump(exclude_none=True) for f in files]
            )
            if not result:
                raise HTTPException(status_code=404, detail="Skill not found")
            await session.commit()
            return result

    skills, _ = _get_in_memory_stores()
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill = skills[skill_id]
    existing_names = {f["name"] for f in skill["files"]}
    for f in files:
        if f.name not in existing_names:
            skill["files"].append(f.model_dump(exclude_none=True))
            existing_names.add(f.name)
    skill["updated_at"] = _now_iso()
    return skill


@router.delete("/{skill_id}/files/{filename}")
async def remove_skill_file(skill_id: str, filename: str):
    if _db_available:
        from services import skill_service
        async with _get_session_factory()() as session:
            result = await skill_service.remove_file(session, skill_id, filename)
            if not result:
                raise HTTPException(status_code=404, detail="Skill not found")
            await session.commit()
            return result

    skills, _ = _get_in_memory_stores()
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill = skills[skill_id]
    skill["files"] = [f for f in skill["files"] if f["name"] != filename]
    skill["updated_at"] = _now_iso()
    return skill


@router.delete("/{skill_id}")
async def delete_skill(skill_id: str):
    if _db_available:
        from services import skill_service
        async with _get_session_factory()() as session:
            deleted = await skill_service.delete_skill(session, skill_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Skill not found or is builtin")
            await session.commit()
            return {"ok": True}

    skills, _ = _get_in_memory_stores()
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skills[skill_id]["type"] == "builtin":
        raise HTTPException(status_code=403, detail="Cannot delete builtin skills")
    del skills[skill_id]
    return {"ok": True}


@router.get("/{skill_id}/files/{filename:path}")
async def get_skill_file_content(skill_id: str, filename: str):
    if _db_available:
        from services import skill_service
        async with _get_session_factory()() as session:
            result = await skill_service.get_file_content(session, skill_id, filename)
            if not result:
                raise HTTPException(status_code=404, detail="File not found")
            return result

    skills, file_contents = _get_in_memory_stores()
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill_files = file_contents.get(skill_id, {})
    # Normalize: try both with and without ./ prefix
    for candidate in (filename, f"./{filename}", filename.lstrip("./")):
        if candidate in skill_files:
            return {"filename": filename, "content": skill_files[candidate]}
    file_exists = any(
        f["name"] == filename or f["name"] == f"./{filename}" or f["name"].lstrip("./") == filename
        for f in skills[skill_id].get("files", [])
    )
    if file_exists:
        return {"filename": filename, "content": f"# {filename}\n\n(File content placeholder)"}
    raise HTTPException(status_code=404, detail="File not found")


@router.post("/train")
async def train_skills(files: list[UploadFile] = File(...)):
    """Accept media uploads, run MMSkillTrainer, return newly created skills.

    The response also carries:

    - ``session_id`` and a ``files`` list of session-scoped video URLs so the
      frontend can play the source media next to the extracted workflow.
      The session directory is kept around for a short TTL (see
      :mod:`skills_ingestor.sessions`) and can be cleaned up explicitly via
      ``DELETE /api/skills/train/sessions/{session_id}``.
    - ``workflows`` keyed by skill slug — the structured workflow trees that
      MMSkillTrainer recorded via the ``record_workflow`` tool.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    from skills_ingestor.mm_train import MMSkillTrainer

    tmp_dir = tempfile.mkdtemp(prefix="mm_train_")
    saved_paths: list[str] = []
    saved_basenames: list[str] = []
    train_failed = False
    try:
        for upload in files:
            safe_name = os.path.basename(upload.filename or "")
            if not safe_name:
                continue
            dest = os.path.join(tmp_dir, safe_name)
            # Verify resolved path stays under tmp_dir
            if not os.path.realpath(dest).startswith(os.path.realpath(tmp_dir)):
                continue
            with open(dest, "wb") as f:
                content = await upload.read()
                f.write(content)
            saved_paths.append(dest)
            saved_basenames.append(safe_name)

        if os.getenv("DEMO_REPLAY") == "1":
            # Demo mode: train normally and surface the freshly extracted
            # skills only in process memory (``server._SKILLS`` /
            # ``server._FILE_CONTENTS``) so the wizard, browse list and
            # chat runtime can all see them. The on-disk
            # ``backend/skills/<slug>/`` directories are then removed so
            # demo mode never pollutes the working tree across server
            # restarts. The skills are forced to ``type="user"`` so
            # ``_validate_skills_for_runtime`` resolves their files from
            # the in-memory store rather than the deleted disk path.
            skills_root = Path(__file__).resolve().parent.parent / "skills"
            before_dirs = (
                {p.name for p in skills_root.iterdir() if p.is_dir()}
                if skills_root.exists()
                else set()
            )

            trainer = MMSkillTrainer()
            train_result = await asyncio.to_thread(trainer.train, saved_paths)

            new_skills: list[dict] = []
            if skills_root.exists():
                import server

                refreshed = server._load_skills_from_disk()
                after_dirs = {
                    p.name for p in skills_root.iterdir() if p.is_dir()
                }
                for slug in sorted(after_dirs - before_dirs):
                    skill = refreshed.get(slug)
                    if skill is None:
                        continue
                    skill = {**skill, "type": "user"}
                    skill_dir = skills_root / slug
                    contents: dict[str, str] = {}
                    for meta in skill.get("files") or []:
                        rel = meta["name"]
                        try:
                            with open(skill_dir / rel, encoding="utf-8") as fh:
                                contents[rel] = fh.read()
                        except (OSError, UnicodeDecodeError):
                            # Binary or unreadable auxiliaries are rare
                            # for trained skills (which are mostly
                            # SKILL.md text). Skipping them is safe;
                            # validation only fails for non-SKILL.md
                            # files with no retrievable content.
                            continue

                    server._SKILLS[slug] = skill
                    server._FILE_CONTENTS[slug] = contents
                    new_skills.append(skill)

                    shutil.rmtree(skill_dir, ignore_errors=True)
        elif _db_available:
            from services import skill_service
            async with _get_session_factory()() as session:
                existing = await skill_service.list_skills(session)
                existing_ids = {s["id"] for s in existing}

            trainer = MMSkillTrainer()
            train_result = await asyncio.to_thread(trainer.train, saved_paths)

            from db.seed import seed_from_filesystem
            await seed_from_filesystem()

            import server
            server._SKILLS = server._load_skills_from_disk()
            server._FILE_CONTENTS = server._load_file_contents_from_disk()

            async with _get_session_factory()() as session:
                all_skills = await skill_service.list_skills(session)
                new_skills = [s for s in all_skills if s["id"] not in existing_ids]
        else:
            # In-memory fallback
            skills, _ = _get_in_memory_stores()
            existing_ids = set(skills.keys())

            trainer = MMSkillTrainer()
            train_result = await asyncio.to_thread(trainer.train, saved_paths)

            import server
            refreshed = server._load_skills_from_disk()
            new_skills = []
            for sid, skill in refreshed.items():
                if sid not in existing_ids:
                    skills[sid] = skill
                    new_skills.append(skill)
                else:
                    skills[sid] = skill

        session = get_default_store().register(tmp_dir, saved_basenames)
        file_descriptors = [
            {
                "name": name,
                "url": f"/api/skills/train/sessions/{session.session_id}/files/{name}",
            }
            for name in saved_basenames
        ]
        return {
            "skills": new_skills,
            "session_id": session.session_id,
            "files": file_descriptors,
            "workflows": train_result.get("workflows", {}),
        }

    except HTTPException:
        train_failed = True
        raise
    except Exception as e:
        train_failed = True
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Only purge the temp dir if we never handed it off to the session
        # store (i.e. on early errors before session.register completed).
        if train_failed:
            shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/train/sessions/{session_id}/files/{filename}")
async def get_train_session_file(session_id: str, filename: str):
    """Stream a file from a post-train session directory."""
    session = get_default_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Train session not found or expired")

    try:
        path = session.file_path(filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found in session")

    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, media_type=media_type or "application/octet-stream", filename=filename)


@router.delete("/train/sessions/{session_id}")
async def delete_train_session(session_id: str):
    """Tear down a post-train session early (frees disk before TTL)."""
    removed = get_default_store().discard(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Train session not found")
    return {"ok": True}


@router.get("/{skill_id}/workflow")
async def get_skill_workflow(skill_id: str):
    """Return the persisted ``workflow.json`` for a skill.

    Workflows live next to ``SKILL.md`` under
    ``backend/skills/<slug>/workflow.json``. The frontend identifies
    skills by their DB UUID in DB mode and by an in-memory id that
    matches the slug otherwise — resolve both shapes to the slug before
    reading from disk.
    """
    if not skill_id:
        raise HTTPException(status_code=400, detail="skill_id is required")

    slug = await _resolve_skill_slug(skill_id)
    if slug is None:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Use the memory-fallback variant so a skill whose disk dir was
    # purged (--demo training keeps the workflow text in server.
    # _FILE_CONTENTS but removes backend/skills/<slug>/) can still
    # serve its workflow.json to the trajectory drawer / review surfaces.
    workflow = await asyncio.to_thread(load_workflow_with_memory_fallback, slug)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found for skill")
    return workflow.to_dict()


async def _resolve_skill_slug(skill_id: str) -> str | None:
    """Resolve a frontend-supplied skill identifier to an on-disk slug.

    In DB mode ``skill_id`` is a UUID, so look up ``Skill.slug``. In the
    in-memory fallback, ``_SKILLS`` is keyed by the slug already, but
    legacy callers may pass an arbitrary id that happens to match a
    directory under ``backend/skills/``.
    """
    if _db_available:
        try:
            skill_uuid = uuid.UUID(skill_id)
        except (ValueError, TypeError):
            # Not a UUID — fall through to the in-memory / slug-style
            # lookup so legacy ids like ``user_foo_abcdef`` keep working.
            skill_uuid = None
        if skill_uuid is not None:
            from db.models import Skill
            from sqlalchemy import select

            async with _get_session_factory()() as session:
                row = (
                    await session.execute(select(Skill).where(Skill.id == skill_uuid))
                ).scalar_one_or_none()
                if row is not None:
                    return row.slug

    skills, _ = _get_in_memory_stores()
    if skill_id in skills:
        # The in-memory id IS the directory slug for skills written by
        # ``_load_skills_from_disk``; for user-created skills it's a
        # ``user_<slug>_<hex>`` id that won't have a directory.
        return skill_id
    return None
