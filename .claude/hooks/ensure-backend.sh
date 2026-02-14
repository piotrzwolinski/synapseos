#!/usr/bin/env bash
# Hook: ensure backend is running after editing backend Python files.
# If uvicorn is already running (with --reload), it auto-picks up changes.
# If it crashed or was never started, this starts it.

INPUT=$(cat)

# Extract file_path without jq
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

# Only care about backend Python files
case "$FILE_PATH" in
  */backend/*.py) ;;
  *) exit 0 ;;
esac

PORT=8000

# Check if server is responding
if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
  exit 0
fi

# Server is down — start it
BACKEND_DIR="$(cd "$(dirname "$0")/../../backend" && pwd)"
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
BACKEND_LOG="/tmp/backend.log"

[ -f "$VENV_PYTHON" ] || exit 0

# Kill any zombie processes on the port
PIDS=$(lsof -ti :$PORT 2>/dev/null || true)
[ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null && sleep 0.5

cd "$BACKEND_DIR"
PYTHONUNBUFFERED=1 "$VENV_PYTHON" -m uvicorn main:app \
  --host 0.0.0.0 --port $PORT --reload \
  > "$BACKEND_LOG" 2>&1 &

# Wait for health
for i in 1 2 3 4 5 6 7 8; do
  curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1 && exit 0
  sleep 1
done

exit 0
