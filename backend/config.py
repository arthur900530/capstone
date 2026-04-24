"""Runtime configuration.

All values come from environment variables (loaded from the repo-root
``.env`` first, then ``backend/.env`` as an override). This file is
safe to commit — every secret lives in ``.env``, which is gitignored.
See ``.env.template`` at the repo root for the full list of variables.
"""

from __future__ import annotations

import os
from pathlib import Path

import dotenv

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent

# Repo-root ``.env`` is the canonical location; ``backend/.env`` is a
# per-backend override that wins when both are present.
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(_BACKEND_DIR / ".env", override=True)

# ── OpenRouter (chat agent, trajectory annotation) ──────────────────────────
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ── Model ids ───────────────────────────────────────────────────────────────
AGENT_MODEL = os.getenv("AGENT_MODEL", "openrouter/minimax/minimax-m2.7")
SKILL_MODEL = os.getenv("SKILL_MODEL", "google/gemini-2.5-flash")
VERIFIER_MODEL = os.getenv("VERIFIER_MODEL", "openai/gpt-4o")

# ── PostgreSQL ──────────────────────────────────────────────────────────────
# Default points at a localhost Postgres with stock ``postgres:postgres``
# credentials. Production deployments must override this in ``.env``.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/skillmarket",
)
