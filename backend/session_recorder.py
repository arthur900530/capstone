"""Capture live agent runs into per-session JSON recordings.

When ``RECORD_SESSIONS=1`` is set, this module accumulates every SSE event,
user submission, and noVNC RFB byte chunk emitted during a chat session and
flushes the result to ``backend/recordings/{session_id}.json``. The JSON
envelope is consumed by the demo replay path (``session_replay`` +
``_stream_demo_replay`` in ``server.py``) and by the frontend's
``BrowserReplayView`` component.

When ``RECORD_SESSIONS`` is not set, every public function is a cheap no-op
so the live path pays no cost.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent
RECORDINGS_DIR = _BACKEND_DIR / "recordings"

ENVELOPE_VERSION = 1

_lock = threading.Lock()
# Per-session in-memory buffer. Keyed by session_id; absent until ``start``.
_sessions: dict[str, dict[str, Any]] = {}


def enabled() -> bool:
    return os.getenv("RECORD_SESSIONS") == "1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir() -> None:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)


def _t_ms(session: dict[str, Any]) -> int:
    """Return ms since this session's first captured timestamp."""
    return int((time.monotonic() - session["t0"]) * 1000)


def start(
    session_id: str,
    *,
    employee_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> None:
    """Initialize a recording buffer for ``session_id``. Idempotent.

    Subsequent calls for the same session keep the existing buffer so a
    multi-turn chat appends to one JSON file.
    """
    if not enabled() or not session_id:
        return
    with _lock:
        if session_id in _sessions:
            return
        _sessions[session_id] = {
            "version": ENVELOPE_VERSION,
            "sessionId": session_id,
            "createdAt": _now_iso(),
            "employeeId": employee_id,
            "config": config or {},
            "submits": [],
            "events": [],
            "browser": {
                "kind": "rfb",
                "pixelFormat": {"width": 1280, "height": 800},
                "frames": [],
            },
            # internal:
            "t0": time.monotonic(),
        }


def add_submit(session_id: str, payload: dict[str, Any]) -> None:
    """Record a user submission at the start of a turn."""
    if not enabled() or not session_id:
        return
    with _lock:
        session = _sessions.get(session_id)
        if session is None:
            return
        entry = {"t": _t_ms(session)}
        entry.update(payload)
        session["submits"].append(entry)


def add_event(session_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Record one SSE event."""
    if not enabled() or not session_id:
        return
    with _lock:
        session = _sessions.get(session_id)
        if session is None:
            return
        session["events"].append(
            {
                "t": _t_ms(session),
                "event": event_type,
                "data": data,
            }
        )


def add_browser_frame(session_id: str, direction: str, b64: str) -> None:
    """Record a base64-encoded RFB frame.

    Only ``s2c`` frames are useful for passive replay; ``c2s`` (pointer/key
    events) is recorded for completeness but the player ignores it.
    """
    if not enabled() or not session_id:
        return
    with _lock:
        session = _sessions.get(session_id)
        if session is None:
            return
        session["browser"]["frames"].append(
            {
                "t": _t_ms(session),
                "dir": direction,
                "b64": b64,
            }
        )


def finalize(session_id: str) -> Path | None:
    """Atomically flush the buffer for ``session_id`` to disk.

    Called after each turn's ``answer`` / ``done`` / on disconnect. The
    buffer is kept in memory (not discarded) so subsequent turns append to
    the same JSON file.
    """
    if not enabled() or not session_id:
        return None
    with _lock:
        session = _sessions.get(session_id)
        if session is None:
            return None
        snapshot = _serialize(session)

    _ensure_dir()
    final_path = RECORDINGS_DIR / f"{session_id}.json"
    tmp_path = final_path.with_suffix(".json.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, ensure_ascii=False)
        os.replace(tmp_path, final_path)
    except Exception:
        logger.exception("[recorder] failed to flush session=%s", session_id)
        return None
    logger.info(
        "[recorder] flushed session=%s events=%d submits=%d frames=%d -> %s",
        session_id,
        len(snapshot["events"]),
        len(snapshot["submits"]),
        len(snapshot["browser"]["frames"]),
        final_path,
    )
    return final_path


def discard(session_id: str) -> None:
    """Drop the in-memory buffer without writing to disk."""
    if not session_id:
        return
    with _lock:
        _sessions.pop(session_id, None)


def _serialize(session: dict[str, Any]) -> dict[str, Any]:
    """Strip internal-only fields (``t0``) and return a JSON-safe dict."""
    out = {
        "version": session["version"],
        "sessionId": session["sessionId"],
        "createdAt": session["createdAt"],
        "employeeId": session.get("employeeId"),
        "config": session.get("config") or {},
        "submits": list(session["submits"]),
        "events": list(session["events"]),
        "browser": {
            "kind": session["browser"]["kind"],
            "pixelFormat": dict(session["browser"]["pixelFormat"]),
            "frames": list(session["browser"]["frames"]),
        },
    }
    return out
