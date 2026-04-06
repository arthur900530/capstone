"""Marketplace browsing, search, and install/uninstall — with in-memory fallback."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


def _db_available() -> bool:
    from routers.skills import _db_available as flag
    return flag


def _get_in_memory_skills() -> list[dict]:
    """Get skills from the in-memory store, enriched with marketplace fields."""
    import server
    skills = sorted(server._SKILLS.values(), key=lambda s: str(s.get("created_at", "")))
    out = []
    for s in skills:
        enriched = dict(s)
        enriched.setdefault("status", "published")
        enriched.setdefault("is_builtin", s.get("type") == "builtin")
        enriched.setdefault("is_cloud_only", False)
        enriched.setdefault("is_installed", True)
        enriched.setdefault("slug", s.get("id", ""))
        enriched.setdefault("tags", [])
        enriched.setdefault("version", "1.0")
        enriched.setdefault("long_description", "")
        enriched.setdefault("published_at", None)
        out.append(enriched)
    return out


@router.get("/skills")
async def browse_skills(
    q: str | None = Query(None, description="Search query"),
    status: str | None = Query(None),
    source_type: str | None = Query(None),
    tag: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    if _db_available():
        from db import get_session as _gs
        from services import marketplace_service
        async for session in _gs():
            return await marketplace_service.browse_skills(
                session, q=q, status=status, source_type=source_type, tag=tag,
                page=page, page_size=page_size,
            )

    # In-memory fallback
    skills = _get_in_memory_skills()
    if q:
        q_lower = q.lower()
        skills = [s for s in skills if q_lower in s.get("name", "").lower() or q_lower in s.get("id", "").lower()]
    if status:
        skills = [s for s in skills if s.get("status") == status]
    if source_type:
        skills = [s for s in skills if s.get("type") == source_type]

    total = len(skills)
    start = (page - 1) * page_size
    items = skills[start:start + page_size]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/skills/{slug}")
async def get_marketplace_skill(slug: str):
    if _db_available():
        from db import get_session as _gs
        from services import marketplace_service
        async for session in _gs():
            result = await marketplace_service.get_marketplace_skill(session, slug)
            if not result:
                raise HTTPException(status_code=404, detail="Skill not found")
            return result

    skills = _get_in_memory_skills()
    for s in skills:
        if s.get("slug") == slug or s.get("id") == slug:
            return s
    raise HTTPException(status_code=404, detail="Skill not found")


@router.post("/skills/{slug}/install")
async def install_skill(slug: str):
    if _db_available():
        from db import get_session as _gs
        from services import marketplace_service
        async for session in _gs():
            result = await marketplace_service.install_skill(session, slug)
            if not result:
                raise HTTPException(status_code=404, detail="Skill not found")
            return result

    return {"ok": True, "slug": slug}


@router.post("/skills/{slug}/uninstall")
async def uninstall_skill(slug: str):
    if _db_available():
        from db import get_session as _gs
        from services import marketplace_service
        async for session in _gs():
            result = await marketplace_service.uninstall_skill(session, slug)
            if not result:
                raise HTTPException(status_code=404, detail="Skill not found")
            return result

    return {"ok": True, "slug": slug}
