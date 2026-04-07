"""Skill submission and review endpoints — with in-memory fallback."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/marketplace/submissions", tags=["submissions"])

# In-memory store when DB is unavailable
_submissions: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SubmissionCreate(BaseModel):
    name: str
    description: str = ""
    skill_md: str = ""
    submission_type: str = "authored"


class DecisionRequest(BaseModel):
    decision: str  # accept | discard | keep_both
    reason: str = ""


def _db_available() -> bool:
    from routers.skills import _db_available as flag
    return flag


@router.post("")
async def create_submission(body: SubmissionCreate, background_tasks: BackgroundTasks):
    if _db_available():
        from db.engine import async_session
        from services import submission_service, similarity_service
        async with async_session() as session:
            result = await submission_service.create_submission(
                session, name=body.name, description=body.description,
                skill_md=body.skill_md, submission_type=body.submission_type,
            )
            await session.commit()

            async def _run_bg(sid):
                async with async_session() as s:
                    try:
                        await similarity_service.run_similarity_check(s, sid)
                        await s.commit()
                    except Exception:
                        await s.rollback()

            background_tasks.add_task(_run_bg, result["id"])
            return result

    # In-memory fallback
    sub_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    sub = {
        "id": sub_id,
        "proposed_name": body.name,
        "proposed_description": body.description,
        "proposed_skill_md": body.skill_md,
        "submission_type": body.submission_type,
        "status": "uploaded",
        "created_at": now,
        "updated_at": now,
        "reviewed_at": None,
        "similarity_results": [],
    }
    _submissions[sub_id] = sub
    return sub


@router.get("")
async def list_submissions(status: str | None = Query(None)):
    if _db_available():
        from db.engine import async_session
        from services import submission_service
        async with async_session() as session:
            return await submission_service.list_submissions(session, status=status)

    subs = list(_submissions.values())
    if status:
        subs = [s for s in subs if s["status"] == status]
    return sorted(subs, key=lambda s: s["created_at"], reverse=True)


@router.get("/{submission_id}")
async def get_submission(submission_id: str):
    if _db_available():
        from db.engine import async_session
        from services import submission_service
        async with async_session() as session:
            result = await submission_service.get_submission(session, submission_id)
            if not result:
                raise HTTPException(status_code=404, detail="Submission not found")
            return result

    sub = _submissions.get(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    return sub


@router.post("/{submission_id}/decision")
async def make_decision(submission_id: str, body: DecisionRequest):
    if _db_available():
        from db.engine import async_session
        from services import submission_service
        async with async_session() as session:
            result = await submission_service.make_decision(
                session, submission_id, decision=body.decision, reason=body.reason,
            )
            if not result:
                raise HTTPException(status_code=404, detail="Submission not found or invalid decision")
            await session.commit()
            return result

    sub = _submissions.get(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    sub["status"] = "accepted" if body.decision == "accept" else body.decision
    sub["reviewed_at"] = _now_iso()
    sub["updated_at"] = _now_iso()
    return {"ok": True, "decision": body.decision, "submission_id": submission_id}


@router.delete("/{submission_id}")
async def delete_submission(submission_id: str):
    if _db_available():
        from db.engine import async_session
        from sqlalchemy import select, delete as sa_delete
        from db.models import SkillSubmission, SkillSimilarityResult, SkillPolicyDecision
        import uuid as _uuid
        try:
            sid = _uuid.UUID(submission_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Invalid submission ID")
        async with async_session() as session:
            # Delete related records first
            await session.execute(sa_delete(SkillSimilarityResult).where(SkillSimilarityResult.submission_id == sid))
            await session.execute(sa_delete(SkillPolicyDecision).where(SkillPolicyDecision.submission_id == sid))
            result = await session.execute(select(SkillSubmission).where(SkillSubmission.id == sid))
            sub = result.scalar_one_or_none()
            if not sub:
                raise HTTPException(status_code=404, detail="Submission not found")
            await session.delete(sub)
            await session.commit()
            return {"ok": True}

    if submission_id in _submissions:
        del _submissions[submission_id]
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Submission not found")
