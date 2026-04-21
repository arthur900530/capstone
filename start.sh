#!/usr/bin/env bash
# =============================================================================
# BNY Digital Employee Platform — startup script
# =============================================================================

set -euo pipefail

MOCK_MODE=0
DEMO_MODE=0
for arg in "$@"; do
  case "$arg" in
    --mock) MOCK_MODE=1 ;;
    --demo) DEMO_MODE=1 ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_DIR="$ROOT_DIR/backend"
SKILLSBENCH_DIR="$BACKEND_DIR/skillsbench"

PIDS=()

# ── Colors & symbols ─────────────────────────────────────────────────────────

BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
BLUE='\033[34m'
MAGENTA='\033[35m'

CHECK="${GREEN}+${RESET}"
ARROW="${CYAN}>${RESET}"
WARN="${YELLOW}!${RESET}"
FAIL="${RED}x${RESET}"
DOT="${DIM}.${RESET}"

line() {
  echo -e "${DIM}$(printf '%.0s─' {1..60})${RESET}"
}

# Filter pip/uv output to show compact package status
pip_filter() {
  while IFS= read -r l; do
    case "$l" in
      Collecting*)           echo -e "       ${DIM}${l#Collecting }${RESET}" ;;
      Successfully*)         echo -e "       ${GREEN}${l}${RESET}" ;;
      Resolved*)             echo -e "       ${DIM}${l}${RESET}" ;;
      Installed*|" + "*)     echo -e "       ${GREEN}${l}${RESET}" ;;
      Audited*|Uninstalled*) echo -e "       ${DIM}${l}${RESET}" ;;
      *packages\ in*)        echo -e "       ${DIM}${l}${RESET}" ;;
      Requirement\ already*) ;;
      *) ;;
    esac
  done
}

header() {
  echo ""
  line
  echo -e "  ${CYAN}${BOLD}$1${RESET}"
  line
}

step() {
  echo -e "  ${CHECK}  $1"
}

info() {
  echo -e "  ${DOT}  ${DIM}$1${RESET}"
}

warn() {
  echo -e "  ${WARN}  ${YELLOW}$1${RESET}"
}

fail() {
  echo -e "  ${FAIL}  ${RED}$1${RESET}"
}

# ── Lifecycle ─────────────────────────────────────────────────────────────────

cleanup() {
  echo ""
  header "Shutting down"
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null && wait "$pid" 2>/dev/null || true
  done
  step "All services stopped."
  echo ""
  exit 0
}

trap cleanup SIGINT SIGTERM

die() {
  fail "$*"
  exit 1
}

# ── Banner ────────────────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}${BOLD}"
echo "    ____  _   ___   __   ___                    __ "
echo "   / __ )/ | / /\\ \\/ /  /   | ____ ____  ____  / /_"
echo "  / __  /  |/ /  \\  /  / /| |/ __ \`/ _ \\/ __ \\/ __/"
echo " / /_/ / /|  /   / /  / ___ / /_/ /  __/ / / / /_  "
echo "/_____/_/ |_/   /_/  /_/  |_\\__, /\\___/_/ /_/\\__/  "
echo "                           /____/                   "
echo -e "${RESET}"
echo -e "  ${DIM}Digital Employee Platform${RESET}              ${DIM}$(date '+%Y-%m-%d %H:%M')${RESET}"
line
echo ""

# ── Prerequisites ─────────────────────────────────────────────────────────────

header "Checking prerequisites"

command -v python3 >/dev/null 2>&1 || die "python3 not found. Install Python 3.12+."
step "Python      $(python3 --version 2>&1 | cut -d' ' -f2)"

command -v node >/dev/null 2>&1 || die "node not found. Install Node.js 18+."
step "Node.js     $(node --version 2>&1)"

command -v npm >/dev/null 2>&1 || die "npm not found."
step "npm         $(npm --version 2>&1)"

command -v git >/dev/null 2>&1 || die "git not found."
step "git         $(git --version 2>&1 | cut -d' ' -f3)"

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
  bench_meets_312 || die "skillsbench needs Python >= 3.12. Set SKIP_SKILLSBENCH=1 to skip."
fi

[[ -d "$FRONTEND_DIR" ]] || die "Missing frontend directory"
[[ -d "$BACKEND_DIR" ]] || die "Missing backend directory"
[[ -f "$BACKEND_DIR/requirements.txt" ]] || die "Missing requirements.txt"
[[ -f "$SKILLSBENCH_DIR/pyproject.toml" ]] || die "Missing skillsbench package"

# ── Frontend ──────────────────────────────────────────────────────────────────

header "Frontend"

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  info "First run — installing npm dependencies..."
  (cd "$FRONTEND_DIR" && npm install --silent 2>&1 | grep -E "added|up to date" | head -1 | sed "s/^/       /")
  step "Dependencies installed"
else
  step "Dependencies ready"
fi

# ── Backend virtualenv ────────────────────────────────────────────────────────

header "Backend"

if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
  info "Creating virtual environment..."
  "$PYTHON_API" -m venv "$BACKEND_DIR/.venv"
