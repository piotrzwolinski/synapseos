#!/usr/bin/env bash
# Build distribution package for SynapseOS backend.
#
# Output: dist/ directory with:
#   - .so files for background IP (compiled, unreadable)
#   - .py files for foreground IP (tenant-specific, readable)
#   - tenants/ directory (config + prompts)
#   - static/ directory
#   - requirements.txt
#
# Usage: ./build_dist.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
FOREGROUND_MARKER="# FOREGROUND"

# Use venv Python if available, otherwise system Python
if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ]; then
    PYTHON="$VIRTUAL_ENV/bin/python"
else
    PYTHON="python"
fi
echo "Using Python: $PYTHON"

echo "=== SynapseOS Backend Distribution Builder ==="

# Step 1: Clean dist directory
echo "[1/7] Cleaning dist/"
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR/logic"

# Step 2: Compile background files with Cython
echo "[2/7] Compiling background IP with Cython..."
cd "$SCRIPT_DIR"
$PYTHON setup_cython.py build_ext --inplace 2>&1 | tail -5
echo "  Compilation complete."

# Step 3: Copy .so files to dist
echo "[3/7] Copying compiled .so files..."
so_count=0
for so_file in "$SCRIPT_DIR"/*.so; do
    [ -f "$so_file" ] || continue
    cp "$so_file" "$DIST_DIR/"
    so_count=$((so_count + 1))
done
for so_file in "$SCRIPT_DIR"/logic/*.so; do
    [ -f "$so_file" ] || continue
    cp "$so_file" "$DIST_DIR/logic/"
    so_count=$((so_count + 1))
done
echo "  Copied $so_count .so files."

# Step 4: Copy foreground .py files (those with FOREGROUND marker)
echo "[4/7] Copying foreground .py files..."
fg_count=0
for py_file in "$SCRIPT_DIR"/*.py "$SCRIPT_DIR"/logic/*.py; do
    [ -f "$py_file" ] || continue
    first_line=$(head -1 "$py_file")
    if [[ "$first_line" == "$FOREGROUND_MARKER"* ]]; then
        # Determine relative path
        rel_path="${py_file#$SCRIPT_DIR/}"
        target_dir="$DIST_DIR/$(dirname "$rel_path")"
        mkdir -p "$target_dir"
        cp "$py_file" "$DIST_DIR/$rel_path"
        fg_count=$((fg_count + 1))
    fi
done
echo "  Copied $fg_count foreground .py files."

# Step 4b: Copy Cython-incompatible files (FastAPI patterns)
echo "  Copying Cython-incompatible .py files..."
INCOMPATIBLE="main.py"
for inc_file in $INCOMPATIBLE; do
    if [ -f "$SCRIPT_DIR/$inc_file" ]; then
        cp "$SCRIPT_DIR/$inc_file" "$DIST_DIR/$inc_file"
        echo "    $inc_file (incompatible with Cython)"
    fi
done

# Step 5: Copy __init__.py files (needed for package imports)
echo "[5/7] Copying __init__.py files..."
for init_file in "$SCRIPT_DIR"/__init__.py "$SCRIPT_DIR"/logic/__init__.py; do
    if [ -f "$init_file" ]; then
        rel_path="${init_file#$SCRIPT_DIR/}"
        target_dir="$DIST_DIR/$(dirname "$rel_path")"
        mkdir -p "$target_dir"
        cp "$init_file" "$DIST_DIR/$rel_path"
    fi
done

# Step 6: Copy supporting directories
echo "[6/7] Copying tenants/, static/, requirements.txt..."
[ -d "$SCRIPT_DIR/tenants" ] && cp -r "$SCRIPT_DIR/tenants" "$DIST_DIR/tenants"
[ -d "$SCRIPT_DIR/static" ] && cp -r "$SCRIPT_DIR/static" "$DIST_DIR/static"
[ -f "$SCRIPT_DIR/requirements.txt" ] && cp "$SCRIPT_DIR/requirements.txt" "$DIST_DIR/"

# Step 7: Verify — ensure no background .py source leaked
echo "[7/7] Verifying dist/ contents..."
leak_count=0
for so_file in "$DIST_DIR"/*.so "$DIST_DIR"/logic/*.so; do
    [ -f "$so_file" ] || continue
    # Extract module name from .so filename (e.g., main.cpython-312-darwin.so → main)
    base=$(basename "$so_file" | sed 's/\.cpython.*//')
    so_dir=$(dirname "$so_file")
    if [ -f "$so_dir/$base.py" ]; then
        echo "  WARNING: $base.py exists alongside $base.so — removing .py"
        rm "$so_dir/$base.py"
        leak_count=$((leak_count + 1))
    fi
done

echo ""
echo "=== Build Complete ==="
echo "  dist/ contains:"
echo "    .so files (background): $so_count"
echo "    .py files (foreground): $fg_count"
[ $leak_count -gt 0 ] && echo "    .py leaks removed: $leak_count"
echo ""
echo "  Ready for Docker build: docker build -f Dockerfile.dist -t synapseos ."
