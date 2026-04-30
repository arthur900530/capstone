from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from config import TEST_CASE_DEFAULT_MAX_LATENCY_MS
from test_case_verifier import verify_test_case_run
from agent_event_utils import compact_event as _compact_event, serialize_trajectory
from workflow import compute_workflow_completion

try:
    from reflexion_agent.agent import runtime as _agent_runtime
except Exception:  # noqa: BLE001
    _agent_runtime = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _extract_tool_name(event: Any) -> str | None:
    """Return the event's tool name, if any, for deterministic-check tracking.

    We keep this thin helper local because the deterministic-checks bookkeeping
    (``used_tools`` set in ``_callback``) needs the tool name even for events
    we *don't* end up appending to the compact trajectory (e.g. when the cap
    is hit, or when ``_compact_event`` returns None for filtered events).
    """
    name = getattr(event, "tool_name", None)
    if name:
        return str(name).strip()
    event_dict = event.model_dump() if hasattr(event, "model_dump") else {}
    fallback = event_dict.get("tool_name")
    return str(fallback).strip() if fallback else None


# Hard cap on events captured per test run. Prevents a runaway agent (or a
# huge tool dump) from ballooning memory when the events drawer renders.
# 500 covers any realistic test trajectory; anything longer is truncated.
_MAX_EVENTS_PER_RUN = 500




_LOG_PATH = "/Users/hinkitericwong/Library/Mobile Documents/com~apple~CloudDocs/Personal - HKEW/Education/Carnegie Mellon University/Classes/4. 2026 Spring/11-699 Capstone/Capstone Frontend/.cursor/debug-3f5e2b.log"

def _dbg(msg: str, data: dict, hyp: str) -> None:
    import json as _json, time as _time
    entry = {"sessionId": "3f5e2b", "timestamp": int(_time.time() * 1000), "location": "test_case_runner.py", "message": msg, "hypothesisId": hyp, "data": data}
    try:
        with open(_LOG_PATH, "a") as _f:
            _f.write(_json.dumps(entry) + "\n")
    except Exception:
        pass


