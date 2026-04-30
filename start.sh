#!/usr/bin/env bash
# =============================================================================
# BNY Digital Employee Platform — startup script
# =============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_DIR="$ROOT_DIR/backend"
SKILLSBENCH_DIR="$BACKEND_DIR/skillsbench"

# First-run bootstrap: copy config.py and .env from their templates so a
# fresh clone doesn't crash on the DATABASE_URL import below, and so the
# wizard's system-prompt generation has somewhere to read OPENAI_API_KEY from.
if [[ ! -f "$BACKEND_DIR/config.py" && -f "$BACKEND_DIR/config.py.example" ]]; then
  cp "$BACKEND_DIR/config.py.example" "$BACKEND_DIR/config.py"
  echo "Created backend/config.py from template."
fi
if [[ ! -f "$ROOT_DIR/.env" && -f "$ROOT_DIR/.env.template" ]]; then
  cp "$ROOT_DIR/.env.template" "$ROOT_DIR/.env"
  echo "Created .env from template — edit it and fill in OPENAI_API_KEY before using the wizard."
fi

# DATABASE_URL is extracted later (after the backend venv is built) via the
# venv's python, so python-dotenv is guaranteed importable. The system
# python3 doesn't have our dependencies on a fresh clone.

MOCK_MODE=0
DEMO_MODE=0
for arg in "$@"; do
  case "$arg" in
    --mock) MOCK_MODE=1 ;;
    --demo) DEMO_MODE=1 ;;
  esac
done

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

  # Stop any openhands agent-server containers we spawned (the server
  # lifespan normally tears them down, but a hard kill or crash can leave
  # them holding on to ports 8010-8012, blocking the next start). Match by
  # container name prefix since openhands generates a uuid suffix.
  # Intentionally we do NOT wipe /tmp/shared_ws_* — those bind-mount dirs
  # may contain the agent's MEMORY.md and any per-conversation logs the
  # user might want to keep or inspect.
  if command -v docker >/dev/null 2>&1; then
    leftover=$(docker ps -q --filter "name=^agent-server-" 2>/dev/null)
    if [ -n "$leftover" ]; then
      info "Stopping leftover agent-server containers..."
      docker stop $leftover >/dev/null 2>&1 || true
    fi
  fi

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

PYTHON_API=""
PYTHON_BENCH=""
for candidate in python3.12 python3.13 python3; do
  if command -v "$candidate" >/dev/null 2>&1 \
    && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    PYTHON_API="$candidate"
    PYTHON_BENCH="$candidate"
    break
  fi
done

[[ -n "$PYTHON_API" ]] || die "backend needs Python >= 3.12 because openhands-sdk requires it."
step "Backend py  $($PYTHON_API --version 2>&1 | cut -d' ' -f2)"

if [[ "${SKIP_SKILLSBENCH:-0}" != "1" && -z "$PYTHON_BENCH" ]]; then
  die "skillsbench needs Python >= 3.12. Set SKIP_SKILLSBENCH=1 to skip."
fi

[[ -d "$FRONTEND_DIR" ]] || die "Missing frontend directory"
[[ -d "$BACKEND_DIR" ]] || die "Missing backend directory"
[[ -f "$BACKEND_DIR/requirements.txt" ]] || die "Missing requirements.txt"
[[ -f "$SKILLSBENCH_DIR/pyproject.toml" ]] || die "Missing skillsbench package"

# ── Frontend ──────────────────────────────────────────────────────────────────

header "Frontend"

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  info "First run — installing npm dependencies..."
  if npm_output="$(cd "$FRONTEND_DIR" && npm install --silent 2>&1)"; then
    printf '%s\n' "$npm_output" | grep -E "added|up to date" | head -1 | sed "s/^/       /" || true
  else
    printf '%s\n' "$npm_output" >&2
    die "npm install failed"
  fi
  step "Dependencies installed"
else
  step "Dependencies ready"
fi

# ── Backend virtualenv ────────────────────────────────────────────────────────

header "Backend"

if [[ -d "$BACKEND_DIR/.venv" ]] \
  && ! "$BACKEND_DIR/.venv/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
  info "Recreating backend virtual environment with $($PYTHON_API --version 2>&1)..."
  rm -rf "$BACKEND_DIR/.venv"
fi

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

# Read DATABASE_URL from the backend's config via the venv's python (which
# has python-dotenv and every other dependency installed above).
DATABASE_URL=$(cd "$BACKEND_DIR" && PYTHONPATH=. .venv/bin/python -c "from config import DATABASE_URL; print(DATABASE_URL)")
export DATABASE_URL

# # ── Skillsbench ───────────────────────────────────────────────────────────────

# if [[ "${SKIP_SKILLSBENCH:-0}" == "1" ]]; then
#   info "Skillsbench skipped ${DIM}(SKIP_SKILLSBENCH=1)${RESET}"
# else
#   header "Skillsbench"
#   if [[ ! -d "$SKILLSBENCH_DIR/.venv" ]]; then
#     info "Creating venv ${DIM}(first run may take a few minutes)${RESET}..."
#     "$PYTHON_BENCH" -m venv "$SKILLSBENCH_DIR/.venv"
#   fi
#   info "Installing evaluation framework..."
#   if command -v uv >/dev/null 2>&1; then
#     uv pip install -e "$SKILLSBENCH_DIR" --python "$SKILLSBENCH_DIR/.venv/bin/python" 2>&1 | pip_filter
#   else
#     "$SKILLSBENCH_DIR/.venv/bin/pip" install -q -e "$SKILLSBENCH_DIR" 2>&1 | pip_filter
#   fi
#   step "Skillsbench ready"
# fi

# ── PostgreSQL ────────────────────────────────────────────────────────────────

header "Database"

if [[ -z "$DATABASE_URL" ]]; then
  info "DATABASE_URL not configured"
  info "Using in-memory fallback"
elif command -v pg_isready >/dev/null 2>&1; then
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
(cd "$BACKEND_DIR" && PYTHONPATH=. .venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000 >>"$BACKEND_LOG" 2>&1) &
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
