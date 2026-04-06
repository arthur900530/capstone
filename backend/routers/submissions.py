"""Skill submission and review endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session, async_session
from services import submission_service, similarity_service

router = APIRouter(prefix="/api/marketplace/submissions", tags=["submissions"])


class SubmissionCreate(BaseModel):
    name: str
    description: str = ""
    skill_md: str = ""
    submission_type: str = "authored"


class DecisionRequest(BaseModel):
    decision: str  # accept | discard | keep_both
    reason: str = ""


async def _run_similarity_in_background(submission_id: str):
    """Background task to compute similarity scores."""
    async with async_session() as session:
        try:
            await similarity_service.run_similarity_check(session, submission_id)
            await session.commit()
        except Exception:
            await session.rollback()


@router.post("")
async def create_submission(
    body: SubmissionCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    result = await submission_service.create_submission(
        session, name=body.name, description=body.description,
        skill_md=body.skill_md, submission_type=body.submission_type,
    )
    # Trigger duplicate detection in background
    background_tasks.add_task(_run_similarity_in_background, result["id"])
    return result


@router.get("")
async def list_submissions(
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    return await submission_service.list_submissions(session, status=status)


@router.get("/{submission_id}")
async def get_submission(
    submission_id: str, session: AsyncSession = Depends(get_session)
):
    result = await submission_service.get_submission(session, submission_id)
    if not result:
        raise HTTPException(status_code=404, detail="Submission not found")
    return result


@router.post("/{submission_id}/decision")
async def make_decision(
    submission_id: str,
    body: DecisionRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await submission_service.make_decision(
        session, submission_id, decision=body.decision, reason=body.reason,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Submission not found or invalid decision")
    return result
