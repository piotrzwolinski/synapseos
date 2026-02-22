"""IP Cleanliness Tests — verify background IP contains ZERO MH-specific knowledge.

These tests scan source files for Mann Hummel (MH) specific terms.
Background IP must be domain-agnostic: no product codes, material constants,
or HVAC terminology in code OR comments.

Run: pytest tests/test_ip_cleanliness.py -v
"""

import re
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Background IP file list — these must be 100% domain-agnostic
# ---------------------------------------------------------------------------
BACKGROUND_IP_FILES = [
    BACKEND_DIR / "logic" / "universal_engine.py",
    BACKEND_DIR / "logic" / "dimension_tables.py",
    BACKEND_DIR / "logic" / "state.py",
    BACKEND_DIR / "logic" / "scribe.py",
    BACKEND_DIR / "logic" / "engine_adapter.py",
    BACKEND_DIR / "logic" / "verdict_adapter.py",
    BACKEND_DIR / "logic" / "graph_reasoning.py",
    BACKEND_DIR / "logic" / "reasoning_engine.py",
    BACKEND_DIR / "logic" / "session_graph.py",
    BACKEND_DIR / "retriever.py",
    BACKEND_DIR / "main.py",
    BACKEND_DIR / "config_loader.py",
    BACKEND_DIR / "llm_router.py",
    # NOTE: database.py EXCLUDED — methods mirror graph schema (foreground).
    # NOTE: bulk_offer.py EXCLUDED — will be moved to tenants/mann_hummel/.
]

# ---------------------------------------------------------------------------
# Banned terms
# ---------------------------------------------------------------------------

# MH product family codes — never in background IP (code or comments)
MH_PRODUCT_CODES = ["GDB", "GDC", "GDP", "GDMI", "GDR", "GDF", "PFF", "BFF"]

# Build regex: whole-word match, case-sensitive (product codes are uppercase)
_PRODUCT_CODE_RE = re.compile(
    r'\b(' + '|'.join(re.escape(c) for c in MH_PRODUCT_CODES) + r')\b'
)

# MH material codes as string literals (quoted values = hardcoded data)
MH_MATERIAL_LITERALS = ['"FZ"', '"RF"', '"SF"', '"ZM"', '"AZ"',
                        "'FZ'", "'RF'", "'SF'", "'ZM'", "'AZ'"]

# MH-specific domain words
MH_DOMAIN_WORDS_RE = re.compile(
    r'ROSTFRI|Sendzimir|HVAC|filter_housings_sweden',
    re.IGNORECASE,
)

# Hardcoded graph name
MH_GRAPH_NAME_RE = re.compile(r"""['"]hvac['"]""")

# ---------------------------------------------------------------------------
# Lines to EXCLUDE from scanning (config plumbing, not hardcoded knowledge)
# ---------------------------------------------------------------------------
EXCLUSION_PATTERNS = [
    "get_config",
    "load_domain_config",
    "load_tenant_prompt",
    "DEFAULT_DOMAIN",
    "_cfg.",
    "config.",
    "cfg.",
    "from config_loader",
    "import config_loader",
    "from tenants",
    "# NOTE:",       # our own classification comments
    "BACKGROUND_IP",  # this test file's own constants
]


# Enum value definition pattern (e.g., `RF = "RF"` in MaterialCode).
# These are structural type definitions, not hardcoded domain data.
# TODO: Refactor MaterialCode to be config-driven when second tenant appears.
_ENUM_VALUE_RE = re.compile(r'^[A-Z]{2,4}\s*=\s*"[A-Z]{2,4}"\s*$')


def _should_exclude_line(line: str) -> bool:
    """Return True if line is config-plumbing or structural and should be skipped."""
    stripped = line.strip()
    if any(pat in stripped for pat in EXCLUSION_PATTERNS):
        return True
    # Exclude enum value definitions (MaterialCode members)
    if _ENUM_VALUE_RE.match(stripped):
        return True
    return False


