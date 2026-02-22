"""Functional Regression Tests — verify config-driven lookups return correct MH data.

These tests ensure that WITH config loaded (production scenario), all lookups
return the expected Mann Hummel data. They must PASS before AND after the
IP cleanup — proving we didn't break functionality.

Run: pytest tests/test_config_driven_lookups.py -v
"""

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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ===================================================================
# DIMENSION TABLES — config-driven getters
# ===================================================================

class TestDimensionMapFromConfig:
    """get_dimension_map() must return MH filter→housing mappings via config."""

    def test_returns_nonempty(self):
        from logic.dimension_tables import get_dimension_map
        dim_map = get_dimension_map()
        assert len(dim_map) > 0, "Dimension map is empty — config not loaded?"

    def test_287_maps_to_300(self):
        from logic.dimension_tables import get_dimension_map
        assert get_dimension_map()[287] == 300

    def test_592_maps_to_600(self):
        from logic.dimension_tables import get_dimension_map
        assert get_dimension_map()[592] == 600

    def test_610_maps_to_600(self):
        from logic.dimension_tables import get_dimension_map
        assert get_dimension_map()[610] == 600

    def test_900_maps_to_900(self):
        from logic.dimension_tables import get_dimension_map
        assert get_dimension_map()[900] == 900


class TestCorrosionMapFromConfig:
    """get_corrosion_map() must return MH material→corrosion class via config."""

    def test_returns_nonempty(self):
        from logic.dimension_tables import get_corrosion_map
        corr_map = get_corrosion_map()
        assert len(corr_map) > 0, "Corrosion map is empty — config not loaded?"

    def test_fz_is_c3(self):
        from logic.dimension_tables import get_corrosion_map
        assert get_corrosion_map()["FZ"] == "C3"

    def test_rf_is_c5(self):
        from logic.dimension_tables import get_corrosion_map
        assert get_corrosion_map()["RF"] == "C5"

    def test_sf_is_c5_1(self):
        from logic.dimension_tables import get_corrosion_map
        assert get_corrosion_map()["SF"] == "C5.1"

    def test_az_is_c4(self):
        from logic.dimension_tables import get_corrosion_map
        assert get_corrosion_map()["AZ"] == "C4"


class TestKnownMaterialsFromConfig:
    """get_known_material_codes() must return full MH material set via config."""

    def test_returns_all_five(self):
        from logic.dimension_tables import get_known_material_codes
        codes = get_known_material_codes()
        assert codes == {"FZ", "AZ", "ZM", "RF", "SF"}


class TestOrientationThresholdFromConfig:
    """get_orientation_threshold() must return 600 via config."""

    def test_threshold_is_600(self):
        from logic.dimension_tables import get_orientation_threshold
        assert get_orientation_threshold() == 600


# ===================================================================
# HOUSING LENGTH DERIVATION — config-driven
# ===================================================================

class TestHousingDerivationFromConfig:
    """derive_housing_length() must return correct values via config rules."""

    def test_gdb_depth_292_gives_550(self):
        from logic.dimension_tables import derive_housing_length
        assert derive_housing_length(292, "GDB") == 550

    def test_gdb_depth_450_gives_750(self):
        from logic.dimension_tables import derive_housing_length
        assert derive_housing_length(450, "GDB") == 750

    def test_gdb_depth_600_gives_900(self):
        from logic.dimension_tables import derive_housing_length
        assert derive_housing_length(600, "GDB") == 900

    def test_gdmi_depth_450_gives_600(self):
        from logic.dimension_tables import derive_housing_length
        assert derive_housing_length(450, "GDMI") == 600

    def test_gdmi_depth_500_gives_850(self):
        from logic.dimension_tables import derive_housing_length
        assert derive_housing_length(500, "GDMI") == 850

    def test_gdc_depth_450_gives_750(self):
        from logic.dimension_tables import derive_housing_length
        assert derive_housing_length(450, "GDC") == 750

    def test_gdc_depth_500_gives_900(self):
        from logic.dimension_tables import derive_housing_length
        assert derive_housing_length(500, "GDC") == 900


# ===================================================================
# MATERIAL ALIASES — config-driven via TechnicalState
# ===================================================================

