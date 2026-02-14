#!/usr/bin/env bash
# restart-backend.sh — Kill old backend, start new one, wait for health check.
# Usage: ./scripts/restart-backend.sh [--no-reload]
#
# Exit codes: 0 = server healthy, 1 = failed to start

set -euo pipefail

PORT=8000
BACKEND_DIR="$(cd "$(dirname "$0")/../backend" && pwd)"
VENV_PYTHON="$BACKEND_DIR/venv/bin/python"
LOG_FILE="/tmp/backend.log"
HEALTH_URL="http://localhost:${PORT}/health"
MAX_WAIT=30  # seconds
RELOAD_FLAG="--reload"

# Parse args
for arg in "$@"; do
  case $arg in
    --no-reload) RELOAD_FLAG="" ;;
  esac
done

echo "==> Stopping old backend on port $PORT..."

# Graceful kill → force kill after 3s
PIDS=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  echo "    Killing PIDs: $PIDS"
  kill $PIDS 2>/dev/null || true
  # Wait up to 3s for graceful shutdown
  for i in $(seq 1 6); do
    if ! lsof -ti :$PORT >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  # Force kill if still alive
  PIDS=$(lsof -ti :$PORT 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    echo "    Force killing: $PIDS"
    kill -9 $PIDS 2>/dev/null || true
    sleep 0.5
  fi
else
  echo "    No process on port $PORT"
fi

echo "==> Starting backend (log: $LOG_FILE)..."

# Start uvicorn in background with unbuffered output
cd "$BACKEND_DIR"
PYTHONUNBUFFERED=1 "$VENV_PYTHON" -m uvicorn main:app \
  --host 0.0.0.0 --port $PORT $RELOAD_FLAG \
  > "$LOG_FILE" 2>&1 &

BACKEND_PID=$!
echo "    PID: $BACKEND_PID"

echo "==> Waiting for health check ($HEALTH_URL)..."

for i in $(seq 1 $MAX_WAIT); do
  if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
    echo "==> Backend healthy after ${i}s (PID: $BACKEND_PID)"
    exit 0
  fi
  # Check if process died
  if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "!!! Backend process died. Last 20 lines of log:"
    tail -20 "$LOG_FILE"
    exit 1
  fi
  sleep 1
done

echo "!!! Backend failed to respond after ${MAX_WAIT}s. Last 20 lines of log:"
tail -20 "$LOG_FILE"
exit 1