def _scan_files_for_pattern(pattern, files=None):
    """Scan background IP files for a regex pattern. Return list of violations."""
    violations = []
    for fpath in (files or BACKGROUND_IP_FILES):
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _should_exclude_line(line):
                continue
            if pattern.search(line):
                rel = fpath.relative_to(PROJECT_ROOT)
                violations.append(f"  {rel}:{lineno}: {line.strip()}")
    return violations


def _scan_files_for_literals(literals, files=None):
    """Scan background IP files for literal substrings. Return violations."""
    violations = []
    for fpath in (files or BACKGROUND_IP_FILES):
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _should_exclude_line(line):
                continue
            for lit in literals:
                if lit in line:
                    rel = fpath.relative_to(PROJECT_ROOT)
                    violations.append(f"  {rel}:{lineno}: {line.strip()}")
                    break  # one violation per line is enough
    return violations


# ===================================================================
# TESTS
# ===================================================================

class TestNoMHProductCodes:
    """Background IP must not contain MH product family codes."""

    def test_no_mh_product_codes_in_background(self):
        violations = _scan_files_for_pattern(_PRODUCT_CODE_RE)
        assert not violations, (
            f"MH product codes found in background IP ({len(violations)} violations):\n"
            + "\n".join(violations)
        )


class TestNoMHMaterialLiterals:
    """Background IP must not contain hardcoded MH material string literals."""

    def test_no_mh_material_literals_in_background(self):
        violations = _scan_files_for_literals(MH_MATERIAL_LITERALS)
        assert not violations, (
            f"MH material literals found in background IP ({len(violations)} violations):\n"
            + "\n".join(violations)
        )


class TestNoMHDomainWords:
    """Background IP must not contain MH-specific domain terminology."""

    def test_no_mh_domain_words_in_background(self):
        violations = _scan_files_for_pattern(MH_DOMAIN_WORDS_RE)
        assert not violations, (
            f"MH domain words found in background IP ({len(violations)} violations):\n"
            + "\n".join(violations)
        )


class TestNoHardcodedGraphName:
    """engine_adapter.py must not hardcode graph name."""

    def test_no_hardcoded_graph_name(self):
        ea_file = BACKEND_DIR / "logic" / "engine_adapter.py"
        violations = _scan_files_for_pattern(MH_GRAPH_NAME_RE, files=[ea_file])
        assert not violations, (
            f"Hardcoded graph name 'hvac' found:\n" + "\n".join(violations)
        )


class TestDimensionTablesNoHardcodedData:
    """dimension_tables.py module-level constants must be empty (config-driven)."""

    def test_dimension_map_empty(self):
        from logic.dimension_tables import DIMENSION_MAP
        assert DIMENSION_MAP == {}, (
            f"DIMENSION_MAP has hardcoded data: {DIMENSION_MAP}"
        )

    def test_corrosion_map_empty(self):
        from logic.dimension_tables import CORROSION_MAP
        assert CORROSION_MAP == {}, (
            f"CORROSION_MAP has hardcoded data: {CORROSION_MAP}"
        )

    def test_known_material_codes_empty(self):
        from logic.dimension_tables import KNOWN_MATERIAL_CODES
        assert KNOWN_MATERIAL_CODES == set(), (
            f"KNOWN_MATERIAL_CODES has hardcoded data: {KNOWN_MATERIAL_CODES}"
        )


class TestStateMaterialAliasesFallback:
    """TechnicalState._get_material_aliases() must return {} when config unavailable."""

    def test_material_aliases_fallback_empty(self):
        from unittest.mock import patch
        from logic.state import TechnicalState
        # Patch config_loader.get_config at the source to simulate no config
        with patch("config_loader.get_config", side_effect=Exception("no config")):
            aliases = TechnicalState._get_material_aliases()
            assert aliases == {}, (
                f"Material aliases fallback is not empty: {aliases}"
            )