class TestMaterialAliasesFromConfig:
    """TechnicalState._get_material_aliases() must return MH aliases via config."""

    def test_rostfri_maps_to_rf(self):
        from logic.state import TechnicalState, MaterialCode
        aliases = TechnicalState._get_material_aliases()
        assert aliases.get("ROSTFRI") == MaterialCode.RF

    def test_galvanized_maps_to_fz(self):
        from logic.state import TechnicalState, MaterialCode
        aliases = TechnicalState._get_material_aliases()
        assert aliases.get("GALVANIZED") == MaterialCode.FZ

    def test_stainless_maps_to_rf(self):
        from logic.state import TechnicalState, MaterialCode
        aliases = TechnicalState._get_material_aliases()
        assert aliases.get("STAINLESS") == MaterialCode.RF

    def test_cynk_maps_to_fz(self):
        from logic.state import TechnicalState, MaterialCode
        aliases = TechnicalState._get_material_aliases()
        assert aliases.get("CYNK") == MaterialCode.FZ


# ===================================================================
# SCRIBE PRODUCT INFERENCE — config-driven
# ===================================================================

class TestProductInferenceFromConfig:
    """_build_product_inference_text() must return MH hints via config."""

    def test_contains_gdmi(self):
        from logic.scribe import _build_product_inference_text
        text = _build_product_inference_text()
        assert "GDMI" in text, f"Product inference missing GDMI: {text[:200]}"

    def test_contains_insulated(self):
        from logic.scribe import _build_product_inference_text
        text = _build_product_inference_text()
        assert "insulated" in text.lower(), f"Missing 'insulated': {text[:200]}"

    def test_contains_gdc(self):
        from logic.scribe import _build_product_inference_text
        text = _build_product_inference_text()
        assert "GDC" in text, f"Product inference missing GDC: {text[:200]}"

    def test_contains_carbon(self):
        from logic.scribe import _build_product_inference_text
        text = _build_product_inference_text()
        assert "carbon" in text.lower(), f"Missing 'carbon': {text[:200]}"


# ===================================================================
# PROMPT CONTEXT — corrosion reference built from config
# ===================================================================

class TestPromptContextCorrosionRef:
    """to_prompt_context() must include corrosion reference from config."""

    def test_corrosion_ref_present(self):
        from logic.state import TechnicalState, MaterialCode
        state = TechnicalState()
        state.lock_material("RF")
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        ctx = state.to_prompt_context()
        # Must contain corrosion class for RF
        assert "C5" in ctx, f"Corrosion class C5 not in prompt context"

    def test_material_code_in_context(self):
        from logic.state import TechnicalState, MaterialCode
        state = TechnicalState()
        state.lock_material("RF")
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        ctx = state.to_prompt_context()
        assert "RF" in ctx, f"Material code RF not in prompt context"


class TestPromptContextNoHardcodedRules:
    """After cleanup, to_prompt_context() must NOT contain hardcoded MH rules.

    These tests verify hardcoded MH rules have been removed from prompt context.
    """

    def test_no_hardcoded_indoor_rule(self):
        """GDMI indoor rule should be config-driven, not hardcoded."""
        from logic.state import TechnicalState
        state = TechnicalState()
        state.detected_family = "GDMI"
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        ctx = state.to_prompt_context()
        # After cleanup this hardcoded string should be gone
        assert "Indoor use only per catalog" not in ctx, (
            "Hardcoded GDMI indoor rule still present in prompt context"
        )

    def test_corrosion_ref_is_config_driven(self):
        """Corrosion reference should be built dynamically from config."""
        from unittest.mock import patch
        from logic.state import TechnicalState
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        # Mock corrosion map with test data to prove it's dynamic
        with patch("logic.dimension_tables.get_corrosion_map",
                   return_value={"XX": "C9", "YY": "C1"}):
            ctx = state.to_prompt_context()
        assert "XX=C9" in ctx, "Corrosion ref not built from config dynamically"
        assert "FZ=C3" not in ctx, "Original data leaked despite mock"

    def test_no_hardcoded_housing_corrosion_comment(self):
        """Housing corrosion class comment should not mention specific products."""
        from logic.state import TechnicalState
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        ctx = state.to_prompt_context()
        assert "C2 for GDB/GDC" not in ctx, (
            "Hardcoded product-specific corrosion comment still present"
        )
