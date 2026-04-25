"""Employee CRUD router with in-memory fallback when DB is unavailable."""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import shutil
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import yaml
from config import SKILL_SELECTION_MODEL

logger = logging.getLogger(__name__)

# ── Project file storage ─────────────────────────────────────────────────────
# Files users attach to an employee (via the Project Files tab) live on the
# host disk under ``backend/uploads/employees/<employee_id>/<filename>``.
# Metadata (id, name, size, mime, uploaded_at, storage_uri) is persisted on
# the employee row in the existing ``files`` JSONB column, so no migration
# is needed. The agent workspace plumbing in ``server.py`` copies these
# files into ``/workspace/project_files/`` at the start of each turn so the
# agent's file-editor tool can read them by a predictable relative path.

_BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_FILES_ROOT = _BACKEND_DIR / "uploads" / "employees"


def _employee_files_dir(employee_id: str) -> Path:
    """Return the on-disk directory for an employee's project files."""
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", employee_id)
    return PROJECT_FILES_ROOT / safe_id


def _safe_file_name(name: str) -> str:
    """Strip path components and normalise to a safe single-segment name."""
    base = os.path.basename((name or "").strip()) or f"file_{uuid.uuid4().hex}"
    # Drop characters that would break shell paths or look suspicious.
    return re.sub(r"[\x00-\x1f/\\]", "_", base)

from metrics import (
    aggregate_task_runs,
    serialize_task_run,
    task_runs_from_chat,
)
from trajectory import build_nodes_from_events, flatten_action_nodes, segment_nodes, to_dict
from trajectory_llm import annotate_tree, apply_annotations

router = APIRouter(prefix="/api/employees", tags=["employees"])

_db_available = False
_memory_store: list[dict] = []


def set_db_available(value: bool):
    global _db_available
    _db_available = value


# Length caps on the free-form text fields. ``description`` is a short hint
# users type in the wizard — a couple sentences at most — so 2k is generous.
# ``task`` is the generated (or hand-edited) system prompt; 40k lets users
# paste a long custom prompt while still bounding a runaway LLM response.
_MAX_DESCRIPTION_CHARS = 2000
_MAX_TASK_CHARS = 40000


class EmployeeCreate(BaseModel):
    name: str
    position: str = ""
    # Short free-form hint the user types in the wizard. When present, the
    # backend expands it into a full system prompt and stores the result in
    # ``task``. Legacy callers that still send ``task`` directly keep working.
    description: str = Field(default="", max_length=_MAX_DESCRIPTION_CHARS)
    task: str = Field(default="", max_length=_MAX_TASK_CHARS)
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
    description: str | None = Field(default=None, max_length=_MAX_DESCRIPTION_CHARS)
    task: str | None = Field(default=None, max_length=_MAX_TASK_CHARS)
    pluginIds: list[str] | None = None
    skillIds: list[str] | None = None
    model: str | None = None
    useReflexion: bool | None = None
    maxTrials: int | None = None
    confidenceThreshold: float | None = None
    chatSessionIds: list[str] | None = None
    files: list[dict] | None = None
    lastActiveAt: str | None = None


class SkillSuggestionRequest(BaseModel):
    description: str = Field(default="", max_length=_MAX_DESCRIPTION_CHARS)


# ── System-prompt generation ────────────────────────────────────────────────
# The wizard's "Describe" step used to flow straight into the system prompt.
# Now the backend expands that short hint with an OpenAI call so users get a
# coherent multi-paragraph system prompt by default. They can edit either the
# description or the generated prompt later from the "System Prompt" tab.

_SYSTEM_PROMPT_META = (
    "You are writing the system prompt for an AI employee. "
    "The user has given you a short description of the employee's role. "
    "Expand it into a clear, professional system prompt (2-4 paragraphs) telling "
    "the employee who they are, what expertise they have, how they should behave, "
    "and the kinds of tasks they should excel at. Output only the prompt text — "
    "no markdown headers, no quotes, no preamble."
)

