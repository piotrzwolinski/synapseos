"""Pin build_product_code() behavior."""

import pytest
from backend.logic.state import TechnicalState, TagSpecification, MaterialCode


class TestBuildProductCode:
    def test_basic_code_with_format(self):
        state = TechnicalState()
        state.lock_material("RF")
        state.resolved_params = {"connection_type": "PG"}
        tag = TagSpecification(tag_id="t1", housing_width=300, housing_height=600,
                                housing_length=550, product_family="GDB")
        fmt = "{family}-{width}x{height}-{length}-{side}-{connection}-{material}"
        code = state.build_product_code(tag, code_format=fmt)
        assert code == "GDB-300x600-550-R-PG-RF"

    def test_code_with_left_side(self):
        state = TechnicalState()
        state.lock_material("FZ")
        state.resolved_params = {"connection_type": "PG", "side": "L"}
        tag = TagSpecification(tag_id="t1", housing_width=300, housing_height=600,
                                housing_length=550, product_family="GDB")
        fmt = "{family}-{width}x{height}-{length}-{side}-{connection}-{material}"
        code = state.build_product_code(tag, code_format=fmt)
        assert "-L-" in code

    def test_code_with_flange_connection(self):
        state = TechnicalState()
        state.lock_material("FZ")
        state.resolved_params = {"connection_type": "F"}
        tag = TagSpecification(tag_id="t1", housing_width=300, housing_height=600,
                                housing_length=550, product_family="GDB")
        fmt = "{family}-{width}x{height}-{length}-{side}-{connection}-{material}"
        code = state.build_product_code(tag, code_format=fmt)
        assert "-F-" in code

    def test_code_with_dict_format(self):
        state = TechnicalState()
        state.lock_material("FZ")
        tag = TagSpecification(tag_id="t1", housing_width=300, housing_height=600,
                                housing_length=550, product_family="GDB")
        code_format = {"fmt": "{family}-{width}x{height}-{length}-{side}-{connection}-{material}"}
        code = state.build_product_code(tag, code_format=code_format)
        assert code.startswith("GDB-")

    def test_generic_fallback_no_format(self):
        state = TechnicalState()
        tag = TagSpecification(tag_id="t1", housing_width=300, housing_height=600,
                                housing_length=550, product_family="GDB")
        code = state.build_product_code(tag, code_format=None)
        assert code == "GDB-300x600-550"

    def test_default_material_is_fz(self):
        """Default material when nothing locked is FZ."""
        state = TechnicalState()
        tag = TagSpecification(tag_id="t1", housing_width=300, housing_height=600,
                                housing_length=550, product_family="GDB")
        fmt = "{family}-{width}x{height}-{length}-{side}-{connection}-{material}"
        code = state.build_product_code(tag, code_format=fmt)
        assert code.endswith("-FZ")

    def test_material_override_takes_precedence(self):
        state = TechnicalState()
        state.lock_material("RF")
        tag = TagSpecification(tag_id="t1", housing_width=300, housing_height=600,
                                housing_length=550, product_family="GDB",
                                material_override="AZ")
        fmt = "{family}-{width}x{height}-{length}-{side}-{connection}-{material}"
        code = state.build_product_code(tag, code_format=fmt)
        assert code.endswith("-AZ")

    def test_double_dash_cleanup(self):
        """Empty placeholders should not produce double-dashes."""
        state = TechnicalState()
        tag = TagSpecification(tag_id="t1", housing_width=300, housing_height=600,
                                product_family="GDB")
        fmt = "{family}-{width}x{height}-{length}-{material}"
        code = state.build_product_code(tag, code_format=fmt)
        assert "--" not in code

    def test_gdp_frame_depth_format(self):
        """GDP-style codes with frame_depth placeholder."""
        state = TechnicalState()
        state.lock_material("FZ")
        state.resolved_params = {"frame_depth": "50"}
        tag = TagSpecification(tag_id="t1", housing_width=300, housing_height=600,
                                product_family="GDP")
        fmt = "{family}-{width}x{height}-{frame_depth}-{material}"
        code = state.build_product_code(tag, code_format=fmt)
        assert "50" in code
        assert code.startswith("GDP-")
