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


_MAX_RAW_EVENT_TEXT_CHARS = 8_000
_MAX_RAW_EVENTS_BYTES = 2_000_000


def _trim_raw_event_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:_MAX_RAW_EVENT_TEXT_CHARS]
    if isinstance(value, list):
        return [_trim_raw_event_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _trim_raw_event_value(v) for k, v in value.items()}
    return value


def _serialize_raw_events(events: list[dict]) -> list[dict]:
    """Trim stored raw events so trajectory playback survives without huge rows."""
    serialized: list[dict] = []
    total_bytes = 0
    for event in events:
        trimmed = _trim_raw_event_value(event)
        approx_bytes = len(str(trimmed).encode("utf-8", errors="ignore"))
        if serialized and total_bytes + approx_bytes > _MAX_RAW_EVENTS_BYTES:
            break
        serialized.append(trimmed)
        total_bytes += approx_bytes
    return serialized


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
        "full_prompt": prompt,
        "prompt_preview": prompt_preview,
        "started_at": started_at,
        "ended_at": end_ts,
        "duration_ms": duration_ms,
        "n_tool_calls": len(tool_calls),
        "n_trials": max(len(trials), 1),
        "n_reflections": len(reflections),
        "tool_histogram": tool_histogram,
        "raw_events": _serialize_raw_events(events),
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
        run.setdefault("trajectory_annotations", {})
        _attach_goal_fields(run)
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


