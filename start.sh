#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_DIR="$ROOT_DIR/mock_backend"

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

# -- Install frontend dependencies if needed --
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install)
fi

# # -- Set up Python venv & install backend dependencies if needed --
# if [ ! -d "$BACKEND_DIR/.venv" ]; then
#   echo "Creating Python virtual environment..."
#   python3 -m venv "$BACKEND_DIR/.venv"
# fi

# echo "Installing backend dependencies..."
# "$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

# -- Start mock backend --
echo "Starting mock backend on http://localhost:8000 ..."
(cd "$BACKEND_DIR" && uvicorn server:app --reload --port 8000) &
PIDS+=($!)

# -- Start frontend dev server --
echo "Starting frontend on http://localhost:5173 ..."
(cd "$FRONTEND_DIR" && npm run dev) &
PIDS+=($!)

echo ""
echo "Both services are running. Press Ctrl+C to stop."
wait
