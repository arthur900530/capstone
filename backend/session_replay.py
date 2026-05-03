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
