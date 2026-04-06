"""Marketplace browsing, search, and install/uninstall endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from services import marketplace_service

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


@router.get("/skills")
async def browse_skills(
    q: str | None = Query(None, description="Search query"),
    status: str | None = Query(None),
    source_type: str | None = Query(None),
    tag: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await marketplace_service.browse_skills(
        session, q=q, status=status, source_type=source_type, tag=tag,
        page=page, page_size=page_size,
    )


@router.get("/skills/{slug}")
async def get_marketplace_skill(slug: str, session: AsyncSession = Depends(get_session)):
    result = await marketplace_service.get_marketplace_skill(session, slug)
    if not result:
        raise HTTPException(status_code=404, detail="Skill not found")
    return result


@router.post("/skills/{slug}/install")
async def install_skill(slug: str, session: AsyncSession = Depends(get_session)):
    result = await marketplace_service.install_skill(session, slug)
    if not result:
        raise HTTPException(status_code=404, detail="Skill not found")
    return result


@router.post("/skills/{slug}/uninstall")
async def uninstall_skill(slug: str, session: AsyncSession = Depends(get_session)):
    result = await marketplace_service.uninstall_skill(session, slug)
    if not result:
        raise HTTPException(status_code=404, detail="Skill not found")
    return result
