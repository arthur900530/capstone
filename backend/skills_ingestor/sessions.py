"""Short-lived store of post-train upload directories.

When the multimodal trainer finishes ingesting a media batch, the frontend
needs to play the source video back next to the extracted workflow steps.
Instead of persisting videos forever (we explicitly chose not to in the
plan), we keep the upload directory alive for a short TTL keyed by a
session id, and stream files out of it through a dedicated route.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path


_DEFAULT_TTL_SECONDS = 60 * 60  # 60 minutes


@dataclass
class TrainSession:
    session_id: str
    tmp_dir: Path
    file_basenames: list[str]
    created_at: float
    expires_at: float
    cleaned: bool = field(default=False)

    def is_expired(self, now: float | None = None) -> bool:
        return (now or time.time()) >= self.expires_at

    def file_path(self, filename: str) -> Path:
        # Path-traversal guard: only allow exact basename matches that the
        # session knows about.
        base = os.path.basename(filename)
        if base != filename or base not in self.file_basenames:
            raise FileNotFoundError(filename)
        candidate = self.tmp_dir / base
        if not candidate.exists():
            raise FileNotFoundError(filename)
        return candidate


class TrainSessionStore:
    """In-process registry of post-train sessions with lazy TTL eviction.

    Thread-safe so it can be used from FastAPI's worker thread + the
    asyncio.to_thread call paths in the trainer.
    """

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._ttl = max(60, int(ttl_seconds))
        self._sessions: dict[str, TrainSession] = {}
        self._lock = threading.Lock()

    def register(self, tmp_dir: str | Path, file_basenames: list[str]) -> TrainSession:
        session_id = uuid.uuid4().hex[:16]
        now = time.time()
        session = TrainSession(
            session_id=session_id,
            tmp_dir=Path(tmp_dir),
            file_basenames=[os.path.basename(name) for name in file_basenames],
            created_at=now,
            expires_at=now + self._ttl,
        )
        with self._lock:
            self._sweep_locked(now)
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> TrainSession | None:
        if not session_id:
            return None
        now = time.time()
        with self._lock:
            self._sweep_locked(now)
            return self._sessions.get(session_id)

    def discard(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        _safe_rmtree(session.tmp_dir)
        session.cleaned = True
        return True

    def _sweep_locked(self, now: float) -> None:
        expired = [
            sid for sid, s in self._sessions.items() if s.is_expired(now)
        ]
        for sid in expired:
            session = self._sessions.pop(sid, None)
            if session is not None:
                _safe_rmtree(session.tmp_dir)
                session.cleaned = True


def _safe_rmtree(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass


_store = TrainSessionStore()


def get_default_store() -> TrainSessionStore:
    return _store
