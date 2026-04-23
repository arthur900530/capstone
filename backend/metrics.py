"""Per-employee task metrics.

A *task* is one user-turn within an employee's chat — i.e. the trajectory
between two consecutive ``user`` messages (or between the last ``user`` message
and the end of the chat). For each task we capture a small set of behavioral
signals that let the frontend report card answer questions like:

  • How many tool calls does this employee make on average?
  • How fast does it respond?
  • Which tools does it rely on the most?
  • How often does it kick off a second (reflexion) trial?

Success / step-info tracking is intentionally deferred — it needs more work to
define what counts as a success, and we want a small, opinionated v1 first.

Two call sites use this module:

  1. ``server.py`` writes a :class:`TaskRun` row at the end of each chat turn
     (see :func:`build_task_run_from_buffer`), so restarts don't wipe history.
  2. ``/api/employees/{id}/metrics`` reads those rows and aggregates them with
     :func:`aggregate_task_runs` for the report card.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Iterable


# Events that terminate a task — once we see one, the current task's buffer
# is complete. ``error`` is included so failed turns still get recorded with
# whatever metrics we accumulated up to the failure.
_TASK_TERMINAL_TYPES = frozenset({"answer", "chat_response", "error"})


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            # datetime.fromisoformat handles the ``+00:00`` suffix _now_iso uses.
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def build_task_run_from_buffer(
    *,
    user_msg: dict,
    events: list[dict],
    end_ts: datetime,
) -> dict:
    """Derive a task-run record from a streaming turn.

    ``events`` is the list of SSE event dicts emitted *after* ``user_msg`` and
    up to (and including) the terminal event. We don't require the caller to
    filter out any event types — we pick out what we need.

    The returned dict is shaped to map 1:1 onto the ``task_runs`` table columns
    (minus the surrogate ``id`` / ``created_at``).
    """
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    trials = [e for e in events if e.get("type") == "trial_start"]
    reflections = [e for e in events if e.get("type") == "reflection"]

    tool_histogram = dict(
        Counter(e.get("tool") or "unknown" for e in tool_calls)
    )

    started_at = _parse_ts(user_msg.get("timestamp")) or end_ts
    duration_ms = max(0, int((end_ts - started_at).total_seconds() * 1000))

    prompt = user_msg.get("content") or ""
    prompt_preview = prompt[:200]

    return {
        "session_id": None,  # caller fills this in
        "task_index": 0,     # caller fills this in
        "prompt_preview": prompt_preview,
        "started_at": started_at,
        "ended_at": end_ts,
        "duration_ms": duration_ms,
        "n_tool_calls": len(tool_calls),
        "n_trials": max(len(trials), 1),
        "n_reflections": len(reflections),
        "tool_histogram": tool_histogram,
    }


def task_runs_from_chat(chat: dict) -> list[dict]:
    """Reconstruct task-run records from an in-memory chat transcript.

    Used as a fallback when the DB is unavailable (or for sessions recorded
    before the ``task_runs`` table existed). Walks the chat's ``messages``
    list, splitting on ``user`` events.
    """
    runs: list[dict] = []
    messages = chat.get("messages") or []
    current_user: dict | None = None
    buffer: list[dict] = []
    task_index = 0

    def _flush(terminal_event: dict | None):
        nonlocal task_index
        if current_user is None:
            return
        # Pick an end timestamp: terminal event's ts, or the last event's,
        # or the user's own ts as a fallback (zero-duration tasks are fine).
        end_source = (
            terminal_event
            or (buffer[-1] if buffer else current_user)
        )
        end_ts = _parse_ts(end_source.get("timestamp"))
        if end_ts is None:
            end_ts = _parse_ts(current_user.get("timestamp"))
        if end_ts is None:
            return  # pathological — skip

        run = build_task_run_from_buffer(
            user_msg=current_user,
            events=buffer,
            end_ts=end_ts,
        )
        run["session_id"] = chat.get("id")
        run["task_index"] = task_index
        runs.append(run)
        task_index += 1

    for msg in messages:
        mtype = msg.get("type")
        if mtype == "user":
            _flush(terminal_event=None)
            current_user = msg
            buffer = []
            continue

        if current_user is None:
            # Stray event before any user message — ignore.
            continue

        buffer.append(msg)
        if mtype in _TASK_TERMINAL_TYPES:
            _flush(terminal_event=msg)
            current_user = None
            buffer = []

    # Trailing user message with no terminal event (turn still in flight,
    # or chat was abandoned) — still record what we have.
    if current_user is not None:
        _flush(terminal_event=None)

    return runs


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    idx = min(int(len(s) * p), len(s) - 1)
    return s[idx]


def aggregate_task_runs(runs: Iterable[dict]) -> dict:
    """Roll a list of task-run dicts up into the shape the report card wants.

    Each run dict may come from the DB (``TaskRun`` row converted via
    ``dict()``) or from :func:`task_runs_from_chat`; both shapes use the same
    field names so this function doesn't care which source produced them.
    """
    runs = list(runs)
    if not runs:
        return {
            "tasks": 0,
            "avg_tool_calls": 0.0,
            "avg_trials": 0.0,
            "avg_reflections": 0.0,
            "avg_latency_ms": 0,
            "p50_latency_ms": 0,
            "p95_latency_ms": 0,
            "tool_mix": [],
            "reflexion_rate": 0.0,
        }

    n = len(runs)
    mean = lambda xs: sum(xs) / n if n else 0.0  # noqa: E731
    durations = [int(r.get("duration_ms") or 0) for r in runs]

    tool_mix: Counter[str] = Counter()
    for r in runs:
        hist = r.get("tool_histogram") or {}
        for tool, count in hist.items():
            tool_mix[tool] += int(count)

    multi_trial = sum(1 for r in runs if int(r.get("n_trials") or 1) > 1)

    return {
        "tasks": n,
        "avg_tool_calls":  round(mean([int(r.get("n_tool_calls") or 0) for r in runs]), 2),
        "avg_trials":      round(mean([int(r.get("n_trials") or 1) for r in runs]), 2),
        "avg_reflections": round(mean([int(r.get("n_reflections") or 0) for r in runs]), 2),
        "avg_latency_ms":  int(mean(durations)),
        "p50_latency_ms":  _percentile(durations, 0.50),
        "p95_latency_ms":  _percentile(durations, 0.95),
        "tool_mix":        tool_mix.most_common(10),
        "reflexion_rate":  round(multi_trial / n, 3) if n else 0.0,
    }


def serialize_task_run(row) -> dict:
    """Convert a ``TaskRun`` ORM row to a plain JSON-ready dict."""
    return {
        "session_id": row.session_id,
        "task_index": row.task_index,
        "prompt_preview": row.prompt_preview,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "duration_ms": row.duration_ms,
        "n_tool_calls": row.n_tool_calls,
        "n_trials": row.n_trials,
        "n_reflections": row.n_reflections,
        "tool_histogram": row.tool_histogram or {},
    }
