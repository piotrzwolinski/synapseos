"""Pin housing length derivation rules (depth→length)."""

import pytest
from backend.logic.state import TagSpecification


class TestDefaultDerivationRules:
    """Pin depth→length breakpoints for default (GDB-like) derivation."""

    @pytest.mark.parametrize("depth,expected_length", [
        (100, 550),
        (150, 550),
        (292, 550),  # Upper bound of short range
        (293, 750),  # Just above → medium range
        (400, 750),
        (450, 750),  # Upper bound of medium range
        (451, 900),  # Just above → long range
        (500, 900),
        (600, 900),
    ])
    def test_depth_to_length(self, depth, expected_length):
        tag = TagSpecification(tag_id="t1", filter_depth=depth)
        tag.compute_housing_length_from_depth()
        assert tag.housing_length == expected_length


class TestDerivationEdgeCases:
    def test_no_depth_no_derivation(self):
        tag = TagSpecification(tag_id="t1")
        tag.compute_housing_length_from_depth()
        assert tag.housing_length is None

    def test_explicit_length_not_overridden(self):
        """If housing_length is already set, depth derivation is skipped."""
        tag = TagSpecification(tag_id="t1", filter_depth=292, housing_length=900)
        tag.compute_housing_length_from_depth()
        assert tag.housing_length == 900  # Not overridden to 550

    def test_merge_tag_auto_derives_length(self):
        """merge_tag calls compute_housing_length_from_depth automatically."""
        from backend.logic.state import TechnicalState
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600, filter_depth=292)
        assert state.tags["item_1"].housing_length == 550

        state.merge_tag("item_2", filter_width=600, filter_height=600, filter_depth=450)
        assert state.tags["item_2"].housing_length == 750

        state.merge_tag("item_3", filter_width=600, filter_height=600, filter_depth=600)
        assert state.tags["item_3"].housing_length == 900


class TestSessionGraphFamilySpecificDerivation:
    """Pin family-specific derivation in session_graph.py."""

    def test_gdmi_derivation(self):
        from backend.logic.session_graph import _derive_housing_length
        assert _derive_housing_length(300, "GDMI") == 600
        assert _derive_housing_length(450, "GDMI") == 600
        assert _derive_housing_length(451, "GDMI") == 850

    def test_gdc_derivation(self):
        from backend.logic.session_graph import _derive_housing_length
        assert _derive_housing_length(300, "GDC") == 750
        assert _derive_housing_length(450, "GDC") == 750
        assert _derive_housing_length(451, "GDC") == 900

    def test_gdb_default_derivation(self):
        from backend.logic.session_graph import _derive_housing_length
        assert _derive_housing_length(200, "GDB") == 550
        assert _derive_housing_length(292, "GDB") == 550
        assert _derive_housing_length(293, "GDB") == 750
        assert _derive_housing_length(450, "GDB") == 750
        assert _derive_housing_length(451, "GDB") == 900

    def test_state_vs_session_graph_consistency(self):
        """Both state.py and session_graph.py now use the same unified function."""
        from backend.logic.session_graph import _derive_housing_length

        # Both should return 900 for depth=500 GDB (unified function has >450→900)
        tag = TagSpecification(tag_id="t1", filter_depth=500)
        tag.compute_housing_length_from_depth()
        state_result = tag.housing_length

        session_result = _derive_housing_length(500, "GDB")

        assert state_result == session_result == 900