_SKILL_SELECTION_PROMPT = (
    "You are selecting the most relevant skills for an AI employee. "
    "Given the employee description and a list of candidate skills with ids, names, "
    "and descriptions, choose only the skills that are clearly useful for the role. "
    "Return strict JSON with the shape "
    '{"skill_ids":["id1","id2"],"reason":"short explanation"}. '
    "Prefer precision over recall. Return an empty array if none fit."
)

# Used when the user's configured chat model isn't an OpenAI model we can call
# directly (e.g. ``google/gemini-2.5-flash``). Generation goes through OpenAI,
# while the employee continues to chat with whichever model they picked.
_FALLBACK_PROMPT_MODEL = "gpt-4o-mini"


def _resolve_openai_model(model: str) -> str:
    """Turn a user-facing model id into something OpenAI's API will accept.

    - ``openai/gpt-5.4`` → ``gpt-5.4`` (strip provider prefix).
    - ``openai/openai/gpt-4o`` → ``gpt-4o`` (strip repeated prefixes).
    - ``gpt-5.4-nano-2026-03-17`` → unchanged.
    - ``google/gemini-2.5-flash`` → ``_FALLBACK_PROMPT_MODEL`` (non-OpenAI).
    - ``openai/`` or ``/`` or ``""`` / ``None`` → ``_FALLBACK_PROMPT_MODEL``.
    """
    raw = (model or "").strip()
    if not raw:
        return _FALLBACK_PROMPT_MODEL
    while "/" in raw:
        provider, _, bare = raw.partition("/")
        if provider.lower() != "openai":
            return _FALLBACK_PROMPT_MODEL
        raw = bare
    return raw or _FALLBACK_PROMPT_MODEL


def _parse_skill_frontmatter(definition: str) -> dict:
    text = definition or ""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}


def _skill_candidate_from_dict(skill: dict) -> dict | None:
    skill_id = str(skill.get("id") or skill.get("slug") or "").strip()
    if not skill_id:
        return None

    definition = skill.get("definition") or ""
    meta = _parse_skill_frontmatter(definition) if definition else {}
    description = (
        str(skill.get("description") or "").strip()
        or str(meta.get("description") or "").strip()
    )
    name = (
        str(skill.get("name") or "").strip()
        or str(meta.get("name") or "").strip()
        or skill_id
    )
    return {
        "id": skill_id,
        "name": name,
        "description": description,
    }


async def _list_skill_candidates() -> list[dict]:
    if _db_available:
        from db.engine import async_session
        from services import skill_service

        async with async_session() as session:
            skills = await skill_service.list_skills(session)
        candidates = [_skill_candidate_from_dict(skill) for skill in skills]
        return [candidate for candidate in candidates if candidate]

    import server

    candidates = [_skill_candidate_from_dict(skill) for skill in server._SKILLS.values()]
    return [candidate for candidate in candidates if candidate]


def _normalize_selected_skill_ids(skill_ids: object, candidates: list[dict]) -> list[str]:
    if not isinstance(skill_ids, list):
        return []
    allowed_ids = {candidate["id"] for candidate in candidates}
    seen: set[str] = set()
    selected: list[str] = []
    for item in skill_ids:
        skill_id = str(item or "").strip()
        if not skill_id or skill_id not in allowed_ids or skill_id in seen:
            continue
        seen.add(skill_id)
        selected.append(skill_id)
    return selected


