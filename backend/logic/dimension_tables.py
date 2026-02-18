"""Single source of truth for dimension/material/derivation tables.

Phase 1: Consolidates duplicate data structures from state.py and session_graph.py.
Phase 2: Config-aware getters load from tenant config when available, with hardcoded
fallbacks for tests and bootstrapping.
"""

# =============================================================================
# HARDCODED FALLBACKS (used when config isn't loaded or lacks these fields)
# =============================================================================

# Filter dimension → housing dimension mapping (superset of both state.py and session_graph.py)
DIMENSION_MAP = {
    287: 300, 305: 300, 300: 300,
    592: 600, 610: 600, 600: 600,
    495: 500, 500: 500,
    900: 900, 1200: 1200,
}

# Material code → corrosion class mapping
CORROSION_MAP = {
    "FZ": "C3",
    "AZ": "C4",
    "ZM": "C5",
    "RF": "C5",
    "SF": "C5.1",
}

# All known material codes
KNOWN_MATERIAL_CODES = {"FZ", "AZ", "ZM", "RF", "SF"}

# Orientation normalization threshold (max dimension for auto-swap)
ORIENTATION_THRESHOLD = 600


# =============================================================================
# CONFIG-AWARE GETTERS
# =============================================================================

def _get_config_safe():
    """Try to get domain config; return None if unavailable."""
    try:
        from config_loader import get_config
        return get_config()
    except Exception:
        return None


def get_dimension_map() -> dict[int, int]:
    """Get filter→housing dimension map from config, falling back to hardcoded."""
    cfg = _get_config_safe()
    if cfg and cfg.dimension_mapping:
        return cfg.dimension_mapping
    return DIMENSION_MAP


def get_corrosion_map() -> dict[str, str]:
    """Get material→corrosion class map from config, falling back to hardcoded."""
    cfg = _get_config_safe()
    if cfg and cfg.corrosion_class_map:
        return cfg.corrosion_class_map
    return CORROSION_MAP


def get_known_material_codes() -> set[str]:
    """Get set of known material codes from config, falling back to hardcoded."""
    cfg = _get_config_safe()
    if cfg and cfg.corrosion_class_map:
        return set(cfg.corrosion_class_map.keys())
    return KNOWN_MATERIAL_CODES


def get_orientation_threshold() -> int:
    """Get orientation threshold from config, falling back to hardcoded."""
    cfg = _get_config_safe()
    if cfg and cfg.orientation_threshold is not None:
        return cfg.orientation_threshold
    return ORIENTATION_THRESHOLD


# =============================================================================
# HOUSING LENGTH DERIVATION
# =============================================================================

def derive_housing_length(filter_depth: int, product_family: str = "GDB") -> int:
    """Derive housing length from filter depth using engineering rules.

    Reads breakpoints from config when available, otherwise uses hardcoded logic.
    """
    cfg = _get_config_safe()
    if cfg and cfg.housing_length_derivation:
        return _derive_from_config(filter_depth, product_family, cfg.housing_length_derivation)
    return _derive_hardcoded(filter_depth, product_family)


def _derive_from_config(depth: int, family: str, rules: dict) -> int:
    """Derive housing length using config-supplied breakpoint rules."""
    family = (family or "GDB").upper().replace("-", "_")
    # Try exact match, then strip _FLEX suffix, then fall back to GDB
    breakpoints = (
        rules.get(family)
        or rules.get(family.replace("_FLEX", ""))
        or rules.get("GDB", [])
    )
    for bp in breakpoints:
        if depth <= bp["max_depth"]:
            return bp["length"]
    # Past all breakpoints → return last entry
    return breakpoints[-1]["length"] if breakpoints else 900


def _derive_hardcoded(depth: int, family: str) -> int:
    """Derive housing length using hardcoded rules (fallback)."""
    family = (family or "GDB").upper().replace("-", "_")

    if family in ("GDMI", "GDMI_FLEX"):
        return 600 if depth <= 450 else 850
    elif family in ("GDC", "GDC_FLEX"):
        return 750 if depth <= 450 else 900
    else:  # GDB and all other families
        if depth <= 292:
            return 550
        elif depth <= 450:
            return 750
        else:
            return 900
