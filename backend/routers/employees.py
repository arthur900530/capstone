"""Employee CRUD router with in-memory fallback when DB is unavailable."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import re
import shutil
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import yaml
from config import SKILL_SELECTION_MODEL
from config import TEST_CASE_DEFAULT_MAX_LATENCY_MS, TEST_CASE_MIN_LATENCY_MS
from test_case_generator import generate_test_cases
from test_case_runner import run_test_case
from workflow import compute_workflow_completion, load_workflow

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
from trajectory_llm import annotate_tree, apply_annotations, _action_subgoal
from trajectory_workflow_align import align_trajectory_to_workflow

router = APIRouter(prefix="/api/employees", tags=["employees"])

_db_available = False
_memory_store: list[dict] = []
_test_case_memory_store: dict[str, list[dict[str, Any]]] = {}
_test_case_run_memory_store: dict[str, list[dict[str, Any]]] = {}
# Captured agent event stream per test-case run, keyed by the run's id (the
# DB row's UUID string, or the in-memory uuid). Memory-only by design — events
# are large and only useful for debugging the latest run; they vanish on
# server restart, which the events drawer surfaces gracefully.
_test_case_run_events: dict[str, list[dict[str, Any]]] = {}
_test_case_run_transcripts: dict[str, str] = {}


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
            max_completion_tokens=600,
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
    # doesn't spin forever on a stalled upstream. ``max_completion_tokens`` bounds the
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
            max_completion_tokens=1500,
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


def _parse_case_uuid(case_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(case_id)
    except ValueError:
        raise HTTPException(400, "Invalid test case ID format")


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


class TestCaseUpdate(BaseModel):
    title: str | None = None
    prompt: str | None = None
    success_criteria: str | None = None
    hard_failure_signals: list[str] | None = None
    expected_tool_families: list[str] | None = None
    max_latency_ms: int | None = Field(default=None, gt=0)
    status: str | None = None
    # Optional. When set, the LLM-as-judge prompt for this test case
    # includes the skill's expected workflow so the verdict scores
    # per-step adherence. Pass an empty string to clear the link.
    skill_id: str | None = None


def _serialize_test_case(row) -> dict:
    skill_id_value = getattr(row, "skill_id", None)
    skill_obj = getattr(row, "skill", None)
    return {
        "id": str(row.id),
        "employee_id": str(row.employee_id),
        "skill_id": str(skill_id_value) if skill_id_value else None,
        "skill_slug": getattr(skill_obj, "slug", None) if skill_obj else None,
        "skill_name": getattr(skill_obj, "display_name", None) if skill_obj else None,
        "title": row.title,
        "prompt": row.prompt,
        "success_criteria": row.success_criteria,
        "hard_failure_signals": row.hard_failure_signals or [],
        "expected_tool_families": row.expected_tool_families or [],
        "max_latency_ms": row.max_latency_ms,
        "generated_by_model": row.generated_by_model or "",
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_test_case_run(row, *, expected_workflow: dict | None = None) -> dict:
    workflow_alignment = getattr(row, "workflow_alignment", None)
    workflow_completion = (
        compute_workflow_completion(expected_workflow, workflow_alignment)
        if expected_workflow and workflow_alignment
        else None
    )
    return {
        "id": str(row.id),
        "test_case_id": str(row.test_case_id),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": int(row.duration_ms or 0),
        "verdict": row.verdict,
        "verdict_source": row.verdict_source,
        "judge_rationale": row.judge_rationale,
        "judge_evidence_quote": row.judge_evidence_quote,
        "judge_confidence": row.judge_confidence,
        "raw_output": row.raw_output,
        "failure_reason": row.failure_reason,
        "agent_session_id": row.agent_session_id,
        "deterministic_checks": row.deterministic_checks or {},
        "workflow_alignment": workflow_alignment,
        "workflow_completion": workflow_completion,
    }


async def _assert_employee_exists(employee_id: str) -> dict:
    if _db_available:
        from db.engine import async_session
        from db.models import Employee
        from sqlalchemy import select

        async with async_session() as session:
            row = (
                await session.execute(
                    select(Employee).where(Employee.id == _parse_uuid(employee_id))
                )
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(404, "Employee not found")
            return _row_to_dict(row)

    emp = next((e for e in _memory_store if e.get("id") == employee_id), None)
    if emp is None:
        raise HTTPException(404, "Employee not found")
    return emp


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


# ── Auto Tests ───────────────────────────────────────────────────────────────


@router.post("/{employee_id}/test_cases/generate")
async def generate_employee_test_cases(employee_id: str, count: int = 5):
    employee = await _assert_employee_exists(employee_id)
    skill_ids = employee.get("skillIds") or []
    plugin_ids = employee.get("pluginIds") or []
    skill_summaries = [{"id": sid, "name": sid, "description": ""} for sid in skill_ids]
    plugin_summaries = [{"id": pid, "name": pid, "description": ""} for pid in plugin_ids]

    try:
        generated_cases, generated_model = await generate_test_cases(
            employee_description=employee.get("description") or "",
            employee_task=employee.get("task") or "",
            skills=skill_summaries,
            plugins=plugin_summaries,
            count=count,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Test case generation failed for employee=%s", employee_id)
        raise HTTPException(
            status_code=502,
            detail=f"Test case generation failed: {exc}",
        ) from exc

    if _db_available:
        from db.engine import async_session
        from db.models import TestCase

        created: list[dict] = []
        async with async_session() as session:
            for item in generated_cases:
                row = TestCase(
                    employee_id=_parse_uuid(employee_id),
                    title=item["title"],
                    prompt=item["prompt"],
                    success_criteria=item["success_criteria"],
                    hard_failure_signals=item["hard_failure_signals"],
                    expected_tool_families=item.get("expected_tool_families") or [],
                    max_latency_ms=item["max_latency_ms"],
                    generated_by_model=generated_model,
                    status="draft",
                )
                session.add(row)
                await session.flush()
                created.append(_serialize_test_case(row))
            await session.commit()
        return {"employee_id": employee_id, "cases": created}

    created = []
    store = _test_case_memory_store.setdefault(employee_id, [])
    now_iso = datetime.now(timezone.utc).isoformat()
    for item in generated_cases:
        case_id = str(uuid.uuid4())
        entry = {
            "id": case_id,
            "employee_id": employee_id,
            "title": item["title"],
            "prompt": item["prompt"],
            "success_criteria": item["success_criteria"],
            "hard_failure_signals": item["hard_failure_signals"],
            "expected_tool_families": item.get("expected_tool_families") or [],
            "max_latency_ms": item["max_latency_ms"],
            "generated_by_model": generated_model,
            "status": "draft",
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        store.append(entry)
        created.append(entry)
    return {"employee_id": employee_id, "cases": created}


@router.get("/{employee_id}/test_cases")
async def list_employee_test_cases(employee_id: str):
    await _assert_employee_exists(employee_id)
    if _db_available:
        from db.engine import async_session
        from db.models import TestCase
        from sqlalchemy import select

        async with async_session() as session:
            rows = (
                await session.execute(
                    select(TestCase)
                    .where(TestCase.employee_id == _parse_uuid(employee_id))
                    .order_by(TestCase.created_at.desc())
                )
            ).scalars().all()
        return {"employee_id": employee_id, "cases": [_serialize_test_case(r) for r in rows]}

    rows = sorted(
        _test_case_memory_store.get(employee_id, []),
        key=lambda row: row.get("created_at") or "",
        reverse=True,
    )
    return {"employee_id": employee_id, "cases": rows}


@router.patch("/{employee_id}/test_cases/{case_id}")
async def update_employee_test_case(employee_id: str, case_id: str, body: TestCaseUpdate):
    await _assert_employee_exists(employee_id)
    # Don't drop ``skill_id`` when explicitly cleared (empty string ``""``
    # means "unlink the skill"); only drop it when the caller omitted it.
    updates = body.model_dump(exclude_unset=True)

    raw_skill_id = updates.pop("skill_id", None) if "skill_id" in updates else "__unset__"

    if _db_available:
        from db.engine import async_session
        from db.models import Skill, TestCase
        from sqlalchemy import select

        resolved_skill_uuid: uuid.UUID | None = None
        if raw_skill_id != "__unset__" and raw_skill_id:
            try:
                resolved_skill_uuid = uuid.UUID(str(raw_skill_id))
            except (ValueError, TypeError):
                raise HTTPException(400, "skill_id is not a valid UUID")

        async with async_session() as session:
            row = (
                await session.execute(
                    select(TestCase).where(
                        TestCase.id == _parse_case_uuid(case_id),
                        TestCase.employee_id == _parse_uuid(employee_id),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(404, "Test case not found")
            if raw_skill_id != "__unset__":
                if resolved_skill_uuid is not None:
                    skill_row = (
                        await session.execute(
                            select(Skill).where(Skill.id == resolved_skill_uuid)
                        )
                    ).scalar_one_or_none()
                    if skill_row is None:
                        raise HTTPException(404, "Linked skill not found")
                    row.skill_id = resolved_skill_uuid
                else:
                    row.skill_id = None
            for key, value in updates.items():
                setattr(row, key, value)
            await session.commit()
            await session.refresh(row)
            return _serialize_test_case(row)

    cases = _test_case_memory_store.get(employee_id, [])
    row = next((item for item in cases if item.get("id") == case_id), None)
    if row is None:
        raise HTTPException(404, "Test case not found")
    if raw_skill_id != "__unset__":
        # In-memory mode keeps the bare id; we don't resolve a slug here
        # because the in-memory path does not exercise the LLM judge with
        # a workflow today (no DB-backed Skill table to query).
        row["skill_id"] = str(raw_skill_id) if raw_skill_id else None
    row.update(updates)
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    return row


@router.delete("/{employee_id}/test_cases/{case_id}")
async def delete_employee_test_case(employee_id: str, case_id: str):
    await _assert_employee_exists(employee_id)
    if _db_available:
        from db.engine import async_session
        from db.models import TestCase
        from sqlalchemy import select

        async with async_session() as session:
            row = (
                await session.execute(
                    select(TestCase).where(
                        TestCase.id == _parse_case_uuid(case_id),
                        TestCase.employee_id == _parse_uuid(employee_id),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(404, "Test case not found")
            await session.delete(row)
            await session.commit()
            return {"ok": True}

    cases = _test_case_memory_store.get(employee_id, [])
    _test_case_memory_store[employee_id] = [item for item in cases if item.get("id") != case_id]
    _test_case_run_memory_store.pop(case_id, None)
    return {"ok": True}


async def _run_single_test_case(employee_id: str, case_payload: dict[str, Any]) -> dict:
    employee = await _assert_employee_exists(employee_id)

    # Reuse the pre-warmed Docker workspace (H-A fix) AND prime it with the
    # employee's assigned skills so the agent has access to the right tools.
    try:
        from server import (  # type: ignore
            _SHARED_WS,
            _owner_key,
            _prime_shared_workspace_sync,
            _resolve_workspace_for_runtime,
        )
        _ws = _SHARED_WS.get("workspace")
        _host_dir = _SHARED_WS.get("host_dir")
        _ws_lock = _SHARED_WS.get("lock")
        _server_available = True
    except Exception:
        _ws, _host_dir, _ws_lock = None, None, None
        _server_available = False

    skill_ids: list[str] = employee.get("skillIds") or []
    test_session_id = f"autotest-{uuid.uuid4().hex[:12]}"

    # When the test case targets a specific skill, load that skill's
    # workflow.json so the LLM-as-judge can score per-step adherence.
    # The test case row stores ``skill_id`` (UUID); ``skill_slug`` is the
    # resolved on-disk slug used to find ``backend/skills/<slug>/``.
    expected_workflow_dict: dict | None = None
    target_slug = case_payload.get("skill_slug")
    if target_slug:
        try:
            wf = await asyncio.to_thread(load_workflow, target_slug)
            if wf is not None:
                expected_workflow_dict = wf.to_dict()
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to load workflow for skill slug=%s; running without it",
                target_slug,
            )

    # Build a temp workspace directory containing the employee's skill packages.
    # This runs outside the lock (pure disk I/O, no Docker interaction).
    effective_mount: str | None = None
    cleanup_dirs: list[str] = []
    if _server_available and _host_dir:
        try:
            effective_mount, cleanup_dirs = await asyncio.to_thread(
                _resolve_workspace_for_runtime,
                test_session_id,
                None,
                skill_ids or None,
            )
        except Exception:
            logger.warning("Failed to resolve skill workspace for test run; continuing without skills")
            effective_mount, cleanup_dirs = None, []

    async def _prime_and_run() -> dict:
        """Prime the shared workspace with the employee's skills, then run the agent.
        Must be called while the caller already holds _ws_lock (if any)."""
        primed_skills: list[str] = []
        if _server_available and _host_dir:
            try:
                okey = _owner_key(test_session_id, None, skill_ids)
                await asyncio.to_thread(
                    _prime_shared_workspace_sync,
                    test_session_id,
                    effective_mount,
                    None,
                    cleanup_dirs,
                    okey,
                )
                primed_skills = skill_ids
            except Exception:
                logger.warning("Workspace priming failed; continuing with unprimed workspace")
        # region agent log
        import json as _j, time as _t
        _log_path = "/Users/hinkitericwong/Library/Mobile Documents/com~apple~CloudDocs/Personal - HKEW/Education/Carnegie Mellon University/Classes/4. 2026 Spring/11-699 Capstone/Capstone Frontend/.cursor/debug-3f5e2b.log"
        try:
            with open(_log_path, "a") as _lf:
                _lf.write(_j.dumps({"sessionId": "3f5e2b", "timestamp": int(_t.time() * 1000), "location": "employees.py:_prime_and_run", "message": "workspace primed for test run", "data": {"skill_ids": skill_ids, "primed_skills": primed_skills, "effective_mount": effective_mount, "host_dir": _host_dir}}) + "\n")
        except Exception:
            pass
        # endregion

        return await run_test_case(
            case_prompt=case_payload["prompt"],
            success_criteria=case_payload["success_criteria"],
            hard_failure_signals=case_payload.get("hard_failure_signals") or [],
            expected_tool_families=case_payload.get("expected_tool_families") or [],
            employee_profile={
                "name": employee.get("name"),
                "position": employee.get("position"),
                "task": employee.get("task"),
            },
            max_latency_ms=max(
                case_payload.get("max_latency_ms") or TEST_CASE_DEFAULT_MAX_LATENCY_MS,
                TEST_CASE_MIN_LATENCY_MS,
            ),
            use_reflexion=bool(employee.get("useReflexion")),
            workspace=_ws,
            host_dir=_host_dir,
            # Lock is managed by _run_single_test_case; pass None to avoid
            # run_test_case trying to acquire it a second time.
            workspace_lock=None,
            expected_workflow=expected_workflow_dict,
        )

    try:
        if _ws_lock is not None:
            async with _ws_lock:
                run_result = await _prime_and_run()
        else:
            run_result = await _prime_and_run()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Test case run failed case_id=%s employee=%s", case_payload.get("id"), employee_id)
        raise HTTPException(
            status_code=502,
            detail=f"Test case run failed: {exc}",
        ) from exc

    # Pull events and transcript out before any persistence work — the DB
    # schema doesn't store them and the memory dict is keyed separately.
    captured_events: list[dict[str, Any]] = run_result.get("events") or []
    captured_transcript: str = run_result.get("transcript") or ""

    if _db_available:
        from db.engine import async_session
        from db.models import TestCaseRun

        async with async_session() as session:
            row = TestCaseRun(
                test_case_id=uuid.UUID(case_payload["id"]),
                started_at=run_result["started_at"],
                finished_at=run_result["finished_at"],
                duration_ms=run_result["duration_ms"],
                verdict=run_result["verdict"],
                verdict_source=run_result["verdict_source"],
                judge_rationale=run_result["judge_rationale"],
                judge_evidence_quote=run_result["judge_evidence_quote"],
                judge_confidence=run_result["judge_confidence"],
                raw_output=run_result["raw_output"],
                failure_reason=run_result["failure_reason"],
                agent_session_id=run_result["agent_session_id"],
                deterministic_checks=run_result["deterministic_checks"],
                workflow_alignment=run_result.get("workflow_alignment"),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            run_dict = _serialize_test_case_run(
                row, expected_workflow=expected_workflow_dict
            )
            _test_case_run_events[run_dict["id"]] = captured_events
            _test_case_run_transcripts[run_dict["id"]] = captured_transcript
            return run_dict

    run_entry = {
        "id": str(uuid.uuid4()),
        "test_case_id": case_payload["id"],
        "started_at": run_result["started_at"].isoformat(),
        "finished_at": run_result["finished_at"].isoformat() if run_result.get("finished_at") else None,
        "duration_ms": run_result["duration_ms"],
        "verdict": run_result["verdict"],
        "verdict_source": run_result["verdict_source"],
        "judge_rationale": run_result["judge_rationale"],
        "judge_evidence_quote": run_result["judge_evidence_quote"],
        "judge_confidence": run_result["judge_confidence"],
        "raw_output": run_result["raw_output"],
        "failure_reason": run_result["failure_reason"],
        "agent_session_id": run_result["agent_session_id"],
        "deterministic_checks": run_result["deterministic_checks"],
        "workflow_alignment": run_result.get("workflow_alignment"),
        "workflow_completion": run_result.get("workflow_completion"),
    }
    _test_case_run_memory_store.setdefault(case_payload["id"], []).append(run_entry)
    _test_case_run_events[run_entry["id"]] = captured_events
    _test_case_run_transcripts[run_entry["id"]] = captured_transcript
    return run_entry


@router.post("/{employee_id}/test_cases/{case_id}/run")
async def run_employee_test_case(employee_id: str, case_id: str):
    await _assert_employee_exists(employee_id)
    if _db_available:
        from db.engine import async_session
        from db.models import TestCase
        from sqlalchemy import select

        async with async_session() as session:
            row = (
                await session.execute(
                    select(TestCase).where(
                        TestCase.id == _parse_case_uuid(case_id),
                        TestCase.employee_id == _parse_uuid(employee_id),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(404, "Test case not found")
            case_payload = _serialize_test_case(row)
    else:
        row = next(
            (item for item in _test_case_memory_store.get(employee_id, []) if item.get("id") == case_id),
            None,
        )
        if row is None:
            raise HTTPException(404, "Test case not found")
        case_payload = row

    run = await _run_single_test_case(employee_id, case_payload)
    return {"employee_id": employee_id, "case_id": case_id, "run": run}


@router.post("/{employee_id}/test_cases/run_all")
async def run_all_employee_test_cases(employee_id: str):
    await _assert_employee_exists(employee_id)
    if _db_available:
        from db.engine import async_session
        from db.models import TestCase
        from sqlalchemy import select

        async with async_session() as session:
            rows = (
                await session.execute(
                    select(TestCase)
                    .where(
                        TestCase.employee_id == _parse_uuid(employee_id),
                        TestCase.status == "draft",
                    )
                    .order_by(TestCase.created_at.asc())
                )
            ).scalars().all()
            cases = [_serialize_test_case(r) for r in rows]
    else:
        cases = [
            item
            for item in _test_case_memory_store.get(employee_id, [])
            if item.get("status") == "draft"
        ]
        cases.sort(key=lambda row: row.get("created_at") or "")

    runs = []
    for case_payload in cases:
        run = await _run_single_test_case(employee_id, case_payload)
        runs.append({"case_id": case_payload["id"], "run": run})
    return {"employee_id": employee_id, "count": len(runs), "runs": runs}


@router.get("/{employee_id}/test_cases/{case_id}/runs")
async def list_employee_test_case_runs(employee_id: str, case_id: str):
    await _assert_employee_exists(employee_id)
    if _db_available:
        from db.engine import async_session
        from db.models import TestCase, TestCaseRun
        from sqlalchemy import select

        async with async_session() as session:
            case_row = (
                await session.execute(
                    select(TestCase).where(
                        TestCase.id == _parse_case_uuid(case_id),
                        TestCase.employee_id == _parse_uuid(employee_id),
                    )
                )
            ).scalar_one_or_none()
            if case_row is None:
                raise HTTPException(404, "Test case not found")

            rows = (
                await session.execute(
                    select(TestCaseRun)
                    .where(TestCaseRun.test_case_id == _parse_case_uuid(case_id))
                    .order_by(TestCaseRun.started_at.desc())
                )
            ).scalars().all()

            target_slug = (
                case_row.skill.slug if getattr(case_row, "skill", None) else None
            )
        expected_workflow_dict: dict | None = None
        if target_slug:
            try:
                wf = await asyncio.to_thread(load_workflow, target_slug)
                if wf is not None:
                    expected_workflow_dict = wf.to_dict()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Failed to load workflow for skill slug=%s during run listing",
                    target_slug,
                )
        return {
            "employee_id": employee_id,
            "case_id": case_id,
            "runs": [
                _serialize_test_case_run(r, expected_workflow=expected_workflow_dict)
                for r in rows
            ],
        }

    rows = _test_case_run_memory_store.get(case_id, [])
    sorted_rows = sorted(rows, key=lambda row: row.get("started_at") or "", reverse=True)
    return {"employee_id": employee_id, "case_id": case_id, "runs": sorted_rows}


@router.get("/{employee_id}/test_cases/{case_id}/runs/{run_id}/events")
async def get_employee_test_case_run_events(
    employee_id: str, case_id: str, run_id: str
):
    """Return the captured agent event stream for a single test-case run.

    Events are kept in an in-memory dict (``_test_case_run_events``) keyed by
    run id and are NOT persisted to Postgres. They survive only until the
    server restarts, which is intentional: this is a debug aid for the latest
    runs, not a replayable archive. When events are unavailable (e.g. the
    server was restarted after the run completed) we return ``available:
    false`` with an empty list so the drawer can render a friendly message
    instead of a 404.
    """
    await _assert_employee_exists(employee_id)
    events = _test_case_run_events.get(run_id)
    transcript = _test_case_run_transcripts.get(run_id, "")
    if events is None:
        return {
            "employee_id": employee_id,
            "case_id": case_id,
            "run_id": run_id,
            "available": False,
            "events": [],
            "transcript": "",
            "count": 0,
        }
    return {
        "employee_id": employee_id,
        "case_id": case_id,
        "run_id": run_id,
        "available": True,
        "events": events,
        "transcript": transcript,
        "count": len(events),
    }


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


async def _slug_for_skill_id(skill_id: str) -> str | None:
    """Resolve a skill identifier (UUID or slug) to a directory slug.

    Used when hydrating cached alignments whose ``skill_slug`` field
    pre-dates persistence enrichment — we look the row up by UUID and
    fall through to treating the input as a slug when DB mode is off
    or the UUID parse fails.
    """
    if not skill_id:
        return None
    try:
        skill_uuid = uuid.UUID(skill_id)
    except (ValueError, TypeError):
        return skill_id  # Already a slug; pass through.

    if not _db_available:
        return skill_id

    from db.engine import async_session
    from db.models import Skill
    from sqlalchemy import select

    async with async_session() as session:
        row = (
            await session.execute(select(Skill).where(Skill.id == skill_uuid))
        ).scalar_one_or_none()
    return row.slug if row is not None else None


async def _hydrate_workflow_aligns(annotations: dict | None) -> list[dict]:
    """Reconstruct cached workflow alignments into a render-ready list.

    The persistence cache lives at
    ``trajectory_annotations.workflow_aligns[<skill_id>] = {action_assignments,
    workflow_alignment, workflow_completion, skill_slug}`` — it deliberately
    omits the workflow tree itself so we don't snapshot a copy that drifts
    when the user retrains the skill. On read we lazily rehydrate each
    entry by loading the on-disk ``workflow.json`` for the cached slug
    (resolving the slug from the skill_id key when the cache row pre-dates
    slug persistence), de-duping disk I/O when multiple alignments share
    the same slug, recomputing the per-leaf completion when it's missing
    or stale, and silently dropping entries whose workflow file no longer
    exists.
    """
    from workflow import compute_workflow_completion

    aligns_cache = (annotations or {}).get("workflow_aligns") or {}
    if not isinstance(aligns_cache, dict) or not aligns_cache:
        return []

    workflow_by_slug: dict[str, dict | None] = {}

    async def _load_slug(slug: str) -> dict | None:
        if slug in workflow_by_slug:
            return workflow_by_slug[slug]
        wf = await asyncio.to_thread(load_workflow, slug)
        workflow_by_slug[slug] = wf.to_dict() if wf is not None else None
        return workflow_by_slug[slug]

    out: list[dict] = []
    for skill_id, entry in aligns_cache.items():
        if not isinstance(entry, dict):
            continue
        slug = entry.get("skill_slug") or await _slug_for_skill_id(str(skill_id))
        if not slug:
            continue
        workflow_dict = await _load_slug(slug)
        if not workflow_dict:
            continue

        completion = entry.get("workflow_completion")
        if (
            not isinstance(completion, dict)
            or int(completion.get("total") or 0) <= 0
        ):
            # Recompute on the fly when the cache pre-dates the
            # completion enrichment so legacy alignments still surface
            # the right per-step rate in the drawer.
            completion = compute_workflow_completion(
                workflow_dict, entry.get("workflow_alignment")
            )

        out.append(
            {
                "skill_id": str(skill_id),
                "skill_slug": slug,
                "workflow": workflow_dict,
                "action_assignments": entry.get("action_assignments") or [],
                "workflow_alignment": entry.get("workflow_alignment"),
                "workflow_completion": completion,
            }
        )

    # Best (highest completion rate) first so the drawer can default to
    # showing the strongest alignment when multiple skills are cached.
    out.sort(
        key=lambda x: -float(((x.get("workflow_completion") or {}).get("rate") or 0.0))
    )
    return out


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
        workflow_aligns = await _hydrate_workflow_aligns(annotations)

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
            "workflow_aligns": workflow_aligns,
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
        "workflow_aligns": [],
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


@router.post("/{employee_id}/task_runs/{session_id}/{task_index}/trajectory/workflow_align")
async def align_task_trajectory(
    employee_id: str,
    session_id: str,
    task_index: int,
    skill_id: str,
    force: bool = False,
):
    """LLM-map this task run's trajectory onto a chosen skill's workflow.

    Returns ``{action_assignments, workflow_alignment, workflow_completion,
    workflow}`` so the trajectory drawer can render per-step adherence
    (same shape as ``test_case_runs.workflow_alignment``) and decorate
    each agent action with the workflow step it most closely advances.

    Results are cached under
    ``task_runs.trajectory_annotations.workflow_aligns[<skill_id>]`` so
    flipping back to the same skill in the picker is free. Pass
    ``?force=true`` to recompute.
    """
    if not _db_available:
        raise HTTPException(
            503,
            "Trajectory workflow alignment requires the database to be available.",
        )
    if not skill_id:
        raise HTTPException(400, "skill_id query parameter is required")

    from db.engine import async_session
    from db.models import Employee, Skill, TaskRun
    from sqlalchemy import select, update

    emp_uuid = _parse_uuid(employee_id)

    # Resolve the chosen skill -> on-disk slug -> workflow.json before we
    # touch the trajectory; if the skill has no workflow we want a clean
    # 404 rather than an opaque LLM error.
    try:
        skill_uuid = uuid.UUID(skill_id)
    except (ValueError, TypeError):
        skill_uuid = None

    expected_workflow_dict: dict | None = None
    skill_slug: str | None = None
    if skill_uuid is not None:
        async with async_session() as session:
            skill_row = (
                await session.execute(select(Skill).where(Skill.id == skill_uuid))
            ).scalar_one_or_none()
            if skill_row is None:
                raise HTTPException(404, "Skill not found")
            skill_slug = skill_row.slug
    else:
        # Allow callers to pass the slug directly (in-memory fallback or
        # legacy callers).
        skill_slug = skill_id

    if skill_slug:
        wf = await asyncio.to_thread(load_workflow, skill_slug)
        if wf is not None:
            expected_workflow_dict = wf.to_dict()
    if expected_workflow_dict is None:
        raise HTTPException(
            404,
            f"No workflow.json on file for skill '{skill_slug or skill_id}'",
        )

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
        cached_all = run.get("trajectory_annotations") or {}
        cached_aligns = (
            cached_all.get("workflow_aligns") if isinstance(cached_all, dict) else None
        ) or {}
        cached_for_skill = (
            cached_aligns.get(skill_id) if isinstance(cached_aligns, dict) else None
        )
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
    actions = flatten_action_nodes(tree)
    action_descriptions = [_action_subgoal(a) for a in actions]

    if cached_for_skill and not force:
        align_result = cached_for_skill
        source = "cache"
    else:
        try:
            align_result = await align_trajectory_to_workflow(
                workflow=expected_workflow_dict,
                action_descriptions=action_descriptions,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail=f"LLM workflow alignment failed: {exc}",
            ) from exc
        source = "llm"

    # Always derive completion from the freshly loaded workflow + alignment
    # so the cache row carries the headline numbers the report card uses.
    workflow_completion = compute_workflow_completion(
        expected_workflow_dict,
        align_result.get("workflow_alignment"),
    )

    if source == "llm":
        # Write-through cache nested under trajectory_annotations so we
        # don't need a new column. We also stash skill_slug + completion
        # so metrics aggregation can read them without reloading
        # workflow.json for every task on every dashboard render.
        cache_payload = {
            "action_assignments": align_result.get("action_assignments") or [],
            "workflow_alignment": align_result.get("workflow_alignment"),
            "workflow_completion": workflow_completion,
            "skill_slug": skill_slug,
        }
        async with async_session() as session:
            row = (
                await session.execute(
                    select(TaskRun).where(
                        TaskRun.employee_id == emp_uuid,
                        TaskRun.session_id == session_id,
                        TaskRun.task_index == task_index,
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                merged = dict(row.trajectory_annotations or {})
                aligns = dict(merged.get("workflow_aligns") or {})
                aligns[skill_id] = cache_payload
                merged["workflow_aligns"] = aligns
                await session.execute(
                    update(TaskRun)
                    .where(
                        TaskRun.employee_id == emp_uuid,
                        TaskRun.session_id == session_id,
                        TaskRun.task_index == task_index,
                    )
                    .values(trajectory_annotations=merged)
                )
                await session.commit()

    return {
        "available": True,
        "session_id": session_id,
        "task_index": task_index,
        "skill_id": skill_id,
        "skill_slug": skill_slug,
        "workflow": expected_workflow_dict,
        "action_assignments": align_result.get("action_assignments") or [],
        "workflow_alignment": align_result.get("workflow_alignment"),
        "workflow_completion": workflow_completion,
        "source": source,
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