async def _auto_select_skills(description: str) -> list[str]:
    desc = (description or "").strip()
    if not desc:
        return []

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("Skipping auto skill selection: OPENAI_API_KEY not configured")
        return []

    candidates = await _list_skill_candidates()
    if not candidates:
        return []

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, timeout=30.0)
    payload = {
        "employee_description": desc,
        "skills": candidates,
    }

    try:
        target_model = _resolve_openai_model(SKILL_SELECTION_MODEL)
        resp = await client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": _SKILL_SELECTION_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
            ],
            temperature=0.1,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
    except Exception:
        logger.exception("Automatic skill selection failed (model=%s)", target_model)
        return []

    content = ""
    if resp.choices and resp.choices[0].message:
        content = (resp.choices[0].message.content or "").strip()
    if not content:
        return []

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Automatic skill selection returned non-JSON content")
        return []

    selected = _normalize_selected_skill_ids(parsed.get("skill_ids"), candidates)
    logger.info(
        "Automatic skill selection chose %d skill(s): %s",
        len(selected),
        ", ".join(selected) or "(none)",
    )
    return selected


@router.post("/suggest-skills")
async def suggest_skills(body: SkillSuggestionRequest):
    return {"skillIds": await _auto_select_skills(body.description or "")}


async def _generate_system_prompt(description: str, model: str) -> str:
    """Expand ``description`` into a full system prompt via OpenAI.

    Called by ``create_employee`` so the wizard's short hint becomes a proper
    persona prompt before it lands on the employee row. Raises 503 when the
    OpenAI key is missing or the API call fails, so the frontend can surface
    the error instead of silently writing an empty ``task``.
    """
    desc = (description or "").strip()
    if not desc:
        return ""

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "OPENAI_API_KEY is not configured on the backend — cannot "
                "generate a system prompt from the description."
            ),
        )

    from openai import AsyncOpenAI

    # ``timeout`` bounds a hung OpenAI call so the wizard's submit button
    # doesn't spin forever on a stalled upstream. ``max_tokens`` bounds the
    # response size so a runaway model can't produce a 100KB system prompt.
    client = AsyncOpenAI(api_key=api_key, timeout=30.0)
    target_model = _resolve_openai_model(model)

    try:
        resp = await client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT_META},
                {"role": "user", "content": desc},
            ],
            temperature=0.4,
            max_tokens=1500,
        )
    except Exception as exc:  # noqa: BLE001
        # Don't leak raw exception strings to the client — they can embed
        # request ids or organisation metadata from the OpenAI SDK. The
        # server-side traceback is in ``logger.exception`` if we need it.
        logger.exception("System-prompt generation failed (model=%s)", target_model)
        raise HTTPException(
            status_code=503,
            detail="System-prompt generation failed. Please try again.",
        ) from exc

    content = ""
    if resp.choices and resp.choices[0].message:
        content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise HTTPException(
            status_code=503,
            detail="System-prompt generation returned an empty response.",
        )
    return content


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
        "description": getattr(row, "description", "") or "",
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
    # Expand the wizard's short description into a full system prompt when the
    # caller provided one. Legacy callers that pre-compute ``task`` directly
    # keep working — we only generate when ``task`` wasn't explicitly supplied.
    # Store the description verbatim; the strip is only to decide whether
    # there's something meaningful to generate from (PATCH also preserves
    # whitespace, so CREATE matches that contract).
    description = body.description or ""
    task = body.task or ""
    if description.strip() and not task.strip():
        task = await _generate_system_prompt(description, body.model)

    if _db_available:
        from db.engine import async_session
        from db.models import Employee

        async with async_session() as session:
            emp = Employee(
                name=body.name,
                position=body.position,
                description=description,
                task=task,
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
        "description": description,
        "task": task,
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
            if body.description is not None:
                row.description = body.description
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


def _fallback_metrics_from_memory(employee_id: str, limit: int = _RECENT_TASK_LIMIT) -> dict:
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
            for r in runs[:limit]
        ],
        "recent_limit": limit,
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
async def employee_metrics(employee_id: str, limit: int = _RECENT_TASK_LIMIT):
    """Return aggregate + recent task-run metrics for the report card.

    Reads from the ``task_runs`` table when the DB is available; otherwise
    falls back to deriving runs from the in-memory chat transcript so older
    sessions and DB-less dev environments still render a useful card.
    The ``limit`` query param controls how many recent runs are returned
    alongside the aggregate (the aggregate always spans every run).
    """
    limit = max(1, min(int(limit), 100))

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
            "recent": runs[:limit],
            "recent_limit": limit,
            "source": "db",
        }

    emp = next((e for e in _memory_store if e.get("id") == employee_id), None)
    if emp is None:
        raise HTTPException(404, "Employee not found")
    return _fallback_metrics_from_memory(employee_id, limit=limit)


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

        annotations = run.get("trajectory_annotations") or {}
        tree_dict = apply_annotations(to_dict(tree), annotations)

        return {
            "available": True,
            "session_id": session_id,
            "task_index": task_index,
            "prompt": prompt,
            "summary": _trajectory_summary(run, tree),
            "tree": tree_dict,
            "raw_events": raw_events,
            "annotations": annotations,
            "annotated": bool(annotations),
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
        "annotations": {},
        "annotated": False,
    }


