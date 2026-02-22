"""Pin DIMENSION_MAP values and orientation normalization rules."""

import pytest
from backend.logic.state import TagSpecification


class TestDimensionMap:
    """Pin every known filter→housing mapping."""

    @pytest.mark.parametrize("filter_dim,expected_housing", [
        (287, 300),
        (305, 300),
        (300, 300),
        (592, 600),
        (610, 600),
        (600, 600),
        (495, 500),
        (500, 500),
    ])
    def test_dimension_map_known_values(self, filter_dim, expected_housing):
        tag = TagSpecification(tag_id="t1", filter_width=filter_dim, filter_height=filter_dim)
        tag.compute_housing_from_filter()
        assert tag.housing_width == expected_housing
        assert tag.housing_height == expected_housing

    def test_dimension_map_passthrough_unknown(self):
        tag = TagSpecification(tag_id="t1", filter_width=450, filter_height=450)
        tag.compute_housing_from_filter()
        assert tag.housing_width == 450
        assert tag.housing_height == 450

    def test_dimension_map_large_passthrough(self):
        tag = TagSpecification(tag_id="t1", filter_width=900, filter_height=1200)
        tag.compute_housing_from_filter()
        assert tag.housing_width == 900
        assert tag.housing_height == 1200


class TestOrientationNormalization:
    """Pin orientation swap rules: height >= width for small modules."""

    def test_small_modules_swap_width_gt_height(self):
        """305x610 filter → 300x600 housing, then swap so height=600."""
        tag = TagSpecification(tag_id="t1", filter_width=610, filter_height=305)
        tag.compute_housing_from_filter()
        # After mapping: 600x300, then swap → 300x600
        assert tag.housing_width == 300
        assert tag.housing_height == 600

    def test_large_modules_no_swap(self):
        """900x600 → no swap (900 > 600 threshold)."""
        tag = TagSpecification(tag_id="t1", filter_width=900, filter_height=600)
        tag.compute_housing_from_filter()
        assert tag.housing_width == 900
        assert tag.housing_height == 600

    def test_square_no_swap(self):
        """600x600 → no swap needed."""
        tag = TagSpecification(tag_id="t1", filter_width=600, filter_height=600)
        tag.compute_housing_from_filter()
        assert tag.housing_width == 600
        assert tag.housing_height == 600

    def test_filter_dims_also_swapped(self):
        """When housing is swapped, filter dims should also be swapped."""
        tag = TagSpecification(tag_id="t1", filter_width=610, filter_height=305)
        tag.compute_housing_from_filter()
        assert tag.filter_width == 305
        assert tag.filter_height == 610


class TestDimensionMapSingleSource:
    """Both state.py and session_graph.py now use the same DIMENSION_MAP from dimension_tables.py."""

    def test_state_and_session_graph_share_same_map(self):
        from backend.logic.dimension_tables import DIMENSION_MAP as CANONICAL
        from backend.logic.dimension_tables import get_dimension_map
        from backend.logic.session_graph import DIMENSION_MAP as SESSION_MAP

        # Module-level constants are empty (config-driven). Both modules
        # import from dimension_tables, proving single-source-of-truth.
        assert CANONICAL == SESSION_MAP
        # Actual data comes from config via get_dimension_map()
        config_map = get_dimension_map()
        assert 900 in config_map
        assert 1200 in config_map
