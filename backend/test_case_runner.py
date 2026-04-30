from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from config import TEST_CASE_DEFAULT_MAX_LATENCY_MS
from test_case_verifier import verify_test_case_run
from agent_event_utils import compact_event as _compact_event, serialize_trajectory

# Files larger than this threshold are included up to this limit with a
# truncation marker appended. This is a pure engineering guardrail against
# pathological cases (e.g. the agent writing a binary blob or a megabyte
# of log output). Normal KYC reports, CSVs, or JSON files are well under
# this limit and will always be included in full.
_WORKSPACE_FILE_CHAR_CAP = 32_000

# Hidden-directory prefixes to skip when scanning the workspace. This
# prevents the judge from being flooded with agent-internal scaffolding
# files (.agents/skills/, .openhands/, .git/, etc.).
_HIDDEN_DIR_PREFIXES = (".", "__pycache__")

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

    The OpenHands SDK uses OpenAI's ``MessageToolCall`` shape on ActionEvents:
    ``event.tool_call.function.name`` is the canonical place where the
    invoked function name lives. ``event.tool_name`` is set on most events
    but not all of them — when it's missing, the previous implementation
    silently dropped the tool from ``tools_used`` even though
    ``_compact_action_event`` in agent_event_utils could still recover it.
    Walk the canonical path before declaring "no tool name".
    """
    name = getattr(event, "tool_name", None)
    if name:
        return str(name).strip()

    # Canonical SDK path: ActionEvent.tool_call.function.name
    tool_call = getattr(event, "tool_call", None)
    if tool_call is not None:
        function = getattr(tool_call, "function", None)
        if function is not None:
            fn_name = getattr(function, "name", None)
            if fn_name:
                return str(fn_name).strip()

    # Dump fallback for non-pydantic event objects (older SDK builds, mocks).
    event_dict = event.model_dump() if hasattr(event, "model_dump") else {}
    fallback = event_dict.get("tool_name")
    if fallback:
        return str(fallback).strip()
    nested_call = event_dict.get("tool_call") or {}
    if isinstance(nested_call, dict):
        nested_fn = nested_call.get("function") or {}
        if isinstance(nested_fn, dict) and nested_fn.get("name"):
            return str(nested_fn["name"]).strip()
    return None


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


def _snapshot_workspace_filenames(host_dir: str) -> set[str]:
    """Return a set of all non-hidden file paths (relative to host_dir) that
    currently exist in the workspace.

    Called BEFORE the agent runs to establish a baseline so we can detect
    new or modified files after it finishes. Hidden directories
    (names starting with '.' or '__pycache__') are skipped entirely.
    """
    result: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(host_dir):
        # Prune hidden/internal directories in-place so os.walk doesn't
        # descend into them.
        dirnames[:] = [
            d for d in dirnames
            if not any(d.startswith(p) for p in _HIDDEN_DIR_PREFIXES)
        ]
        for fname in filenames:
            if any(fname.startswith(p) for p in _HIDDEN_DIR_PREFIXES):
                continue
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, host_dir)
            result.add(rel)
    return result


def _harvest_workspace_files(
    compact_trajectory: list[dict[str, Any]],
    host_dir: str,
    pre_run_snapshot: set[str],
) -> dict[str, str]:
    """Collect the content of files the agent wrote during the run.

    Two complementary strategies are used so neither file_editor nor
    terminal-written files are missed:

    A. Trajectory scan — extract every ``path`` arg from ``file_editor``
       events in the compact trajectory. This is the most targeted source
       and captures the agent's explicit write intent.

    B. Workspace diff — compare the current workspace against the
       ``pre_run_snapshot`` taken before the agent started. Any file that
       is new (created via terminal redirection, curl -o, python open(),
       etc.) is included even if it has no file_editor entry.

    Both sources are merged; duplicates are deduplicated by path. Content
    is capped at ``_WORKSPACE_FILE_CHAR_CAP`` chars per file to guard
    against accidental binary or enormous log files.
    """
    candidate_paths: set[str] = set()

    # Strategy A: file_editor trajectory entries
    for event in compact_trajectory:
        if (event.get("tool_name") or "").lower() in ("file_editor", "fileeditor", "fileeditortool"):
            args = event.get("args") or {}
            raw_path = args.get("path") or args.get("file_path") or ""
            if raw_path:
                # Normalize /workspace/foo.md → foo.md
                if raw_path.startswith("/workspace/"):
                    raw_path = raw_path[len("/workspace/"):]
                candidate_paths.add(raw_path.lstrip("/"))

    # Strategy B: workspace diff (catches terminal-written files)
    for dirpath, dirnames, filenames in os.walk(host_dir):
        dirnames[:] = [
            d for d in dirnames
            if not any(d.startswith(p) for p in _HIDDEN_DIR_PREFIXES)
        ]
        for fname in filenames:
            if any(fname.startswith(p) for p in _HIDDEN_DIR_PREFIXES):
                continue
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, host_dir)
            if rel not in pre_run_snapshot:
                candidate_paths.add(rel)

    workspace_files: dict[str, str] = {}
    for rel_path in sorted(candidate_paths):
        full_path = os.path.join(host_dir, rel_path)
        if not os.path.isfile(full_path):
            continue
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            if len(content) > _WORKSPACE_FILE_CHAR_CAP:
                content = (
                    content[:_WORKSPACE_FILE_CHAR_CAP]
                    + f"\n\n[...file truncated — {len(content) - _WORKSPACE_FILE_CHAR_CAP} additional chars not shown]"
                )
            workspace_files[rel_path] = content
        except OSError:
            # Binary, device, or permission-denied file — skip silently.
            pass
    return workspace_files


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
    # Telemetry accumulated throughout the run. Populated incrementally so
    # partial data is available even when the run is cut short by a timeout
    # or error. Stored as a JSONB column on TestCaseRun and included in every
    # JSON export so downstream consumers have a complete cost + behaviour
    # snapshot without re-running the agent.
    run_telemetry: dict[str, Any] = {
        "tool_call_count": 0,
        "tools_used": [],
    }

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
            "run_telemetry": run_telemetry,
            "events": list(compact_trajectory),
            "transcript": serialize_trajectory(raw_events),
        }

    # The judge reads files the agent wrote to /workspace. Without a real
    # bind-mounted host_dir those files never exist on disk, so the judge
    # would have no artifact evidence to grade against. Failing here early
    # is intentional: tests that require file output are meaningless in a
    # workspace-less environment and would produce misleadingly low scores.
    if not host_dir or not os.path.isdir(host_dir):
        finished_at = _now()
        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
            "verdict": "error",
            "verdict_source": "deterministic",
            "judge_rationale": (
                "Shared workspace is not available (host_dir is missing or not a directory). "
                "Auto-test runs require a running Docker workspace so the judge can read "
                "file artifacts the agent writes to /workspace. "
                "Ensure REAL_AGENT_ENABLED is configured and the Docker workspace started "
                "successfully before running test cases."
            ),
            "judge_evidence_quote": None,
            "judge_confidence": None,
            "raw_output": None,
            "failure_reason": "Shared workspace unavailable — set REAL_AGENT_ENABLED and ensure Docker is running",
            "agent_session_id": session_id,
            "deterministic_checks": {
                "finished_cleanly": False,
                "non_empty_output": False,
                "latency_within_budget": False,
                "expected_tool_families": False,
            },
            "run_telemetry": run_telemetry,
            "events": [],
            "transcript": "[trajectory: no events captured — workspace unavailable]",
        }

    # Snapshot the workspace before the agent runs so the post-run diff
    # can identify files the agent created via terminal (curl, python
    # open(), shell redirection, etc.) that have no file_editor event.
    pre_run_snapshot = await asyncio.to_thread(_snapshot_workspace_filenames, host_dir)

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
            run_telemetry["tool_call_count"] = run_telemetry.get("tool_call_count", 0) + 1

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
        run_telemetry["tools_used"] = sorted(used_tools)
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
            "run_telemetry": run_telemetry,
            "events": list(compact_trajectory),
            "transcript": serialize_trajectory(raw_events),
        }
    except Exception as exc:  # noqa: BLE001
        finished_at = _now()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        # region agent log
        _dbg("outer except caught", {"exc_type": type(exc).__name__, "exc_msg": str(exc)[:300], "duration_ms": duration_ms}, "H-A,H-C,H-D")
        # endregion
        run_telemetry["tools_used"] = sorted(used_tools)
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
            "run_telemetry": run_telemetry,
            "events": list(compact_trajectory),
            "transcript": serialize_trajectory(raw_events),
        }

    finished_at = _now()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    # Recover final_answer from the finish event when the runtime returns
    # an empty string (file-centric workflows where the agent writes to
    # disk and calls finish without producing conversational text).
    if not (final_answer or "").strip():
        for event in compact_trajectory:
            if event.get("is_finish") and event.get("content", "").strip():
                final_answer = event["content"].strip()
                break

    non_empty_output = bool((final_answer or "").strip())
    latency_within_budget = duration_ms <= latency_cap_ms
    deterministic_checks = {
        "finished_cleanly": finished_cleanly,
        # Kept for display/telemetry only — no longer gates the judge call.
        # File-centric agents (file_editor + finish) legitimately return an
        # empty conversational answer; the judge has workspace_files as
        # ground-truth evidence and can grade correctly regardless.
        "non_empty_output": non_empty_output,
        "latency_within_budget": latency_within_budget,
        "used_tools": sorted(used_tools),
    }
    run_telemetry["tools_used"] = sorted(used_tools)
    # region agent log
    _dbg("deterministic checks complete", {
        "used_tools": sorted(used_tools),
        "non_empty_output": non_empty_output,
        "latency_within_budget": latency_within_budget,
        "duration_ms": duration_ms,
    }, "H-E,H-F,H-G")
    # endregion

    # Harvest files the agent wrote during the run. Must happen while the
    # workspace lock is still held (i.e. before the next session evicts
    # the current bind-mount contents). This call is sync I/O so we run
    # it on a thread to avoid blocking the event loop.
    workspace_files: dict[str, str] = await asyncio.to_thread(
        _harvest_workspace_files, compact_trajectory, host_dir, pre_run_snapshot
    )
    # Store just the file paths (not content) in telemetry — the content
    # is large and already available via the export payload.
    run_telemetry["workspace_files_written"] = sorted(workspace_files.keys())

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
            "run_telemetry": run_telemetry,
            "events": list(compact_trajectory),
            "transcript": serialize_trajectory(raw_events),
        }

    try:
        # Pass the observed tool trace to the judge so it can grade WORKFLOW
        # integrity, not just output shape. We deliberately do NOT pass
        # `expected_tool_families` — empirically, naming specific skills the
        # agent "should" use was overfitting the judge to a brittle ground
        # truth. The remaining process-integrity gates (claim-without-call
        # and tool-output-fabrication) catch the same hallucinations via
        # success_criteria + final_answer + tools_used.
        judged = await verify_test_case_run(
            case_prompt=case_prompt,
            success_criteria=success_criteria,
            hard_failure_signals=hard_failure_signals,
            final_answer=final_answer,
            compact_trajectory=compact_trajectory,
            tools_used=sorted(used_tools),
            workspace_files=workspace_files,
        )
        # region agent log
        _dbg("llm_judge result", {
            "verdict": judged["verdict"],
            "confidence": judged["confidence"],
            "process_score": judged.get("process_score"),
            "output_score": judged.get("output_score"),
            "hallucination_detected": judged.get("hallucination_detected"),
            "rationale": judged["rationale"][:200],
            "evidence_quote": judged["evidence_quote"][:120],
            "success_criteria": success_criteria[:150],
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
            "process_score": None,
            "output_score": None,
            "hallucination_detected": None,
        }

    # Merge judge process/output telemetry into run_telemetry so it shows up
    # in JSON exports and on the governance dashboard alongside tool-call
    # metrics. We keep these inside run_telemetry (a JSONB column) instead of
    # adding new top-level columns — additive and backwards-compatible with
    # any rows written before this change.
    run_telemetry["process_score"] = judged.get("process_score")
    run_telemetry["output_score"] = judged.get("output_score")
    run_telemetry["hallucination_detected"] = judged.get("hallucination_detected")
    run_telemetry["expected_tool_families"] = list(expected_tool_families or [])

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
        "run_telemetry": run_telemetry,
        "events": list(compact_trajectory),
        "transcript": serialize_trajectory(raw_events),
    }