@router.post("/{employee_id}/task_runs/{session_id}/{task_index}/trajectory/annotate")
async def annotate_task_trajectory(
    employee_id: str,
    session_id: str,
    task_index: int,
    force: bool = False,
):
    """Run LLM goal/status annotation on the task's trajectory tree.

    Mirrors the ``induce.py`` step of ai4work-resources/profiling: for every
    ``SequenceNode`` in the segmented tree we ask the LLM to summarize a goal
    from child subgoals and judge whether the action sequence achieved it.
    Results are cached in ``task_runs.trajectory_annotations`` so subsequent
    opens of the "Processed" view are free. Pass ``?force=true`` to recompute.
    """
    if not _db_available:
        raise HTTPException(
            503, "Trajectory annotation requires the database to be available."
        )

    from db.engine import async_session
    from db.models import Employee, TaskRun
    from sqlalchemy import select, update

    emp_uuid = _parse_uuid(employee_id)
    async with async_session() as session:
        emp_row = (
            await session.execute(select(Employee).where(Employee.id == emp_uuid))
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
        cached = run.get("trajectory_annotations") or {}
        raw_events = run.get("raw_events") or []

    # Fall back to in-memory chat if the DB row predates raw-event persistence.
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
                raw_events = live_run.get("raw_events") or []

    if not raw_events:
        raise HTTPException(
            status_code=410,
            detail={"available": False, "reason": "trajectory_not_persisted"},
        )

    action_nodes, trial_boundaries = build_nodes_from_events(raw_events)
    tree = segment_nodes(action_nodes, trial_boundaries)

    if cached and not force:
        annotations = cached
    else:
        try:
            annotations = await annotate_tree(tree)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail=f"LLM annotation failed: {exc}",
            ) from exc

        # Write-through cache so we only pay once per task.
        async with async_session() as session:
            await session.execute(
                update(TaskRun)
                .where(
                    TaskRun.employee_id == emp_uuid,
                    TaskRun.session_id == session_id,
                    TaskRun.task_index == task_index,
                )
                .values(trajectory_annotations=annotations)
            )
            await session.commit()

    tree_dict = apply_annotations(to_dict(tree), annotations)
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
        "tree": tree_dict,
        "raw_events": raw_events,
        "annotations": annotations,
        "annotated": True,
        "source": "cache" if (cached and not force) else "llm",
    }


