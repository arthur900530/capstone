"""Employee CRUD router with in-memory fallback when DB is unavailable."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from metrics import (
    aggregate_task_runs,
    serialize_task_run,
    task_runs_from_chat,
)
from trajectory import build_nodes_from_events, flatten_action_nodes, segment_nodes, to_dict

router = APIRouter(prefix="/api/employees", tags=["employees"])

_db_available = False
_memory_store: list[dict] = []


def set_db_available(value: bool):
    global _db_available
    _db_available = value


class EmployeeCreate(BaseModel):
    name: str
    position: str = ""
    task: str = ""
    pluginIds: list[str] = []
    skillIds: list[str] = []
    model: str = ""
    useReflexion: bool = False
    maxTrials: int = 3
    confidenceThreshold: float = 0.7
    files: list[dict] = []


class EmployeeUpdate(BaseModel):
    name: str | None = None
    position: str | None = None
    task: str | None = None
    pluginIds: list[str] | None = None
    skillIds: list[str] | None = None
    model: str | None = None
    useReflexion: bool | None = None
    maxTrials: int | None = None
    confidenceThreshold: float | None = None
    chatSessionIds: list[str] | None = None
    files: list[dict] | None = None
    lastActiveAt: str | None = None


def _parse_uuid(employee_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(employee_id)
    except ValueError:
        raise HTTPException(400, "Invalid employee ID format")


_ACTIVE_THRESHOLD_SECS = 600  # 10 minutes


def _derive_status(last_active_at) -> str:
    if last_active_at:
        elapsed = (datetime.now(timezone.utc) - last_active_at).total_seconds()
        return "active" if elapsed < _ACTIVE_THRESHOLD_SECS else "idle"
    return "idle"


def _row_to_dict(row) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "position": getattr(row, "position", "") or "",
        "task": row.task,
        "pluginIds": row.plugin_ids or [],
        "skillIds": row.skill_ids or [],
        "model": row.model,
        "useReflexion": row.use_reflexion,
        "maxTrials": row.max_trials,
        "confidenceThreshold": row.confidence_threshold,
        "status": _derive_status(row.last_active_at),
        "chatSessionIds": row.chat_session_ids or [],
        "files": row.files or [],
        "lastActiveAt": row.last_active_at.isoformat() if row.last_active_at else None,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("")
async def list_employees():
    if _db_available:
        from db.engine import async_session
        from db.models import Employee
        from sqlalchemy import select

        async with async_session() as session:
            rows = (await session.execute(select(Employee).order_by(Employee.created_at.desc()))).scalars().all()
            return [_row_to_dict(r) for r in rows]
    return _memory_store


@router.get("/{employee_id}")
async def get_employee(employee_id: str):
    if _db_available:
        from db.engine import async_session
        from db.models import Employee
        from sqlalchemy import select

        async with async_session() as session:
            row = (await session.execute(
                select(Employee).where(Employee.id == _parse_uuid(employee_id))
            )).scalar_one_or_none()
            if not row:
                raise HTTPException(404, "Employee not found")
            return _row_to_dict(row)

    emp = next((e for e in _memory_store if e["id"] == employee_id), None)
    if not emp:
        raise HTTPException(404, "Employee not found")
    return emp


@router.post("")
async def create_employee(body: EmployeeCreate):
    if _db_available:
        from db.engine import async_session
        from db.models import Employee

        async with async_session() as session:
            emp = Employee(
                name=body.name,
                position=body.position,
                task=body.task,
                plugin_ids=body.pluginIds,
                skill_ids=body.skillIds,
                model=body.model,
                use_reflexion=body.useReflexion,
                max_trials=body.maxTrials,
                confidence_threshold=body.confidenceThreshold,
                files=body.files,
            )
            session.add(emp)
            await session.commit()
            await session.refresh(emp)
            return _row_to_dict(emp)

    emp = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "position": body.position,
        "task": body.task,
        "pluginIds": body.pluginIds,
        "skillIds": body.skillIds,
        "model": body.model,
        "useReflexion": body.useReflexion,
        "maxTrials": body.maxTrials,
        "confidenceThreshold": body.confidenceThreshold,
        "chatSessionIds": [],
        "files": body.files,
        "status": "idle",
        "lastActiveAt": None,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    _memory_store.append(emp)
    return emp


@router.patch("/{employee_id}")
async def update_employee(employee_id: str, body: EmployeeUpdate):
    if _db_available:
        from db.engine import async_session
        from db.models import Employee
        from sqlalchemy import select

        async with async_session() as session:
            row = (await session.execute(
                select(Employee).where(Employee.id == _parse_uuid(employee_id))
            )).scalar_one_or_none()
            if not row:
                raise HTTPException(404, "Employee not found")

            if body.name is not None:
                row.name = body.name
            if body.position is not None:
                row.position = body.position
            if body.task is not None:
                row.task = body.task
            if body.pluginIds is not None:
                row.plugin_ids = body.pluginIds
            if body.skillIds is not None:
                row.skill_ids = body.skillIds
            if body.model is not None:
                row.model = body.model
            if body.useReflexion is not None:
                row.use_reflexion = body.useReflexion
            if body.maxTrials is not None:
                row.max_trials = body.maxTrials
            if body.confidenceThreshold is not None:
                row.confidence_threshold = body.confidenceThreshold
            if body.chatSessionIds is not None:
                row.chat_session_ids = body.chatSessionIds
            if body.files is not None:
                row.files = body.files
            if body.lastActiveAt is not None:
                row.last_active_at = datetime.fromisoformat(body.lastActiveAt)

            await session.commit()
            await session.refresh(row)
            return _row_to_dict(row)

    emp = next((e for e in _memory_store if e["id"] == employee_id), None)
    if not emp:
        raise HTTPException(404, "Employee not found")
    updates = body.model_dump(exclude_none=True)
    emp.update(updates)
    return emp


@router.delete("/{employee_id}")
async def delete_employee(employee_id: str):
    if _db_available:
        from db.engine import async_session
        from db.models import Employee
        from sqlalchemy import select

        async with async_session() as session:
            row = (await session.execute(
                select(Employee).where(Employee.id == _parse_uuid(employee_id))
            )).scalar_one_or_none()
            if not row:
                raise HTTPException(404, "Employee not found")
            await session.delete(row)
            await session.commit()
            return {"ok": True}

    global _memory_store
    _memory_store = [e for e in _memory_store if e["id"] != employee_id]
    return {"ok": True}


# ── Metrics / Report Card ────────────────────────────────────────────────────


_RECENT_TASK_LIMIT = 20


def _fallback_metrics_from_memory(employee_id: str) -> dict:
    """Derive metrics from the in-memory chat store.

    Used when the DB is unavailable (or for very old sessions predating the
    ``task_runs`` table). Imports ``_chats`` lazily because ``server.py``
    imports this module during app setup.
    """
    try:
        from server import _chats  # type: ignore
    except Exception:
        _chats = {}

    emp = next((e for e in _memory_store if e.get("id") == employee_id), None)
    session_ids = (emp or {}).get("chatSessionIds") or []
    runs: list[dict] = []
    for sid in session_ids:
        chat = _chats.get(sid)
        if chat:
            runs.extend(task_runs_from_chat(chat))

    def _sort_key(run):
        ts = run.get("started_at")
        if isinstance(ts, datetime):
            return ts
        return datetime.min.replace(tzinfo=timezone.utc)

    runs.sort(key=_sort_key, reverse=True)

    def _iso(ts):
        return ts.isoformat() if isinstance(ts, datetime) else ts

    return {
        "employee_id": employee_id,
        "aggregate": aggregate_task_runs(runs),
        "recent": [
            {**r, "started_at": _iso(r.get("started_at")), "ended_at": _iso(r.get("ended_at"))}
            for r in runs[:_RECENT_TASK_LIMIT]
        ],
        "source": "memory",
    }


def _task_run_prompt_from_chat(session_id: str, task_index: int) -> str | None:
    try:
        from server import _chats  # type: ignore
    except Exception:
        return None

    chat = _chats.get(session_id)
    if not chat:
        return None

    current_index = -1
    for message in chat.get("messages") or []:
        if message.get("type") == "user":
            current_index += 1
            if current_index == task_index:
                return message.get("content")
    return None


def _trajectory_summary(run: dict, tree) -> dict:
    flat = flatten_action_nodes(tree)
    answer_nodes = [
        node for node in flat
        if node.state.extra.get("event_type") in {"answer", "chat_response", "error"}
    ]
    final_status = answer_nodes[-1].status if answer_nodes else tree.status
    return {
        "n_tool_calls": int(run.get("n_tool_calls") or 0),
        "n_trials": int(run.get("n_trials") or 1),
        "duration_ms": int(run.get("duration_ms") or 0),
        "tool_histogram": run.get("tool_histogram") or {},
        "status": final_status or "unknown",
    }


@router.get("/{employee_id}/metrics")
async def employee_metrics(employee_id: str):
    """Return aggregate + recent task-run metrics for the report card.

    Reads from the ``task_runs`` table when the DB is available; otherwise
    falls back to deriving runs from the in-memory chat transcript so older
    sessions and DB-less dev environments still render a useful card.
    """
    if _db_available:
        from db.engine import async_session
        from db.models import Employee, TaskRun
        from sqlalchemy import select

        emp_uuid = _parse_uuid(employee_id)
        async with async_session() as session:
            emp_row = (
                await session.execute(
                    select(Employee).where(Employee.id == emp_uuid)
                )
            ).scalar_one_or_none()
            if emp_row is None:
                raise HTTPException(404, "Employee not found")

            rows = (
                await session.execute(
                    select(TaskRun)
                    .where(TaskRun.employee_id == emp_uuid)
                    .order_by(TaskRun.started_at.desc())
                )
            ).scalars().all()

        runs = [serialize_task_run(r) for r in rows]
        return {
            "employee_id": employee_id,
            "aggregate": aggregate_task_runs(runs),
            "recent": runs[:_RECENT_TASK_LIMIT],
            "source": "db",
        }

    emp = next((e for e in _memory_store if e.get("id") == employee_id), None)
    if emp is None:
        raise HTTPException(404, "Employee not found")
    return _fallback_metrics_from_memory(employee_id)


@router.get("/{employee_id}/task_runs/{session_id}/{task_index}/trajectory")
async def employee_task_trajectory(employee_id: str, session_id: str, task_index: int):
    if _db_available:
        from db.engine import async_session
        from db.models import Employee, TaskRun
        from sqlalchemy import select

        emp_uuid = _parse_uuid(employee_id)
        async with async_session() as session:
            emp_row = (
                await session.execute(
                    select(Employee).where(Employee.id == emp_uuid)
                )
            ).scalar_one_or_none()
            if emp_row is None:
                raise HTTPException(404, "Employee not found")

            row = (
                await session.execute(
                    select(TaskRun).where(
                        TaskRun.employee_id == emp_uuid,
                        TaskRun.session_id == session_id,
                        TaskRun.task_index == task_index,
                    )
                )
            ).scalar_one_or_none()

        if row is None:
            raise HTTPException(404, "Task run not found")

        run = serialize_task_run(row)
        raw_events = run.get("raw_events") or []
        if not raw_events:
            try:
                from server import _chats  # type: ignore
            except Exception:
                _chats = {}

            chat = _chats.get(session_id)
            if chat is not None:
                live_run = next(
                    (
                        r for r in task_runs_from_chat(chat)
                        if r.get("session_id") == session_id and r.get("task_index") == task_index
                    ),
                    None,
                )
                if live_run is not None:
                    run = live_run
                    raw_events = live_run.get("raw_events") or []

        if not raw_events:
            raise HTTPException(
                status_code=410,
                detail={
                    "available": False,
                    "reason": "trajectory_not_persisted",
                },
            )

        action_nodes, trial_boundaries = build_nodes_from_events(raw_events)
        tree = segment_nodes(action_nodes, trial_boundaries)
        prompt = (
            run.get("full_prompt")
            or _task_run_prompt_from_chat(session_id, task_index)
            or run.get("prompt_preview")
            or ""
        )
        return {
            "available": True,
            "session_id": session_id,
            "task_index": task_index,
            "prompt": prompt,
            "summary": _trajectory_summary(run, tree),
            "tree": to_dict(tree),
            "raw_events": raw_events,
        }

    emp = next((e for e in _memory_store if e.get("id") == employee_id), None)
    if emp is None:
        raise HTTPException(404, "Employee not found")

    try:
        from server import _chats  # type: ignore
    except Exception:
        _chats = {}

    chat = _chats.get(session_id)
    if chat is None:
        raise HTTPException(404, "Task run not found")

    runs = task_runs_from_chat(chat)
    run = next(
        (r for r in runs if r.get("session_id") == session_id and r.get("task_index") == task_index),
        None,
    )
    if run is None:
        raise HTTPException(404, "Task run not found")

    raw_events = run.get("raw_events") or []
    action_nodes, trial_boundaries = build_nodes_from_events(raw_events)
    tree = segment_nodes(action_nodes, trial_boundaries)
    return {
        "available": True,
        "session_id": session_id,
        "task_index": task_index,
        "prompt": run.get("full_prompt") or run.get("prompt_preview") or "",
        "summary": _trajectory_summary(run, tree),
        "tree": to_dict(tree),
        "raw_events": raw_events,
    }
