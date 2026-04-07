#!/usr/bin/env bash
# =============================================================================
# Capstone frontend + API — first-time and daily startup
#
# From a fresh clone (no node_modules, no venvs), this script will:
#   1. Install frontend npm dependencies
#   2. Create backend/.venv and install FastAPI stack (requirements.txt)
#   3. Create backend/skillsbench/.venv and pip install -e the skillsbench
#      package (pulls Harbor from GitHub — needs network + git)
#   4. Start the API on http://localhost:8000 and Vite on http://localhost:5173
#
# Prerequisites on your machine:
#   - Python 3.12+ (skillsbench declares requires-python >= 3.12)
#   - Node.js 18+ and npm
#   - git (for Harbor’s VCS dependency)
#
# Optional: skip skillsbench venv (API-only) with  SKIP_SKILLSBENCH=1 ./start.sh
# =============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_DIR="$ROOT_DIR/backend"
SKILLSBENCH_DIR="$BACKEND_DIR/skillsbench"

PIDS=()

cleanup() {
  echo ""
  echo "Shutting down services..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null && wait "$pid" 2>/dev/null || true
  done
  echo "All services stopped."
  exit 0
}

trap cleanup SIGINT SIGTERM

die() {
  echo "Error: $*" >&2
  exit 1
}

echo "==> Project root: $ROOT_DIR"
echo ""

# -- Prerequisites --
command -v python3 >/dev/null 2>&1 || die "python3 not found. Install Python 3.12+."
command -v node >/dev/null 2>&1 || die "node not found. Install Node.js 18+."
command -v npm >/dev/null 2>&1 || die "npm not found. Install Node.js (includes npm)."
command -v git >/dev/null 2>&1 || die "git not found (needed to install Harbor for skillsbench)."

# API venv: any reasonable python3. Skillsbench: requires >= 3.12 (see backend/skillsbench/pyproject.toml).
PYTHON_API="python3"
PYTHON_BENCH="python3"
if command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BENCH="python3.12"
elif command -v python3.13 >/dev/null 2>&1; then
  PYTHON_BENCH="python3.13"
fi

bench_meets_312() {
  "$PYTHON_BENCH" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'
}

if [[ "${SKIP_SKILLSBENCH:-0}" != "1" ]]; then
  bench_meets_312 || die "skillsbench needs Python >= 3.12. Found: $PYTHON_BENCH ($($PYTHON_BENCH --version 2>&1)). Install python3.12 or set SKIP_SKILLSBENCH=1 for API-only."
fi

[[ -d "$FRONTEND_DIR" ]] || die "Missing frontend directory: $FRONTEND_DIR"
[[ -d "$BACKEND_DIR" ]] || die "Missing backend directory: $BACKEND_DIR"
[[ -f "$BACKEND_DIR/requirements.txt" ]] || die "Missing $BACKEND_DIR/requirements.txt"
[[ -f "$SKILLSBENCH_DIR/pyproject.toml" ]] || die "Missing skillsbench package at $SKILLSBENCH_DIR (expected pyproject.toml)"

# -- Frontend (npm) --
echo "==> Frontend"
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "    First run: installing npm dependencies (this may take a minute)..."
  (cd "$FRONTEND_DIR" && npm install)
else
  echo "    node_modules present; run 'cd frontend && npm install' manually if package.json changed."
fi
echo ""

# -- API virtualenv (lightweight) --
echo "==> API virtualenv ($BACKEND_DIR/.venv)"
if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
  echo "    Creating venv with $PYTHON_API ..."
  "$PYTHON_API" -m venv "$BACKEND_DIR/.venv"
fi
echo "    Installing / updating API dependencies..."
"$BACKEND_DIR/.venv/bin/python" -m pip install -q --upgrade pip
"$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"
echo ""

# -- Skillsbench virtualenv (Harbor / eval tooling) --
if [[ "${SKIP_SKILLSBENCH:-0}" == "1" ]]; then
  echo "==> Skillsbench virtualenv (skipped: SKIP_SKILLSBENCH=1)"
  echo "    Skill evaluation subprocess will not work until you run:"
  echo "      cd $SKILLSBENCH_DIR && $PYTHON_BENCH -m venv .venv && .venv/bin/pip install -e ."
  echo ""
else
  echo "==> Skillsbench virtualenv ($SKILLSBENCH_DIR/.venv)"
  echo "    Using interpreter: $PYTHON_BENCH (skillsbench requires Python >= 3.12)"
  if [[ ! -d "$SKILLSBENCH_DIR/.venv" ]]; then
    echo "    Creating venv (first run can take several minutes: Harbor installs from GitHub)..."
    "$PYTHON_BENCH" -m venv "$SKILLSBENCH_DIR/.venv"
  fi
  echo "    Installing / updating editable skillsbench package..."
  "$SKILLSBENCH_DIR/.venv/bin/python" -m pip install -q --upgrade pip
  "$SKILLSBENCH_DIR/.venv/bin/pip" install -e "$SKILLSBENCH_DIR"
  echo ""
fi

# -- PostgreSQL check (optional) --
echo "==> PostgreSQL"
if command -v pg_isready >/dev/null 2>&1; then
  if pg_isready -h localhost -p 5432 -q 2>/dev/null; then
    echo "    PostgreSQL is running. Skill marketplace will use DB."
    echo "    Running Alembic migrations..."
    (cd "$BACKEND_DIR" && PYTHONPATH=. .venv/bin/python -m alembic upgrade head 2>&1) || echo "    Migration skipped (DB may need setup)"
    echo "    Seeding skills..."
    (cd "$BACKEND_DIR" && PYTHONPATH=. .venv/bin/python -m db.seed 2>&1) || echo "    Seed skipped"
  else
    echo "    PostgreSQL is not running. Skill marketplace will fall back to in-memory mode."
  fi
else
  echo "    pg_isready not found. Skipping DB check (in-memory fallback active)."
fi
echo ""

# -- Start processes --
echo "==> Starting servers"
echo "    API:      http://localhost:8000"
echo "    Frontend: http://localhost:5173"
echo ""

(cd "$BACKEND_DIR" && PYTHONPATH=. .venv/bin/uvicorn server:app --reload --host 127.0.0.1 --port 8000) &
PIDS+=($!)

(cd "$FRONTEND_DIR" && npm run dev) &
PIDS+=($!)

echo "Press Ctrl+C to stop both."
wait
