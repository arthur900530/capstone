"""Skill CRUD router — backward-compatible with in-memory fallback.

When PostgreSQL is available, uses the DB via skill_service.
When DB is unavailable, falls back to the in-memory _SKILLS dict from server.py.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

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


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_skills():
    if _db_available:
        from db import get_session as _gs
        from services import skill_service
        async for session in _gs():
            return await skill_service.list_skills(session)

    skills, _ = _get_in_memory_stores()
    return sorted(skills.values(), key=lambda s: str(s.get("created_at", "")))


@router.get("/{skill_id}")
async def get_skill(skill_id: str):
    if _db_available:
        from db import get_session as _gs
        from services import skill_service
        async for session in _gs():
            result = await skill_service.get_skill(session, skill_id)
            if not result:
                raise HTTPException(status_code=404, detail="Skill not found")
            return result

    skills, _ = _get_in_memory_stores()
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skills[skill_id]


@router.post("", status_code=201)
async def create_skill(body: SkillCreate):
    if _db_available:
        from db import get_session as _gs
        from services import skill_service
        file_dicts = [f.model_dump(exclude_none=True) for f in body.files] if body.files else None
        async for session in _gs():
            return await skill_service.create_skill(
                session, name=body.name, description=body.description,
                definition=body.definition, files=file_dicts,
            )

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
        from db import get_session as _gs
        from services import skill_service
        async for session in _gs():
            result = await skill_service.update_skill(
                session, skill_id, name=body.name,
                description=body.description, definition=body.definition,
            )
            if not result:
                raise HTTPException(status_code=404, detail="Skill not found")
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
        from db import get_session as _gs
        from services import skill_service
        async for session in _gs():
            result = await skill_service.add_files(
                session, skill_id, [f.model_dump(exclude_none=True) for f in files]
            )
            if not result:
                raise HTTPException(status_code=404, detail="Skill not found")
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
        from db import get_session as _gs
        from services import skill_service
        async for session in _gs():
            result = await skill_service.remove_file(session, skill_id, filename)
            if not result:
                raise HTTPException(status_code=404, detail="Skill not found")
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
        from db import get_session as _gs
        from services import skill_service
        async for session in _gs():
            deleted = await skill_service.delete_skill(session, skill_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Skill not found or is builtin")
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
        from db import get_session as _gs
        from services import skill_service
        async for session in _gs():
            result = await skill_service.get_file_content(session, skill_id, filename)
            if not result:
                raise HTTPException(status_code=404, detail="File not found")
            return result

    skills, file_contents = _get_in_memory_stores()
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill_files = file_contents.get(skill_id, {})
    if filename in skill_files:
        return {"filename": filename, "content": skill_files[filename]}
    file_exists = any(f["name"] == filename for f in skills[skill_id].get("files", []))
    if file_exists:
        return {"filename": filename, "content": f"# {filename}\n\n(File content placeholder)"}
    raise HTTPException(status_code=404, detail="File not found")


@router.post("/train")
async def train_skills(files: list[UploadFile] = File(...)):
    """Accept media uploads, run MMSkillTrainer, return newly created skills."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    from skills_ingestor.mm_train import MMSkillTrainer

    tmp_dir = tempfile.mkdtemp(prefix="mm_train_")
    try:
        saved_paths: list[str] = []
        for upload in files:
            dest = os.path.join(tmp_dir, upload.filename)
            with open(dest, "wb") as f:
                content = await upload.read()
                f.write(content)
            saved_paths.append(dest)

        if _db_available:
            from db import get_session as _gs
            from services import skill_service
            async for session in _gs():
                existing = await skill_service.list_skills(session)
                existing_ids = {s["id"] for s in existing}

            trainer = MMSkillTrainer()
            await asyncio.to_thread(trainer.train, saved_paths)

            # Sync new filesystem skills into DB
            from db.seed import seed_from_filesystem
            await seed_from_filesystem()

            # Also refresh in-memory stores so agent runtime sees new skills
            import server
            server._SKILLS = server._load_skills_from_disk()
            server._FILE_CONTENTS = server._load_file_contents_from_disk()

            async for session in _gs():
                all_skills = await skill_service.list_skills(session)
                return [s for s in all_skills if s["id"] not in existing_ids]
        else:
            # In-memory fallback
            skills, _ = _get_in_memory_stores()
            existing_ids = set(skills.keys())

            trainer = MMSkillTrainer()
            await asyncio.to_thread(trainer.train, saved_paths)

            import server
            refreshed = server._load_skills_from_disk()
            new_skills = []
            for sid, skill in refreshed.items():
                if sid not in existing_ids:
                    skills[sid] = skill
                    new_skills.append(skill)
                else:
                    skills[sid] = skill
            return new_skills

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