fi
info "Installing dependencies..."
if command -v uv >/dev/null 2>&1; then
  uv pip install -r "$BACKEND_DIR/requirements.txt" --python "$BACKEND_DIR/.venv/bin/python" 2>&1 | pip_filter
else
  "$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" 2>&1 | pip_filter
fi
step "API dependencies ready"

# ── Skillsbench ───────────────────────────────────────────────────────────────

if [[ "${SKIP_SKILLSBENCH:-0}" == "1" ]]; then
  info "Skillsbench skipped ${DIM}(SKIP_SKILLSBENCH=1)${RESET}"
else
  header "Skillsbench"
  if [[ ! -d "$SKILLSBENCH_DIR/.venv" ]]; then
    info "Creating venv ${DIM}(first run may take a few minutes)${RESET}..."
    "$PYTHON_BENCH" -m venv "$SKILLSBENCH_DIR/.venv"
  fi
  info "Installing evaluation framework..."
  if command -v uv >/dev/null 2>&1; then
    uv pip install -e "$SKILLSBENCH_DIR" --python "$SKILLSBENCH_DIR/.venv/bin/python" 2>&1 | pip_filter
  else
    "$SKILLSBENCH_DIR/.venv/bin/pip" install -q -e "$SKILLSBENCH_DIR" 2>&1 | pip_filter
  fi
  step "Skillsbench ready"
fi

# ── PostgreSQL ────────────────────────────────────────────────────────────────

header "Database"

if command -v pg_isready >/dev/null 2>&1; then
  if ! pg_isready -h localhost -p 5432 -q 2>/dev/null; then
    info "Starting PostgreSQL..."
    sudo service postgresql start 2>/dev/null \
      || pg_ctlcluster 16 main start 2>/dev/null \
      || true
    sleep 2
  fi

  if pg_isready -h localhost -p 5432 -q 2>/dev/null; then
    step "PostgreSQL running"

    if ! sudo -u postgres psql -lqt 2>/dev/null | grep -qw skillmarket; then
      info "Creating database..."
      sudo -u postgres createdb skillmarket 2>/dev/null || true
      step "Database 'skillmarket' created"
    else
      step "Database 'skillmarket' exists"
    fi

    info "Running migrations..."
    (cd "$BACKEND_DIR" && PYTHONPATH=. .venv/bin/python -m alembic upgrade head >/dev/null 2>&1) \
      || warn "Migration skipped"
    step "Schema up to date"

    info "Seeding skills..."
    (cd "$BACKEND_DIR" && PYTHONPATH=. .venv/bin/python -m db.seed 2>&1 | tail -1) \
      || warn "Seed skipped"
  else
    warn "Could not start PostgreSQL"
    info "Falling back to in-memory mode"
  fi
else
  warn "PostgreSQL not installed"
  info "Falling back to in-memory mode"
  info "Install with: ${CYAN}sudo apt install postgresql${RESET}"
fi


# ── Launch ────────────────────────────────────────────────────────────────────

header "Starting services"

# Build frontend env vars from flags
VITE_ENV=""
MODE_LABEL=""
if [[ "$MOCK_MODE" == "1" ]]; then
  VITE_ENV="VITE_MOCK=true $VITE_ENV"
  MODE_LABEL="${MODE_LABEL} mock"
  step "Mock LLM streaming enabled"
fi
if [[ "$DEMO_MODE" == "1" ]]; then
  VITE_ENV="VITE_DEMO=true $VITE_ENV"
  MODE_LABEL="${MODE_LABEL} demo"
  step "Desktop simulator demo enabled"
fi

# Start backend (logs go to backend/server.log so errors are inspectable)
BACKEND_LOG="$BACKEND_DIR/server.log"
: > "$BACKEND_LOG"
(cd "$BACKEND_DIR" && PYTHONPATH=. .venv/bin/uvicorn server:app --reload --host 127.0.0.1 --port 8000 >>"$BACKEND_LOG" 2>&1) &
PIDS+=($!)

info "Waiting for API..."
for i in $(seq 1 15); do
  if curl -s -o /dev/null http://localhost:8000/api/skills 2>/dev/null; then
    break
  fi
  sleep 1
done
step "API server running"

# Start frontend with env vars
(cd "$FRONTEND_DIR" && env $VITE_ENV npx vite --host 0.0.0.0 >/dev/null 2>&1) &
PIDS+=($!)

sleep 2
step "Frontend server running"

echo ""
line
echo ""
if [[ -n "$MODE_LABEL" ]]; then
  echo -e "  ${GREEN}${BOLD}Ready!${RESET}  ${YELLOW}[${MODE_LABEL# }]${RESET}"
else
  echo -e "  ${GREEN}${BOLD}Ready!${RESET}"
fi
echo ""
echo -e "  ${ARROW}  API         ${BOLD}http://localhost:8000${RESET}"
echo -e "  ${ARROW}  Frontend    ${BOLD}http://localhost:5173${RESET}"
echo ""
line
echo -e "  ${DIM}Press ${BOLD}Ctrl+C${RESET}${DIM} to stop all services${RESET}"
line
echo ""

wait
