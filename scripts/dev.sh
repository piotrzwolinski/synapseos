#!/usr/bin/env bash
# dev.sh — Start backend + frontend dev servers with dependency check.
# Usage: ./scripts/dev.sh [--backend-only | --frontend-only] [--no-reload]
#
# What it does:
#   1. Kills stale processes on ports 8000 / 3000
#   2. Syncs Python deps (pip install -r requirements.txt)
#   3. Starts backend (uvicorn) and frontend (next dev)
#   4. Waits for health checks
#   5. Tails combined logs
#
# Exit: Ctrl+C kills both servers.

set -euo pipefail

# ── Config ──────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
BACKEND_PORT=8000
FRONTEND_PORT=3000
BACKEND_LOG="/tmp/synapse-backend.log"
FRONTEND_LOG="/tmp/synapse-frontend.log"
HEALTH_URL="http://localhost:${BACKEND_PORT}/health"
MAX_WAIT=30
RELOAD_FLAG="--reload"
RUN_BACKEND=true
RUN_FRONTEND=true

# ── Parse args ──────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --backend-only)  RUN_FRONTEND=false ;;
    --frontend-only) RUN_BACKEND=false ;;
    --no-reload)     RELOAD_FLAG="" ;;
  esac
done

# ── Helpers ─────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[dev]${NC} $*"; }
ok()   { echo -e "${GREEN}  OK${NC} $*"; }
warn() { echo -e "${YELLOW}  !!${NC} $*"; }
err()  { echo -e "${RED} ERR${NC} $*"; }

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    log "Killing processes on port $port (PIDs: $pids)"
    kill $pids 2>/dev/null || true
    sleep 1
    # Force kill if still alive
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
      kill -9 $pids 2>/dev/null || true
      sleep 0.5
    fi
  fi
}

cleanup() {
  log "Shutting down..."
  [ -n "${BACKEND_PID:-}" ]  && kill $BACKEND_PID 2>/dev/null || true
  [ -n "${FRONTEND_PID:-}" ] && kill $FRONTEND_PID 2>/dev/null || true
  # Kill child processes too
  kill_port $BACKEND_PORT
  kill_port $FRONTEND_PORT
  exit 0
}

trap cleanup SIGINT SIGTERM

# ── 1. Check prerequisites ─────────────────────────────
log "Checking prerequisites..."

if [ ! -f "$VENV_PYTHON" ]; then
  err "Python venv not found at $VENV_DIR"
  err "Run: python3 -m venv $VENV_DIR && $VENV_PIP install -r $BACKEND_DIR/requirements.txt"
  exit 1
fi

if $RUN_FRONTEND && ! command -v npm &>/dev/null; then
  err "npm not found. Install Node.js first."
  exit 1
fi

ok "Prerequisites found"

# ── 2. Kill stale processes ────────────────────────────
log "Clearing ports..."
$RUN_BACKEND  && kill_port $BACKEND_PORT
$RUN_FRONTEND && kill_port $FRONTEND_PORT
ok "Ports cleared"

# ── 3. Sync Python dependencies ───────────────────────
if $RUN_BACKEND; then
  log "Syncing Python dependencies..."
  # Capture pip output and only show if something was installed
  PIP_OUTPUT=$("$VENV_PIP" install -q -r "$BACKEND_DIR/requirements.txt" 2>&1) || {
    err "pip install failed:"
    echo "$PIP_OUTPUT"
    exit 1
  }
  if echo "$PIP_OUTPUT" | grep -q "Successfully installed"; then
    INSTALLED=$(echo "$PIP_OUTPUT" | grep "Successfully installed" | sed 's/Successfully installed //')
    ok "Installed new packages: $INSTALLED"
  else
    ok "All dependencies up to date"
  fi
fi

# ── 4. Start backend ──────────────────────────────────
if $RUN_BACKEND; then
  log "Starting backend on port $BACKEND_PORT..."
  cd "$BACKEND_DIR"
  PYTHONUNBUFFERED=1 "$VENV_PYTHON" -m uvicorn main:app \
    --host 0.0.0.0 --port $BACKEND_PORT $RELOAD_FLAG \
    > "$BACKEND_LOG" 2>&1 &
  BACKEND_PID=$!

  # Wait for health check
  for i in $(seq 1 $MAX_WAIT); do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
      ok "Backend healthy after ${i}s (PID: $BACKEND_PID)"
      break
    fi
    # Check if process died
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
      err "Backend crashed! Last 30 lines:"
      tail -30 "$BACKEND_LOG"
      exit 1
    fi
    sleep 1
  done

  # Final check
  if ! curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
    err "Backend not responding after ${MAX_WAIT}s. Log tail:"
    tail -30 "$BACKEND_LOG"
    exit 1
  fi
fi

# ── 5. Start frontend ─────────────────────────────────
if $RUN_FRONTEND; then
  log "Starting frontend on port $FRONTEND_PORT..."
  cd "$FRONTEND_DIR"
  npm run dev > "$FRONTEND_LOG" 2>&1 &
  FRONTEND_PID=$!

  # Wait for frontend to be ready
  for i in $(seq 1 20); do
    if curl -sf "http://localhost:${FRONTEND_PORT}" >/dev/null 2>&1; then
      ok "Frontend ready after ${i}s (PID: $FRONTEND_PID)"
      break
    fi
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
      err "Frontend crashed! Last 20 lines:"
      tail -20 "$FRONTEND_LOG"
      exit 1
    fi
    sleep 1
  done
fi

# ── 6. Summary ─────────────────────────────────────────
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  SynapseOS Dev Servers Running${NC}"
echo -e "${GREEN}========================================${NC}"
$RUN_BACKEND  && echo -e "  Backend:  ${CYAN}http://localhost:${BACKEND_PORT}${NC}  (log: $BACKEND_LOG)"
$RUN_FRONTEND && echo -e "  Frontend: ${CYAN}http://localhost:${FRONTEND_PORT}${NC}  (log: $FRONTEND_LOG)"
echo -e "${GREEN}========================================${NC}"
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop all servers"
echo ""

# ── 7. Tail logs ───────────────────────────────────────
if $RUN_BACKEND && $RUN_FRONTEND; then
  tail -f "$BACKEND_LOG" "$FRONTEND_LOG"
elif $RUN_BACKEND; then
  tail -f "$BACKEND_LOG"
elif $RUN_FRONTEND; then
  tail -f "$FRONTEND_LOG"
fi
