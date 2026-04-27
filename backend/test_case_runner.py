from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from config import TEST_CASE_DEFAULT_MAX_LATENCY_MS
from test_case_verifier import verify_test_case_run

try:
    from reflexion_agent.agent import runtime as _agent_runtime
except Exception:  # noqa: BLE001
    _agent_runtime = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _extract_tool_name(event: Any) -> str | None:
    name = getattr(event, "tool_name", None)
    if name:
        return str(name).strip()
    event_dict = event.model_dump() if hasattr(event, "model_dump") else {}
    fallback = event_dict.get("tool_name")
    return str(fallback).strip() if fallback else None


def _compact_event(event: Any) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        event_dict = event.model_dump()
    else:
        event_dict = {}
    tool_name = _extract_tool_name(event)
    etype = event_dict.get("event_type") or event.__class__.__name__
    return {
        "event_type": str(etype),
        "tool_name": tool_name,
        "content": str(
            event_dict.get("content")
            or event_dict.get("message")
            or event_dict.get("thought")
            or ""
        )[:800],
    }


def _check_expected_tool_families(
    used_tools: set[str],
    expected_tool_families: list[str] | None,
) -> tuple[bool, str | None]:
    expected = [str(item).strip().lower() for item in (expected_tool_families or []) if str(item).strip()]
    if not expected:
        return True, None
    missing = []
    lowered_tools = {tool.lower() for tool in used_tools}
    for family in expected:
        if not any(tool.startswith(family) for tool in lowered_tools):
            missing.append(family)
    if missing:
        return False, f"missing expected tool family: {', '.join(missing)}"
    return True, None


async def run_test_case(
    *,
    case_prompt: str,
    success_criteria: str,
    hard_failure_signals: list[str],
    expected_tool_families: list[str] | None,
    employee_profile: dict[str, Any] | None,
    max_latency_ms: int | None,
    use_reflexion: bool = False,
) -> dict[str, Any]:
    started_at = _now()
    session_id = f"testcase-{uuid.uuid4().hex}"
    latency_cap_ms = int(max_latency_ms or TEST_CASE_DEFAULT_MAX_LATENCY_MS)
    compact_trajectory: list[dict[str, Any]] = []
    used_tools: set[str] = set()
    final_answer = ""
    deterministic_checks: dict[str, Any] = {}

    if _agent_runtime is None:
        finished_at = _now()
        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
            "verdict": "error",
            "verdict_source": "deterministic",
            "judge_rationale": None,
            "judge_evidence_quote": None,
            "judge_confidence": None,
            "raw_output": None,
            "failure_reason": "Agent runtime is unavailable",
            "agent_session_id": session_id,
            "deterministic_checks": {
                "finished_cleanly": False,
                "non_empty_output": False,
                "latency_within_budget": False,
                "expected_tool_families": False,
            },
        }

    def _callback(event: Any):
        compact_trajectory.append(_compact_event(event))
        tool_name = _extract_tool_name(event)
        if tool_name:
            used_tools.add(tool_name)

    def _invoke_agent() -> str:
        return _agent_runtime(
            repo_dir=os.getcwd(),
            instruction=case_prompt,
            mount_dir=os.getcwd(),
            event_callback=_callback,
            use_reflexion=use_reflexion,
            workspace=None,
            session_id=session_id,
            employee_profile=employee_profile,
        )

    try:
        final_answer = await asyncio.wait_for(
            asyncio.to_thread(_invoke_agent),
            timeout=max(1.0, latency_cap_ms / 1000.0),
        )
        finished_cleanly = True
    except asyncio.TimeoutError:
        finished_at = _now()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "verdict": "timeout",
            "verdict_source": "deterministic",
            "judge_rationale": None,
            "judge_evidence_quote": None,
            "judge_confidence": None,
            "raw_output": final_answer or None,
            "failure_reason": "agent runtime exceeded latency cap",
            "agent_session_id": session_id,
            "deterministic_checks": {
                "finished_cleanly": False,
                "non_empty_output": False,
                "latency_within_budget": False,
                "expected_tool_families": False,
            },
        }
    except Exception as exc:  # noqa: BLE001
        finished_at = _now()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "verdict": "error",
            "verdict_source": "deterministic",
            "judge_rationale": None,
            "judge_evidence_quote": None,
            "judge_confidence": None,
            "raw_output": final_answer or None,
            "failure_reason": str(exc),
            "agent_session_id": session_id,
            "deterministic_checks": {
                "finished_cleanly": False,
                "non_empty_output": False,
                "latency_within_budget": False,
                "expected_tool_families": False,
            },
        }

    finished_at = _now()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    non_empty_output = bool((final_answer or "").strip())
    latency_within_budget = duration_ms <= latency_cap_ms
    tool_family_ok, tool_family_failure = _check_expected_tool_families(
        used_tools, expected_tool_families
    )
    deterministic_checks = {
        "finished_cleanly": finished_cleanly,
        "non_empty_output": non_empty_output,
        "latency_within_budget": latency_within_budget,
        "expected_tool_families": tool_family_ok,
        "used_tools": sorted(used_tools),
    }

    if not non_empty_output:
        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "verdict": "fail",
            "verdict_source": "deterministic",
            "judge_rationale": None,
            "judge_evidence_quote": None,
            "judge_confidence": None,
            "raw_output": final_answer or None,
            "failure_reason": "empty final output",
            "agent_session_id": session_id,
            "deterministic_checks": deterministic_checks,
        }
    if not latency_within_budget:
        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "verdict": "fail",
            "verdict_source": "deterministic",
            "judge_rationale": None,
            "judge_evidence_quote": None,
            "judge_confidence": None,
            "raw_output": final_answer,
            "failure_reason": "latency budget exceeded",
            "agent_session_id": session_id,
            "deterministic_checks": deterministic_checks,
        }
    if not tool_family_ok:
        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "verdict": "fail",
            "verdict_source": "deterministic",
            "judge_rationale": None,
            "judge_evidence_quote": None,
            "judge_confidence": None,
            "raw_output": final_answer,
            "failure_reason": tool_family_failure,
            "agent_session_id": session_id,
            "deterministic_checks": deterministic_checks,
        }

    judged = await verify_test_case_run(
        case_prompt=case_prompt,
        success_criteria=success_criteria,
        hard_failure_signals=hard_failure_signals,
        final_answer=final_answer,
        compact_trajectory=compact_trajectory,
    )
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "verdict": judged["verdict"],
        "verdict_source": "llm_judge",
        "judge_rationale": judged["rationale"],
        "judge_evidence_quote": judged["evidence_quote"],
        "judge_confidence": judged["confidence"],
        "raw_output": final_answer,
        "failure_reason": None if judged["verdict"] == "pass" else "judge_failed_criteria",
        "agent_session_id": session_id,
        "deterministic_checks": deterministic_checks,
    }