def _attach_goal_fields(run: dict) -> None:
    """Compute the hierarchical goal tree + leaf/top-level summaries for a run.

    Populates ``top_level_goals`` (hierarchy), ``leaf_summary`` and
    ``top_level_summary`` on ``run`` in place. Idempotent — safe to call on a
    run that already carries these fields (e.g. when re-serializing after an
    annotation refresh).
    """
    from trajectory import (  # local import to avoid startup cycles
        _attach_weighted_rates,
        build_nodes_from_events,
        extract_goal_hierarchy,
        leaf_step_summary,
        segment_nodes,
        to_dict,
        top_level_summary,
        weighted_task_score_from_tree,
    )

    annotations = run.get("trajectory_annotations") or {}
    raw_events = run.get("raw_events") or []

    top_level: list[dict] = []
    tree_dict: dict | None = None
    if raw_events:
        action_nodes, trial_boundaries = build_nodes_from_events(raw_events)
        tree = segment_nodes(action_nodes, trial_boundaries)
        tree_dict = to_dict(tree)
        top_level = extract_goal_hierarchy(tree_dict, annotations)

    _attach_weighted_rates(top_level)
    run["top_level_goals"] = top_level
    run["leaf_summary"] = leaf_step_summary(top_level)
    run["top_level_summary"] = top_level_summary(top_level)
    # Full-tree depth-weighted score: walks every annotated sequence node
    # (root, trial wrappers, goals, sub-goals) plus leaf actions so the
    # latest LLM verdict at *any* level — especially the root annotation
    # the UI displays in the drawer — actually drives the KPI. Using
    # ``weighted_task_score(top_level)`` alone here dropped the root /
    # trial statuses and painted sessions green that the LLM flagged as
    # failures.
    run["task_score"] = weighted_task_score_from_tree(tree_dict, annotations)
    run["annotated"] = bool(annotations)


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
            "avg_leaf_rate": 0.0,
            "avg_task_score": 0.0,
            "total_leaf_steps": 0,
            "total_leaf_achieved": 0,
            "tasks_fully_achieved": 0,
            "total_top_level_goals": 0,
            "top_level_fully_achieved": 0,
            "annotated_tasks": 0,
            "unannotated_tasks": 0,
            "avg_user_rating": 0.0,
            "rated_tasks": 0,
            "unrated_tasks": 0,
            "rating_distribution": {k: 0 for k in range(1, 6)},
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

    # Goal-oriented rollups. Each run is expected to carry leaf_summary /
    # top_level_summary as computed by _attach_goal_fields(); tasks whose
    # trajectories haven't been annotated yet will have zero counts and are
    # excluded from averages so they don't drag the mean to zero.
    #
    # Step- and overall-rate KPIs use the depth-weighted per-task score
    # (``task_score``) so they honour the aggregated-mean spec
    # (0.5·L1_avg + 0.25·L2_avg + …). Runs without any status signal
    # (``task_score is None``) are excluded so an un-annotated backlog
    # doesn't drag the mean toward zero.
    task_scores = [
        float(r["task_score"])
        for r in runs
        if r.get("task_score") is not None
    ]
    leaf_rates = [
        float((r.get("leaf_summary") or {}).get("rate") or 0.0)
        for r in runs
        if int((r.get("leaf_summary") or {}).get("total") or 0) > 0
    ]
    total_leaf = sum(int((r.get("leaf_summary") or {}).get("total") or 0) for r in runs)
    total_leaf_achieved = sum(
        int((r.get("leaf_summary") or {}).get("achieved") or 0) for r in runs
    )
    total_top_level = sum(
        int((r.get("top_level_summary") or {}).get("total") or 0) for r in runs
    )
    total_top_level_fully = sum(
        int((r.get("top_level_summary") or {}).get("fully_achieved") or 0) for r in runs
    )
    annotated = sum(1 for r in runs if r.get("annotated"))

    # User-submitted 1–5 ratings. Un-rated runs are excluded from the mean so
    # a backlog of unrated turns doesn't drag the average down — the report
    # card renders ``rated_tasks`` alongside the avg as the honest denominator.
    user_ratings = [
        int(r["user_rating"])
        for r in runs
        if r.get("user_rating") is not None
    ]
    rating_distribution: dict[int, int] = {k: 0 for k in range(1, 6)}
    for r in user_ratings:
        rating_distribution[r] = rating_distribution.get(r, 0) + 1
    # "Tasks achieved" uses the LLM's top-level (root) verdict directly:
    # the session is achieved iff the root annotation says ``success``.
    # The earlier strict-1.0 rule punished every imperfect leaf trace
    # and ended up 0/N; the per-goal count before that ignored the root
    # entirely. Neither matched what the user sees in the drawer.
    tasks_fully_achieved = sum(
        1
        for r in runs
        if ((r.get("trajectory_annotations") or {}).get("root") or {}).get("status")
        == "success"
    )

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
        # Goal/step oriented (new). ``avg_task_score`` is the weighted
        # aggregated mean the report card's KPIs render; ``avg_leaf_rate``
        # stays alongside as the raw count ratio for callers that want
        # "how many leaf steps succeeded" without the depth weighting.
        "avg_task_score":
            round(sum(task_scores) / len(task_scores), 4) if task_scores else 0.0,
        "avg_leaf_rate":
            round(sum(leaf_rates) / len(leaf_rates), 4) if leaf_rates else 0.0,
        "total_leaf_steps": total_leaf,
        "total_leaf_achieved": total_leaf_achieved,
        # Task-level rollup for the "Top-level goals" KPI tile.
        "tasks_fully_achieved": tasks_fully_achieved,
        # Kept for back-compat with any callers still reading the old
        # per-goal counts; the report card no longer uses them.
        "total_top_level_goals": total_top_level,
        "top_level_fully_achieved": total_top_level_fully,
        "annotated_tasks": annotated,
        "unannotated_tasks": n - annotated,
        # Passive user-rating rollups.
        "avg_user_rating":
            round(sum(user_ratings) / len(user_ratings), 2)
            if user_ratings else 0.0,
        "rated_tasks": len(user_ratings),
        "unrated_tasks": n - len(user_ratings),
        "rating_distribution": rating_distribution,
    }


def serialize_task_run(row) -> dict:
    """Convert a ``TaskRun`` ORM row to a plain JSON-ready dict."""
    run = {
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
        "raw_events": row.raw_events or [],
        "trajectory_annotations": getattr(row, "trajectory_annotations", None) or {},
        "user_rating": getattr(row, "user_rating", None),
        "user_rating_at": (
            row.user_rating_at.isoformat()
            if getattr(row, "user_rating_at", None)
            else None
        ),
    }
    _attach_goal_fields(run)
    return run
