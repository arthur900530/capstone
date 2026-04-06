"""Skill CRUD router — backward-compatible replacement for the inline handlers."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from services import skill_service
from skills_ingestor.mm_train import MMSkillTrainer

router = APIRouter(prefix="/api/skills", tags=["skills"])


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


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_skills(session: AsyncSession = Depends(get_session)):
    return await skill_service.list_skills(session)


@router.get("/{skill_id}")
async def get_skill(skill_id: str, session: AsyncSession = Depends(get_session)):
    skill = await skill_service.get_skill(session, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.post("", status_code=201)
async def create_skill(body: SkillCreate, session: AsyncSession = Depends(get_session)):
    file_dicts = [f.model_dump(exclude_none=True) for f in body.files] if body.files else None
    return await skill_service.create_skill(
        session,
        name=body.name,
        description=body.description,
        definition=body.definition,
        files=file_dicts,
    )


@router.patch("/{skill_id}")
async def update_skill(
    skill_id: str, body: SkillUpdate, session: AsyncSession = Depends(get_session)
):
    result = await skill_service.update_skill(
        session,
        skill_id,
        name=body.name,
        description=body.description,
        definition=body.definition,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Skill not found")
    return result


@router.post("/{skill_id}/files")
async def add_skill_files(
    skill_id: str,
    files: list[SkillFileMetadata],
    session: AsyncSession = Depends(get_session),
):
    result = await skill_service.add_files(
        session, skill_id, [f.model_dump(exclude_none=True) for f in files]
    )
    if not result:
        raise HTTPException(status_code=404, detail="Skill not found")
    return result


@router.delete("/{skill_id}/files/{filename}")
async def remove_skill_file(
    skill_id: str, filename: str, session: AsyncSession = Depends(get_session)
):
    result = await skill_service.remove_file(session, skill_id, filename)
    if not result:
        raise HTTPException(status_code=404, detail="Skill not found")
    return result


@router.delete("/{skill_id}")
async def delete_skill(skill_id: str, session: AsyncSession = Depends(get_session)):
    deleted = await skill_service.delete_skill(session, skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill not found or is builtin")
    return {"ok": True}


@router.get("/{skill_id}/files/{filename:path}")
async def get_skill_file_content(
    skill_id: str, filename: str, session: AsyncSession = Depends(get_session)
):
    result = await skill_service.get_file_content(session, skill_id, filename)
    if not result:
        raise HTTPException(status_code=404, detail="File not found")
    return result


@router.post("/train")
async def train_skills(
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Accept media uploads, run MMSkillTrainer, return newly created skills."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Get existing slugs before training
    existing = await skill_service.list_skills(session)
    existing_ids = {s["id"] for s in existing}

    tmp_dir = tempfile.mkdtemp(prefix="mm_train_")
    try:
        saved_paths: list[str] = []
        for upload in files:
            dest = os.path.join(tmp_dir, upload.filename)
            with open(dest, "wb") as f:
                content = await upload.read()
                f.write(content)
            saved_paths.append(dest)

        trainer = MMSkillTrainer()
        await asyncio.to_thread(trainer.train, saved_paths)

        # Re-seed any new skills from filesystem into DB
        from db.seed import seed_from_filesystem
        await seed_from_filesystem()

        # Return only new skills
        all_skills = await skill_service.list_skills(session)
        new_skills = [s for s in all_skills if s["id"] not in existing_ids]
        return new_skills

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
