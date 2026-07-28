#!/usr/bin/env bash
# =============================================================================
# Build client-facing distribution repository.
#
# Output: client-dist/ with:
#   backend/   — compiled .so (background IP) + readable .py (foreground IP)
#   frontend/  — full Next.js source code
#   deploy/    — Terraform + seed scripts
#   backups/   — FalkorDB Cypher backup
#   docs/      — architecture documentation
#
# Backend .so files are compiled inside Docker (linux/amd64, Python 3.12).
#
# Usage: ./scripts/build_client_dist.sh [output-dir]
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
TEMPLATES_DIR="$PROJECT_ROOT/scripts/templates"
CLIENT_DIST="${1:-$PROJECT_ROOT/client-dist}"
BUILDER_TAG="synapseos-cython-builder"

echo "=== SynapseOS Client Distribution Builder ==="
echo "  Source:  $PROJECT_ROOT"
echo "  Output:  $CLIENT_DIST"
echo ""

# ── 1. Clean ─────────────────────────────────────────────────────────────────
echo "[1/7] Cleaning output directory..."
rm -rf "$CLIENT_DIST"
mkdir -p "$CLIENT_DIST"

# ── 2. Compile .so inside Docker (linux/amd64) ───────────────────────────────
echo "[2/7] Compiling backend inside Docker (linux/amd64, Python 3.12)..."
echo "  This may take a few minutes on first run (Docker layer cache helps later)."

docker build \
    --platform linux/amd64 \
    -f "$BACKEND_DIR/Dockerfile.dist" \
    --target builder \
    -t "$BUILDER_TAG" \
    "$BACKEND_DIR" 2>&1 | tail -5

# Extract /dist from the builder container
CONTAINER_ID=$(docker create --platform linux/amd64 "$BUILDER_TAG")
docker cp "$CONTAINER_ID:/dist/." "$CLIENT_DIST/backend/"
docker rm "$CONTAINER_ID" > /dev/null
echo "  Compilation done."

