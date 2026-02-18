"""Pin MaterialCode enum, aliases, corrosion mapping, and material verification."""

import pytest
from backend.logic.state import TechnicalState, MaterialCode, extract_material_from_query


class TestMaterialCodeEnum:
    def test_material_codes_exist(self):
        assert MaterialCode.RF.value == "RF"
        assert MaterialCode.FZ.value == "FZ"
        assert MaterialCode.ZM.value == "ZM"
        assert MaterialCode.SF.value == "SF"

    def test_material_code_from_string(self):
        assert MaterialCode("RF") == MaterialCode.RF
        assert MaterialCode("FZ") == MaterialCode.FZ

    def test_material_code_is_str_enum(self):
        """MaterialCode is str enum — can be used as string directly."""
        assert isinstance(MaterialCode.RF, str)
        assert MaterialCode.RF == "RF"


class TestLockMaterial:
    def test_lock_by_code(self):
        state = TechnicalState()
        state.lock_material("RF")
        assert state.locked_material == MaterialCode.RF

    def test_lock_by_alias_stainless(self):
        state = TechnicalState()
        state.lock_material("STAINLESS")
        assert state.locked_material == MaterialCode.RF

    def test_lock_by_alias_nierdzewna(self):
        state = TechnicalState()
        state.lock_material("NIERDZEWNA")
        assert state.locked_material == MaterialCode.RF

    def test_lock_by_alias_galvanized(self):
        state = TechnicalState()
        state.lock_material("GALVANIZED")
        assert state.locked_material == MaterialCode.FZ

    def test_lock_by_alias_zinc(self):
        state = TechnicalState()
        state.lock_material("ZINC")
        assert state.locked_material == MaterialCode.FZ

    def test_lock_case_insensitive(self):
        state = TechnicalState()
        state.lock_material("rf")
        assert state.locked_material == MaterialCode.RF

    def test_lock_unknown_material_silent(self):
        state = TechnicalState()
        state.lock_material("TITANIUM")
        assert state.locked_material is None

    def test_lock_once_cannot_change(self):
        state = TechnicalState()
        state.lock_material("RF")
        state.lock_material("FZ")  # Should be ignored
        assert state.locked_material == MaterialCode.RF


class TestCorrosionMap:
    def test_corrosion_values_in_prompt_context(self):
        """Pin all corrosion class mappings from to_prompt_context()."""
        state = TechnicalState()
        state.lock_material("FZ")
        ctx = state.to_prompt_context()
        assert "FZ=C3" in ctx

        state2 = TechnicalState()
        state2.lock_material("RF")
        ctx2 = state2.to_prompt_context()
        assert "RF=C5" in ctx2

    def test_corrosion_reference_line_complete(self):
        """The reference line must have all 5 mappings."""
        state = TechnicalState()
        state.lock_material("FZ")
        ctx = state.to_prompt_context()
        assert "FZ=C3, AZ=C4, ZM=C5, RF=C5, SF=C5.1" in ctx


class TestVerifyMaterialCodes:
    def test_clean_no_warnings(self, state_with_material):
        state_with_material.tags["item_1"].product_code = "GDB-600x600-550-R-PG-RF"
        warnings = state_with_material.verify_material_codes()
        assert warnings == []

    def test_mismatch_rewrites_code(self, state_with_material):
        state_with_material.tags["item_1"].product_code = "GDB-600x600-550-R-PG-FZ"
        warnings = state_with_material.verify_material_codes()
        assert len(warnings) == 1
        assert state_with_material.tags["item_1"].product_code.endswith("-RF")


class TestExtractMaterialFromQuery:
    @pytest.mark.parametrize("query,expected", [
        ("I need stainless steel housing", "RF"),
        ("galvanized filter housing", "FZ"),
        ("zinkmagnesium material", "ZM"),
        ("sendzimir finish", "SF"),
        ("no material mentioned", None),
    ])
    def test_extract_material_patterns(self, query, expected):
        assert extract_material_from_query(query) == expected


class TestConfigVsEnumConsistency:
    @pytest.mark.xfail(reason="Known mismatch: config has 'SS', enum has 'SF'")
    def test_config_material_codes_match_enum(self, config):
        enum_codes = {m.value for m in MaterialCode}
        config_codes = set(config.material_codes)
        assert enum_codes == config_codes