@router.post("/{employee_id}/task_runs/annotate_recent")
async def annotate_recent_task_runs(
    employee_id: str,
    limit: int = _RECENT_TASK_LIMIT,
    force: bool = False,
):
    """Backfill LLM goal annotations for this employee's recent task runs.

    Walks the N most recent ``task_runs``, runs :func:`annotate_tree` on any
    that lack cached annotations (or all of them when ``force=true``), and
    writes the results through to the ``trajectory_annotations`` column so
    the report card's goal-oriented KPIs populate. Runs concurrently with a
    small fan-out ceiling to avoid spamming the LLM endpoint.
    """
    if not _db_available:
        raise HTTPException(
            503, "Trajectory annotation requires the database to be available."
        )

    import asyncio

    from db.engine import async_session
    from db.models import Employee, TaskRun
    from sqlalchemy import select, update

    limit = max(1, min(int(limit), 50))
    emp_uuid = _parse_uuid(employee_id)

    async with async_session() as session:
        emp_row = (
            await session.execute(select(Employee).where(Employee.id == emp_uuid))
        ).scalar_one_or_none()
        if emp_row is None:
            raise HTTPException(404, "Employee not found")

        rows = (
            await session.execute(
                select(TaskRun)
                .where(TaskRun.employee_id == emp_uuid)
                .order_by(TaskRun.started_at.desc())
                .limit(limit)
            )
        ).scalars().all()

    targets = [
        row for row in rows
        if (row.raw_events and (force or not (row.trajectory_annotations or {})))
    ]

    if not targets:
        return {
            "employee_id": employee_id,
            "scanned": len(rows),
            "annotated": 0,
            "skipped_unpersisted": sum(1 for r in rows if not r.raw_events),
            "already_cached": sum(
                1 for r in rows if (r.trajectory_annotations or {}) and not force
            ),
        }

    semaphore = asyncio.Semaphore(3)  # cap LLM fan-out

    async def _one(row) -> tuple[str, int, bool, str | None]:
        async with semaphore:
            try:
                action_nodes, trial_boundaries = build_nodes_from_events(row.raw_events or [])
                tree = segment_nodes(action_nodes, trial_boundaries)
                annotations = await annotate_tree(tree)
            except Exception as exc:  # noqa: BLE001
                return row.session_id, row.task_index, False, str(exc)[:200]

        try:
            async with async_session() as session:
                await session.execute(
                    update(TaskRun)
                    .where(
                        TaskRun.employee_id == emp_uuid,
                        TaskRun.session_id == row.session_id,
                        TaskRun.task_index == row.task_index,
                    )
                    .values(trajectory_annotations=annotations)
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            return row.session_id, row.task_index, False, f"db write failed: {exc}"[:200]

        return row.session_id, row.task_index, True, None

    results = await asyncio.gather(*(_one(row) for row in targets))

    succeeded = [r for r in results if r[2]]
    failed = [{"session_id": r[0], "task_index": r[1], "error": r[3]} for r in results if not r[2]]

    return {
        "employee_id": employee_id,
        "scanned": len(rows),
        "annotated": len(succeeded),
        "failed": failed,
        "skipped_unpersisted": sum(1 for r in rows if not r.raw_events),
    }


# ── User rating (passive 1–5 per answer) ─────────────────────────────────────


class RatingUpdate(BaseModel):
    # Passive widget sends a 1–5 integer. ``None`` clears a previous rating.
    rating: int | None = Field(default=None, ge=1, le=5)


@router.put("/{employee_id}/task_runs/{session_id}/{task_index}/rating")
async def rate_task_run(
    employee_id: str,
    session_id: str,
    task_index: int,
    body: RatingUpdate,
):
    """Set (or clear) the user's 1–5 rating on a specific task run.

    Idempotent: re-rating overwrites. Returns 404 when the task_run row
    doesn't yet exist (the persist is async — frontend should retry briefly
    after a fresh answer). Returns 503 when the DB is unavailable because
    ratings are only meaningful with durable storage.
    """
    if not _db_available:
        raise HTTPException(
            503, "User ratings require the database to be available."
        )

    from db.engine import async_session
    from db.models import Employee, TaskRun
    from sqlalchemy import select, update

    emp_uuid = _parse_uuid(employee_id)
    rated_at = datetime.now(timezone.utc) if body.rating is not None else None

    async with async_session() as session:
        emp_row = (
            await session.execute(select(Employee).where(Employee.id == emp_uuid))
        ).scalar_one_or_none()
        if emp_row is None:
            raise HTTPException(404, "Employee not found")

        result = await session.execute(
            update(TaskRun)
            .where(
                TaskRun.employee_id == emp_uuid,
                TaskRun.session_id == session_id,
                TaskRun.task_index == task_index,
            )
            .values(user_rating=body.rating, user_rating_at=rated_at)
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Task run not found")
        await session.commit()

    return {
        "employee_id": employee_id,
        "session_id": session_id,
        "task_index": task_index,
        "user_rating": body.rating,
        "user_rating_at": rated_at.isoformat() if rated_at else None,
    }


@router.get("/{employee_id}/task_runs/ratings")
async def list_session_ratings(employee_id: str, session_id: str):
    """Return a ``{task_index: rating}`` map for a session.

    Used by the chat view to hydrate the passive rating widget when a user
    reopens a past conversation. Cheap read — one indexed scan.
    """
    if not _db_available:
        return {"employee_id": employee_id, "session_id": session_id, "ratings": {}}

    from db.engine import async_session
    from db.models import TaskRun
    from sqlalchemy import select

    emp_uuid = _parse_uuid(employee_id)
    async with async_session() as session:
        rows = (
            await session.execute(
                select(TaskRun.task_index, TaskRun.user_rating)
                .where(
                    TaskRun.employee_id == emp_uuid,
                    TaskRun.session_id == session_id,
                )
            )
        ).all()

    return {
        "employee_id": employee_id,
        "session_id": session_id,
        "ratings": {int(idx): int(r) for idx, r in rows if r is not None},
    }


# ── Project Files ────────────────────────────────────────────────────────────
#
# Project files are attached to an employee and get copied into the agent's
# workspace at the start of every turn, so the agent's standing-task prompt
# can reference them by a stable relative path. Unlike chat-uploaded files
# (staged per-session in /tmp), these persist on the employee record.


def _file_entry(
    file_id: str,
    name: str,
    size: int,
    mime: str,
    storage_uri: str,
    uploaded_at: str,
) -> dict:
    return {
        "id": file_id,
        "name": name,
        "size": size,
        "mime": mime or "application/octet-stream",
        "storage_uri": storage_uri,
        "uploaded_at": uploaded_at,
    }


def _resolve_and_sanitise_files(raw: list | None) -> list[dict]:
    """Normalise a list of file entries read from the DB/memory store.

    Older rows may be missing fields we later added; backfill them with safe
    defaults so downstream code can assume a complete shape.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = _safe_file_name(str(item.get("name") or ""))
        if not name:
            continue
        out.append({
            "id": str(item.get("id") or uuid.uuid4().hex),
            "name": name,
            "size": int(item.get("size") or 0),
            "mime": str(item.get("mime") or "application/octet-stream"),
            "storage_uri": str(item.get("storage_uri") or ""),
            "uploaded_at": str(item.get("uploaded_at") or ""),
        })
    return out


async def _update_files_in_store(employee_id: str, new_files: list[dict]) -> None:
    """Persist ``new_files`` as the employee's ``files`` column (or memory entry)."""
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
            row.files = new_files
            await session.commit()
        return

    emp = next((e for e in _memory_store if e["id"] == employee_id), None)
    if not emp:
        raise HTTPException(404, "Employee not found")
    emp["files"] = new_files


async def _read_files_from_store(employee_id: str) -> list[dict]:
    """Read the current files list from DB or memory fallback."""
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
            return _resolve_and_sanitise_files(row.files)

    emp = next((e for e in _memory_store if e["id"] == employee_id), None)
    if not emp:
        raise HTTPException(404, "Employee not found")
    return _resolve_and_sanitise_files(emp.get("files"))


def _unique_name(dest_dir: Path, desired: str) -> str:
    """Return ``desired`` or a suffixed variant that doesn't collide on disk.

    ``file.pdf`` → ``file.pdf`` if free, else ``file-<hash6>.pdf``.
    """
    if not (dest_dir / desired).exists():
        return desired
    stem, dot, ext = desired.partition(".")
    suffix = uuid.uuid4().hex[:6]
    return f"{stem}-{suffix}" + (f".{ext}" if dot else "")


@router.get("/{employee_id}/project_files")
async def list_project_files(employee_id: str):
    files = await _read_files_from_store(employee_id)
    return {"employee_id": employee_id, "files": files}


@router.post("/{employee_id}/project_files")
async def upload_project_files(
    employee_id: str,
    files: list[UploadFile] = File(...),
):
    """Upload one or more files and attach them to the employee record.

    Files are written to ``PROJECT_FILES_ROOT/<employee_id>/<filename>``
    (resolving on-disk name collisions with a random suffix) and appended to
    the employee's ``files`` JSONB list.
    """
    if not files:
        raise HTTPException(400, "No files provided")

    existing = await _read_files_from_store(employee_id)
    dest_dir = _employee_files_dir(employee_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    added: list[dict] = []
    for upload in files:
        raw_name = _safe_file_name(upload.filename or "")
        final_name = _unique_name(dest_dir, raw_name)
        dest_path = dest_dir / final_name

        content = await upload.read()
        try:
            dest_path.write_bytes(content)
        except OSError as exc:
            logger.exception("Failed to write project file %s", dest_path)
            raise HTTPException(500, f"Failed to save {final_name}: {exc}")

        mime = upload.content_type or (mimetypes.guess_type(final_name)[0] or "application/octet-stream")
        entry = _file_entry(
            file_id=uuid.uuid4().hex,
            name=final_name,
            size=len(content),
            mime=mime,
            storage_uri=str(dest_path),
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
        added.append(entry)

    merged = existing + added
    await _update_files_in_store(employee_id, merged)

    logger.info(
        "project_files: uploaded %d file(s) for employee=%s (total=%d)",
        len(added), employee_id, len(merged),
    )
    return {"employee_id": employee_id, "files": merged, "added": added}


@router.delete("/{employee_id}/project_files/{file_id}")
async def delete_project_file(employee_id: str, file_id: str):
    existing = await _read_files_from_store(employee_id)
    target = next((f for f in existing if f["id"] == file_id), None)
    if not target:
        raise HTTPException(404, "Project file not found")

    # Remove bytes from disk best-effort; always update the metadata row.
    storage_uri = target.get("storage_uri") or ""
    if storage_uri:
        try:
            # Only delete files that live inside our managed directory to
            # avoid a path-traversal from a malformed storage_uri wiping
            # something else on the host.
            p = Path(storage_uri).resolve()
            root = PROJECT_FILES_ROOT.resolve()
            if root in p.parents and p.exists():
                p.unlink()
        except Exception:
            logger.exception("Failed to delete project file bytes at %s", storage_uri)

    remaining = [f for f in existing if f["id"] != file_id]
    await _update_files_in_store(employee_id, remaining)
    return {"employee_id": employee_id, "files": remaining, "removed": target}


@router.get("/{employee_id}/project_files/{file_id}/raw")
async def get_project_file_raw(employee_id: str, file_id: str):
    existing = await _read_files_from_store(employee_id)
    target = next((f for f in existing if f["id"] == file_id), None)
    if not target:
        raise HTTPException(404, "Project file not found")

    storage_uri = target.get("storage_uri") or ""
    if not storage_uri:
        raise HTTPException(410, "Project file bytes are not available")

    p = Path(storage_uri).resolve()
    root = PROJECT_FILES_ROOT.resolve()
    if root not in p.parents or not p.exists():
        raise HTTPException(410, "Project file bytes are not available")

    return FileResponse(
        path=str(p),
        media_type=target.get("mime") or "application/octet-stream",
        filename=target.get("name") or p.name,
    )
