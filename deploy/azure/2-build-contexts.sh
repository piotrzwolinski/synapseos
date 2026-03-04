#!/usr/bin/env bash
# =============================================================================
# Step 2: Build Docker Images / Contexts on Mac
# =============================================================================
# Run this on Mac. Output goes to deploy/azure/output/
# Then copy the output files to Windows via OneDrive.
#
# Usage:
#   ./2-build-contexts.sh --docker     # Path A: build images (needs Docker Desktop)
#   ./2-build-contexts.sh --tar        # Path B: tar build contexts (no Docker needed)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/output"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

mkdir -p "$OUTPUT_DIR"

# --- Parse arguments ---
MODE=""
case "${1:-}" in
    --docker) MODE="docker" ;;
    --tar)    MODE="tar" ;;
    *)
        echo -e "${CYAN}Usage:${NC}"
        echo "  $0 --docker    # Path A: Build Docker images (best IP protection)"
        echo "  $0 --tar       # Path B: Tar build contexts (no Docker needed)"
        echo ""
        echo -e "${YELLOW}Path A (--docker):${NC} Source code NEVER leaves your Mac."
        echo "  Requires: Docker Desktop running"
        echo ""
        echo -e "${YELLOW}Path B (--tar):${NC} Source sent to Azure build agent temporarily."
        echo "  Final image still has only .so files (no source)."
        exit 1
        ;;
esac

# =============================================================================
# PATH A: Build Docker images locally, export as tar
# =============================================================================
if [ "$MODE" = "docker" ]; then
    echo -e "${CYAN}=== Path A: Building Docker images locally ===${NC}"

    # Check Docker is running
    if ! docker info >/dev/null 2>&1; then
        echo -e "${RED}ERROR: Docker is not running. Start Docker Desktop first.${NC}"
        exit 1
    fi

    # --- Build Backend (Dockerfile.dist — Cython compiled) ---
    echo -e "\n${CYAN}--- Building backend image (Cython compilation) ---${NC}"
    echo "This may take 3-5 minutes..."
    docker build \
        -f "$PROJECT_ROOT/backend/Dockerfile.dist" \
        -t synapse-backend:latest \
        "$PROJECT_ROOT/backend"

    echo -e "${GREEN}Backend image built successfully${NC}"

    # --- Build Frontend ---
    echo -e "\n${CYAN}--- Building frontend image ---${NC}"
    echo -e "${YELLOW}NOTE: NEXT_PUBLIC_API_URL will be set during Azure deployment (step 4).${NC}"
    echo "Using placeholder URL for now — will be rebuilt with correct URL in step 3."
    docker build \
        --build-arg NEXT_PUBLIC_API_URL="https://PLACEHOLDER-will-be-set-in-step-3" \
        -f "$PROJECT_ROOT/frontend/Dockerfile" \
        -t synapse-frontend:latest \
        "$PROJECT_ROOT/frontend"

    echo -e "${GREEN}Frontend image built successfully${NC}"

    # --- Export as tar ---
    echo -e "\n${CYAN}--- Exporting images to tar files ---${NC}"

    echo "Saving backend image..."
    docker save synapse-backend:latest | gzip > "$OUTPUT_DIR/backend-image.tar.gz"
    BACKEND_SIZE=$(du -sh "$OUTPUT_DIR/backend-image.tar.gz" | cut -f1)
    echo -e "${GREEN}Backend image: $OUTPUT_DIR/backend-image.tar.gz ($BACKEND_SIZE)${NC}"

    echo "Saving frontend image..."
    docker save synapse-frontend:latest | gzip > "$OUTPUT_DIR/frontend-image.tar.gz"
    FRONTEND_SIZE=$(du -sh "$OUTPUT_DIR/frontend-image.tar.gz" | cut -f1)
    echo -e "${GREEN}Frontend image: $OUTPUT_DIR/frontend-image.tar.gz ($FRONTEND_SIZE)${NC}"

    # --- Verify no source code in backend image ---
    echo -e "\n${CYAN}--- Verifying IP protection (no .py source in backend) ---${NC}"
    PY_FILES=$(docker run --rm synapse-backend:latest find /app -name "*.py" -not -name "__init__.py" 2>/dev/null || true)
    if [ -n "$PY_FILES" ]; then
        echo -e "${YELLOW}Foreground .py files in image (expected — these are marked FOREGROUND):${NC}"
        echo "$PY_FILES"
    fi
    SO_FILES=$(docker run --rm synapse-backend:latest find /app -name "*.so" 2>/dev/null || true)
    if [ -n "$SO_FILES" ]; then
        echo -e "${GREEN}Compiled .so files (background IP — protected):${NC}"
        echo "$SO_FILES"
    fi

    echo -e "\n${GREEN}=== PATH A COMPLETE ===${NC}"
    echo "Files to copy to Windows via OneDrive:"
    echo "  $OUTPUT_DIR/backend-image.tar.gz"
    echo "  $OUTPUT_DIR/frontend-image.tar.gz"
fi

# =============================================================================
# PATH B: Tar build contexts (for az acr build on Windows)
# =============================================================================
if [ "$MODE" = "tar" ]; then
    echo -e "${CYAN}=== Path B: Creating build context tars ===${NC}"

    # --- Backend context ---
    echo -e "\n${CYAN}--- Packaging backend build context ---${NC}"
    # We need: all source + Dockerfile.dist + requirements*.txt + setup_cython.py
    # Respecting .dockerignore
    cd "$PROJECT_ROOT/backend"

    # Use tar with exclusions matching .dockerignore
    tar czf "$OUTPUT_DIR/backend-context.tar.gz" \
        --exclude='venv' \
        --exclude='.venv' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.git' \
        --exclude='.env' \
        --exclude='.env.*' \
        --exclude='tests' \
        --exclude='.vscode' \
        --exclude='.idea' \
        --exclude='*.egg-info' \
        --exclude='build' \
        --exclude='dist' \
        .

    BACKEND_SIZE=$(du -sh "$OUTPUT_DIR/backend-context.tar.gz" | cut -f1)
    echo -e "${GREEN}Backend context: $OUTPUT_DIR/backend-context.tar.gz ($BACKEND_SIZE)${NC}"

    # --- Frontend context ---
    echo -e "\n${CYAN}--- Packaging frontend build context ---${NC}"
    cd "$PROJECT_ROOT/frontend"

    tar czf "$OUTPUT_DIR/frontend-context.tar.gz" \
        --exclude='node_modules' \
        --exclude='.next' \
        --exclude='.git' \
        --exclude='.env*' \
        --exclude='*.log' \
        .

    FRONTEND_SIZE=$(du -sh "$OUTPUT_DIR/frontend-context.tar.gz" | cut -f1)
    echo -e "${GREEN}Frontend context: $OUTPUT_DIR/frontend-context.tar.gz ($FRONTEND_SIZE)${NC}"

    echo -e "\n${GREEN}=== PATH B COMPLETE ===${NC}"
    echo "Files to copy to Windows via OneDrive:"
    echo "  $OUTPUT_DIR/backend-context.tar.gz"
    echo "  $OUTPUT_DIR/frontend-context.tar.gz"
fi

# --- Common instructions ---
echo ""
echo -e "${YELLOW}=== NEXT STEPS ===${NC}"
echo "1. Copy the files from $OUTPUT_DIR/ to your OneDrive"
echo "2. On Windows App, download them to a local folder (e.g., C:\\deploy\\)"
echo "3. Run 3-push-images.ps1 on Windows App"
