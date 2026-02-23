"""Cython build configuration for SynapseOS backend.

Compiles background IP files to .so (unreadable), skips foreground files
(marked with '# FOREGROUND' header) which ship as readable .py source.

Usage:
    python setup_cython.py build_ext --inplace
"""

import os
import sys
from pathlib import Path

from Cython.Build import cythonize
from setuptools import setup, Extension

BACKEND_DIR = Path(__file__).parent
FOREGROUND_MARKER = "# FOREGROUND"
SKIP_FILES = {"__init__.py", "setup_cython.py"}
# Files that use FastAPI patterns (Depends, app decorators) incompatible with Cython
CYTHON_INCOMPATIBLE = {"main.py"}


def is_foreground(filepath: Path) -> bool:
    """Check if a .py file is marked as foreground (tenant-specific)."""
    try:
        with open(filepath, "r") as f:
            first_line = f.readline().strip()
        return first_line.startswith(FOREGROUND_MARKER)
    except Exception:
        return False


def collect_background_modules() -> list[str]:
    """Find all .py files that should be compiled (background IP)."""
    modules = []

    # Scan backend/ root
    for py_file in BACKEND_DIR.glob("*.py"):
        if py_file.name in SKIP_FILES or py_file.name in CYTHON_INCOMPATIBLE:
            continue
        if is_foreground(py_file):
            continue
        modules.append(str(py_file))

    # Scan backend/logic/
    logic_dir = BACKEND_DIR / "logic"
    if logic_dir.exists():
        for py_file in logic_dir.glob("*.py"):
            if py_file.name in SKIP_FILES or py_file.name in CYTHON_INCOMPATIBLE:
                continue
            if is_foreground(py_file):
                continue
            modules.append(str(py_file))

    return modules


def main():
    background_files = collect_background_modules()

    if not background_files:
        print("No background files found to compile.")
        sys.exit(1)

    print(f"Compiling {len(background_files)} background files to .so:")
    for f in sorted(background_files):
        print(f"  {os.path.relpath(f, BACKEND_DIR)}")

    # Collect foreground files for reference
    foreground_files = []
    for py_file in list(BACKEND_DIR.glob("*.py")) + list((BACKEND_DIR / "logic").glob("*.py")):
        if py_file.name not in SKIP_FILES and is_foreground(py_file):
            foreground_files.append(str(py_file))

    if foreground_files:
        print(f"\nSkipping {len(foreground_files)} foreground files (shipped as .py):")
        for f in sorted(foreground_files):
            print(f"  {os.path.relpath(f, BACKEND_DIR)}")

    setup(
        name="synapseos-backend",
        ext_modules=cythonize(
            background_files,
            compiler_directives={
                "language_level": "3",
                "boundscheck": False,
                "wraparound": False,
            },
            nthreads=os.cpu_count() or 4,
        ),
        script_args=sys.argv[1:] if len(sys.argv) > 1 else ["build_ext", "--inplace"],
    )


if __name__ == "__main__":
    main()