async def run_test_case(
    *,
    case_prompt: str,
    success_criteria: str,
    hard_failure_signals: list[str],
    expected_tool_families: list[str] | None,
    employee_profile: dict[str, Any] | None,
    max_latency_ms: int | None,
    use_reflexion: bool = False,
    # H-A fix: accept the pre-warmed shared workspace so the runner reuses the
    # existing Docker container instead of spinning up a new one each time.
    workspace: Any = None,
    host_dir: str | None = None,
    workspace_lock: Any = None,  # asyncio.Lock | None
    expected_workflow: dict | None = None,
) -> dict[str, Any]:
    started_at = _now()
    session_id = f"testcase-{uuid.uuid4().hex}"
    latency_cap_ms = int(max_latency_ms or TEST_CASE_DEFAULT_MAX_LATENCY_MS)
    effective_dir = host_dir or os.getcwd()

    # region agent log
    _dbg("run_test_case entry", {"latency_cap_ms": latency_cap_ms, "agent_runtime_available": _agent_runtime is not None, "workspace_provided": workspace is not None, "host_dir": effective_dir, "prompt_snippet": case_prompt[:80]}, "H-A,H-B,H-D")
    # endregion
    compact_trajectory: list[dict[str, Any]] = []
    raw_events: list[Any] = []
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
            "events": list(compact_trajectory),
            "transcript": serialize_trajectory(raw_events),
        }

    def _callback(event: Any):
        # Collect the raw SDK event object for serialize_trajectory() which
        # runs after the agent finishes. This list is never persisted — it's
        # consumed once and then discarded.
        if len(raw_events) < _MAX_EVENTS_PER_RUN:
            raw_events.append(event)

        # Compact events for the LLM judge. _compact_event returns None for
        # events we deliberately drop (ConversationStateUpdateEvent, etc.).
        if len(compact_trajectory) < _MAX_EVENTS_PER_RUN:
            compact = _compact_event(event)
            if compact is not None:
                compact_trajectory.append(
                    {**compact, "ts": _now().isoformat()}
                )
        tool_name = _extract_tool_name(event)
        if tool_name:
            used_tools.add(tool_name)

    def _invoke_agent() -> str:
        # region agent log
        _dbg("_invoke_agent called", {"effective_dir": effective_dir, "workspace_provided": workspace is not None}, "H-A,H-D")
        # endregion
        try:
            result = _agent_runtime(
                repo_dir=effective_dir,
                instruction=case_prompt,
                mount_dir=effective_dir,
                event_callback=_callback,
                use_reflexion=use_reflexion,
                workspace=workspace,
                session_id=session_id,
                employee_profile=employee_profile,
            )
            # region agent log
            _dbg("_invoke_agent returned", {"result_snippet": str(result)[:120] if result else "(empty)"}, "H-A,H-B")
            # endregion
            return result
        except Exception as _exc:
            # region agent log
            _dbg("_invoke_agent raised exception", {"exc_type": type(_exc).__name__, "exc_msg": str(_exc)[:300]}, "H-A,H-D")
            # endregion
            raise

    async def _run_with_timeout() -> str:
        return await asyncio.wait_for(
            asyncio.to_thread(_invoke_agent),
            timeout=max(1.0, latency_cap_ms / 1000.0),
        )

    try:
        if workspace_lock is not None:
            async with workspace_lock:
                final_answer = await _run_with_timeout()
        else:
            final_answer = await _run_with_timeout()
        finished_cleanly = True
    except asyncio.TimeoutError:
        # region agent log
        _dbg("TimeoutError fired", {"latency_cap_ms": latency_cap_ms, "events_captured": len(compact_trajectory)}, "H-B,H-C")
        # endregion
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
            "events": list(compact_trajectory),
            "transcript": serialize_trajectory(raw_events),
        }
    except Exception as exc:  # noqa: BLE001
        finished_at = _now()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        # region agent log
        _dbg("outer except caught", {"exc_type": type(exc).__name__, "exc_msg": str(exc)[:300], "duration_ms": duration_ms}, "H-A,H-C,H-D")
        # endregion
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
            "events": list(compact_trajectory),
            "transcript": serialize_trajectory(raw_events),
        }

    finished_at = _now()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    non_empty_output = bool((final_answer or "").strip())
    latency_within_budget = duration_ms <= latency_cap_ms
    deterministic_checks = {
        "finished_cleanly": finished_cleanly,
        "non_empty_output": non_empty_output,
        "latency_within_budget": latency_within_budget,
        "used_tools": sorted(used_tools),
    }
    # region agent log
    _dbg("deterministic checks complete", {
        "used_tools": sorted(used_tools),
        "non_empty_output": non_empty_output,
        "latency_within_budget": latency_within_budget,
        "duration_ms": duration_ms,
    }, "H-E,H-F,H-G")
    # endregion

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
            "events": list(compact_trajectory),
            "transcript": serialize_trajectory(raw_events),
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
            "events": list(compact_trajectory),
            "transcript": serialize_trajectory(raw_events),
        }

    try:
        judged = await verify_test_case_run(
            case_prompt=case_prompt,
            success_criteria=success_criteria,
            hard_failure_signals=hard_failure_signals,
            final_answer=final_answer,
            compact_trajectory=compact_trajectory,
            expected_workflow=expected_workflow,
        )
        # region agent log
        _dbg("llm_judge result", {
            "verdict": judged["verdict"],
            "confidence": judged["confidence"],
            "rationale": judged["rationale"][:200],
            "evidence_quote": judged["evidence_quote"][:120],
            "success_criteria": success_criteria[:150],
            "has_workflow_alignment": bool(judged.get("workflow_alignment")),
        }, "H-G")
        # endregion
    except Exception as _verifier_exc:
        # region agent log
        _dbg("llm_judge exception", {
            "exc_type": type(_verifier_exc).__name__,
            "exc_msg": str(_verifier_exc)[:300],
        }, "H-G")
        # endregion
        judged = {
            "verdict": "error",
            "rationale": f"Verifier failed: {_verifier_exc}",
            "evidence_quote": "",
            "confidence": 0.0,
            "workflow_alignment": None,
        }
    workflow_alignment = judged.get("workflow_alignment")
    workflow_completion = (
        compute_workflow_completion(expected_workflow, workflow_alignment)
        if expected_workflow and workflow_alignment
        else None
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
        "events": list(compact_trajectory),
        "transcript": serialize_trajectory(raw_events),
        "workflow_alignment": workflow_alignment,
        "workflow_completion": workflow_completion,
    }