# ── 2b. Patch: copy files excluded by backend/.dockerignore ──────────────────
# backend/.dockerignore excludes test_*.py — copy foreground files manually
FOREGROUND_MARKER="# FOREGROUND"
for py_file in "$BACKEND_DIR"/*.py "$BACKEND_DIR"/logic/*.py; do
    [ -f "$py_file" ] || continue
    first_line=$(head -1 "$py_file")
    if [[ "$first_line" == "$FOREGROUND_MARKER"* ]]; then
        rel_path="${py_file#$BACKEND_DIR/}"
        # Only copy if not already in dist (Docker may have included it)
        if [ ! -f "$CLIENT_DIST/backend/$rel_path" ]; then
            mkdir -p "$CLIENT_DIST/backend/$(dirname "$rel_path")"
            cp "$py_file" "$CLIENT_DIST/backend/$rel_path"
        fi
    fi
done

# domain_config.yaml — legacy fallback used by config_loader
[ -f "$BACKEND_DIR/domain_config.yaml" ] && \
    cp "$BACKEND_DIR/domain_config.yaml" "$CLIENT_DIST/backend/"

# ── 3. Add runtime Dockerfile ────────────────────────────────────────────────
echo "[3/7] Adding runtime Dockerfile for backend..."
cp "$TEMPLATES_DIR/Dockerfile.runtime" "$CLIENT_DIST/backend/Dockerfile"

# ── 4. Copy frontend (full source) ───────────────────────────────────────────
echo "[4/7] Copying frontend source..."
mkdir -p "$CLIENT_DIST/frontend"
rsync -a \
    --exclude='node_modules' \
    --exclude='.next' \
    --exclude='.env*' \
    --exclude='fly.toml' \
    --exclude='.DS_Store' \
    --exclude='tsconfig.tsbuildinfo' \
    "$PROJECT_ROOT/frontend/" "$CLIENT_DIST/frontend/"

# ── 5. Copy deploy infrastructure ────────────────────────────────────────────
echo "[5/7] Copying Terraform, seed scripts, backups, docs..."

# Terraform
mkdir -p "$CLIENT_DIST/deploy/terraform"
for f in main.tf variables.tf providers.tf outputs.tf terraform.tfvars.example .gitignore README.md; do
    [ -f "$PROJECT_ROOT/deploy/terraform/$f" ] && \
        cp "$PROJECT_ROOT/deploy/terraform/$f" "$CLIENT_DIST/deploy/terraform/"
done

# Seed scripts — must be in deploy/terraform/ (main.tf uses ${path.module})
cp "$PROJECT_ROOT/deploy/seed_from_backup.sh" "$CLIENT_DIST/deploy/terraform/"
cp "$PROJECT_ROOT/deploy/seed_graph.sh" "$CLIENT_DIST/deploy/"

# Graph backup
mkdir -p "$CLIENT_DIST/backups"
LATEST_BACKUP=$(ls -t "$PROJECT_ROOT/backups/"*.cypher 2>/dev/null | head -1)
if [ -n "${LATEST_BACKUP:-}" ]; then
    cp "$LATEST_BACKUP" "$CLIENT_DIST/backups/"
    echo "  Backup: $(basename "$LATEST_BACKUP")"
fi

# Docs
mkdir -p "$CLIENT_DIST/docs"
[ -f "$PROJECT_ROOT/docs/architecture-overview.md" ] && \
    cp "$PROJECT_ROOT/docs/architecture-overview.md" "$CLIENT_DIST/docs/"

# Clean __pycache__ from extracted backend
find "$CLIENT_DIST/backend" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

# ── 6. Repo scaffolding ──────────────────────────────────────────────────────
echo "[6/7] Adding .gitignore and README..."
cp "$TEMPLATES_DIR/client-gitignore" "$CLIENT_DIST/.gitignore"
cp "$TEMPLATES_DIR/client-README.md" "$CLIENT_DIST/README.md"

# ── 7. Verify ────────────────────────────────────────────────────────────────
echo "[7/7] Verifying distribution..."

errors=0

# Check no background .py leaked alongside .so
for so_file in "$CLIENT_DIST/backend/"*.so "$CLIENT_DIST/backend/logic/"*.so; do
    [ -f "$so_file" ] || continue
    base=$(basename "$so_file" | sed 's/\.cpython.*//')
    so_dir=$(dirname "$so_file")
    if [ -f "$so_dir/$base.py" ]; then
        echo "  LEAK: $base.py found alongside $base.so — removing"
        rm "$so_dir/$base.py"
        errors=$((errors + 1))
    fi
done

# Check key files exist
for check_file in \
    "backend/main.py" \
    "backend/requirements.txt" \
    "backend/Dockerfile" \
    "backend/domain_config.yaml" \
    "backend/tenants/mann_hummel/config.yaml" \
    "frontend/package.json" \
    "frontend/Dockerfile" \
    "frontend/src/app/page.tsx" \
    "deploy/terraform/main.tf" \
    "deploy/terraform/seed_from_backup.sh" \
    ".gitignore" \
    "README.md"; do
    if [ ! -f "$CLIENT_DIST/$check_file" ]; then
        echo "  MISSING: $check_file"
        errors=$((errors + 1))
    fi
done

# Counts
so_count=$(find "$CLIENT_DIST/backend" -name '*.so' | wc -l | tr -d ' ')
py_count=$(find "$CLIENT_DIST/backend" -name '*.py' | wc -l | tr -d ' ')
total_size=$(du -sh "$CLIENT_DIST" | cut -f1)

echo ""
echo "=== Build Complete ==="
echo ""
echo "  $CLIENT_DIST/"
echo "  ├── backend/        $so_count .so (compiled) + $py_count .py (foreground)"
echo "  ├── frontend/       full Next.js source"
echo "  ├── deploy/terraform/"
echo "  ├── backups/"
echo "  ├── docs/"
echo "  ├── .gitignore"
echo "  └── README.md"
echo ""
echo "  Total size: $total_size"
[ "$errors" -gt 0 ] && echo "  Warnings: $errors (see above)"
echo ""
echo "Next steps:"
echo "  cd $CLIENT_DIST"
echo "  git init && git add -A && git commit -m 'SynapseOS v1.0 distribution'"
echo "  git remote add origin <client-github-url>"
echo "  git push -u origin main"
