"""Load and slice JSON recordings produced by ``session_recorder``.

When ``DEMO_REPLAY=1`` is set, ``server.py`` uses these helpers to back the
``/api/chat`` endpoint with a recorded run instead of the live agent
runtime. Selection rule:

  - If ``recordings/employees/{employee_id}.json`` exists, use it.
  - Else fall back to ``recordings/_default.json``.
  - Else return ``None`` so the caller can emit a friendly SSE error.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent
RECORDINGS_DIR = _BACKEND_DIR / "recordings"
EMPLOYEES_DIR = RECORDINGS_DIR / "employees"
DEFAULT_RECORDING = RECORDINGS_DIR / "_default.json"

EXPECTED_VERSION = 1


def pick_recording(employee_id: str | None) -> tuple[Path, str] | None:
    """Resolve which recording to play.

    Returns ``(path, recording_id)`` where ``recording_id`` matches the
    convention used by ``/api/recordings/{recording_id}`` (filename stem
    relative to ``recordings/``).
    """
    if employee_id:
        candidate = EMPLOYEES_DIR / f"{employee_id}.json"
        if candidate.exists():
            return candidate, f"employees/{employee_id}"
    if DEFAULT_RECORDING.exists():
        return DEFAULT_RECORDING, "_default"
    return None


def load(path: Path) -> dict[str, Any]:
    """Read a recording JSON and validate the envelope shape."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    version = data.get("version")
    if version != EXPECTED_VERSION:
        raise ValueError(
            f"Unsupported recording version {version!r} (expected {EXPECTED_VERSION})"
        )
    if "events" not in data or not isinstance(data["events"], list):
        raise ValueError("Recording missing 'events' list")
    if "submits" not in data or not isinstance(data["submits"], list):
        raise ValueError("Recording missing 'submits' list")
    return data


def slice_turn(session: dict[str, Any], turn_idx: int) -> dict[str, Any]:
    """Return the events / browser frames belonging to one turn.

    A "turn" is the time slice between two ``submits[]`` entries (or
    between the last submit and the end of the recording). ``submits[i].t``
    and ``events[j].t`` share the same clock so we can window directly
    on ``t``.

    The output ``events`` and ``browser_frames`` are rebased so the first
    event in the turn has ``t == 0`` — that gives the replay generator a
    clean clock per turn.
    """
    submits = session.get("submits") or []
    events = session.get("events") or []
    browser_frames = ((session.get("browser") or {}).get("frames")) or []

    if not submits:
        # No submits captured (e.g. very old recording); replay everything.
        return {
            "submit": None,
            "events": events,
            "browser_frames": browser_frames,
            "t0": events[0]["t"] if events else 0,
        }

    if turn_idx < 0 or turn_idx >= len(submits):
        return {"submit": None, "events": [], "browser_frames": [], "t0": 0}

    t_start = int(submits[turn_idx].get("t", 0))
    t_end = (
        int(submits[turn_idx + 1].get("t", 0))
        if turn_idx + 1 < len(submits)
        else None
    )

    def in_window(t: int) -> bool:
        if t < t_start:
            return False
        if t_end is not None and t >= t_end:
            return False
        return True

    sliced_events = [
        {**ev, "t": int(ev.get("t", 0)) - t_start}
        for ev in events
        if in_window(int(ev.get("t", 0)))
    ]
    sliced_frames = [
        {**fr, "t": int(fr.get("t", 0)) - t_start}
        for fr in browser_frames
        if in_window(int(fr.get("t", 0)))
    ]
    return {
        "submit": submits[turn_idx],
        "events": sliced_events,
        "browser_frames": sliced_frames,
        "t0": t_start,
    }


def task_runs_from_recording(
    data: dict[str, Any],
    *,
    recording_id: str,
    base_dt: datetime | None = None,
) -> list[dict[str, Any]]:
    """Convert one recording into ``task_runs[]`` rows for the report card.

    One ``task_run`` per ``submits[]`` entry. The shape mirrors what
    ``metrics.task_runs_from_chat`` produces from a live in-memory chat
    so the report card / trajectory drawer can read demo runs through
    the same code path as DB-backed runs.

    ``recording_id`` is stored as the synthetic ``session_id`` so the
    trajectory endpoint can reverse-lookup the recording with no DB.

    Each turn is staggered by one minute on ``base_dt`` so the recent-
    task list shows distinct timestamps even when a recording only has
    one or two submits.
    """
    # Lazy imports keep this module cheap to import (server.py imports it
    # at startup) and break the metrics → trajectory → session_replay
    # circular import that would otherwise occur via build_task_run_from_buffer.
    from metrics import _attach_goal_fields, build_task_run_from_buffer

    submits = data.get("submits") or []
    if base_dt is None:
        base_dt = datetime.now(timezone.utc)

    runs: list[dict[str, Any]] = []
    for idx, sub in enumerate(submits):
        sliced = slice_turn(data, idx)
        sub_events = sliced.get("events") or []

        # Stagger turns so each gets its own ``started_at`` rather than
        # collapsing onto a single instant in the recent-task list.
        turn_base = base_dt + timedelta(seconds=idx * 60)

        # Recording stores events as ``{t, event, data}``; flatten to the
        # ``{role, type, timestamp, ...payload}`` shape that
        # ``build_task_run_from_buffer`` reads.
        flat_events: list[dict[str, Any]] = []
        for ev in sub_events:
            payload = ev.get("data") or {}
            ts = turn_base + timedelta(milliseconds=int(ev.get("t", 0)))
            entry: dict[str, Any] = {
                "role": "assistant",
                "type": ev.get("event") or "",
                "timestamp": ts.isoformat(),
            }
            if isinstance(payload, dict):
                # Don't let payload keys clobber the role/type/timestamp
                # we just set above (e.g. an "answer" event whose payload
                # also carries a "type" field would otherwise break the
                # tool_call / trial_start counters in build_task_run_from_buffer).
                for k, v in payload.items():
                    entry.setdefault(k, v)
            flat_events.append(entry)

        user_msg = {
            "role": "user",
            "type": "user",
            "content": sub.get("question") or "",
            "timestamp": turn_base.isoformat(),
        }

        if sub_events:
            end_ts = turn_base + timedelta(
                milliseconds=int(sub_events[-1].get("t", 0))
            )
        else:
            end_ts = turn_base

        run = build_task_run_from_buffer(
            user_msg=user_msg,
            events=flat_events,
            end_ts=end_ts,
        )
        run["session_id"] = recording_id
        run["task_index"] = idx
        run.setdefault("trajectory_annotations", {})
        # Match the DB-row shape so the React drawer doesn't see KeyError-
        # like ``undefined``s when toggling between DB and demo employees.
        run["source"] = "chat"
        run["test_case_run_id"] = None
        run["user_rating"] = None
        run["user_rating_at"] = None
        _attach_goal_fields(run)
        runs.append(run)
    return runs
