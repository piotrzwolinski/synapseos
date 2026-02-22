"""Single source of truth for dimension/material/derivation tables.

Config-aware getters load ALL data from tenant config at runtime.
Module-level constants are empty — no domain knowledge in background IP.
"""

from typing import Optional

# =============================================================================
# EMPTY DEFAULTS (all data comes from tenant config at runtime)
# =============================================================================

DIMENSION_MAP = {}
CORROSION_MAP = {}
KNOWN_MATERIAL_CODES = set()
ORIENTATION_THRESHOLD = 600  # generic numeric default


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

def derive_housing_length(filter_depth: int, product_family: str = "") -> Optional[int]:
    """Derive housing length from filter depth using config-supplied rules.

    Returns None if config is unavailable and no derivation is possible.
    """
    cfg = _get_config_safe()
    if cfg and cfg.housing_length_derivation:
        return _derive_from_config(filter_depth, product_family, cfg.housing_length_derivation)
    return _derive_hardcoded(filter_depth, product_family)


def _derive_from_config(depth: int, family: str, rules: dict) -> Optional[int]:
    """Derive housing length using config-supplied breakpoint rules."""
    family = (family or "").upper().replace("-", "_")
    # Try exact match, then strip _FLEX suffix, then first available rule set
    breakpoints = (
        rules.get(family)
        or rules.get(family.replace("_FLEX", ""))
        or (list(rules.values())[0] if rules else [])
    )
    for bp in breakpoints:
        if depth <= bp["max_depth"]:
            return bp["length"]
    # Past all breakpoints → return last entry
    return breakpoints[-1]["length"] if breakpoints else None


def _derive_hardcoded(depth: int, family: str) -> Optional[int]:
    """Fallback when config not loaded. Returns None — caller must handle."""
    return None
