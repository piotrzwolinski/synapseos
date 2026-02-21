"""Tests for bulk_offer.py database access patterns.

bulk_offer.py uses db.connect() to get the FalkorDB graph and calls
graph.query() directly. This file provides test coverage for those DB
interactions using FalkorDB-style mock results.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# =============================================================================
# Mock helpers
# =============================================================================

def _make_mock_db_for_bulk_offer():
    """Create a mock db that simulates FalkorDB graph.query() pattern."""
    db = MagicMock()
    mock_graph = MagicMock()
    db.connect.return_value = mock_graph
    return db, mock_graph


def _make_falkordb_result(rows: list[dict]):
    """Create a mock FalkorDB QueryResult from a list of dicts."""
    if not rows:
        result = MagicMock()
        result.result_set = None
        result.header = []
        return result

    headers = list(rows[0].keys())
    result = MagicMock()
    result.header = [(0, h) for h in headers]
    result.result_set = [[row.get(h) for h in headers] for row in rows]
    return result


def _make_falkordb_single_result(row: dict | None):
    """Create a mock FalkorDB QueryResult with a single row (or empty)."""
    if row is None:
        result = MagicMock()
        result.result_set = None
        result.header = []
        return result
    return _make_falkordb_result([row])


# =============================================================================
# Tests for _load_housing_variants (line 559)
# =============================================================================

class TestLoadHousingVariants:
    """Test _load_housing_variants which loads GDMI product variants."""

    def test_returns_list_of_dicts(self):
        """The method uses result_to_dicts(result) pattern."""
        db, mock_graph = _make_mock_db_for_bulk_offer()

        variant_data = [
            {"name": "GDMI 600x600", "width_mm": 600, "height_mm": 600,
             "family": "FAM_GDMI", "airflow": 3400.0, "weight_kg": 45.0,
             "housing_length": 550},
            {"name": "GDMI 300x600", "width_mm": 300, "height_mm": 600,
             "family": "FAM_GDMI", "airflow": 1700.0, "weight_kg": 25.0,
             "housing_length": 550},
        ]
        mock_graph.query.return_value = _make_falkordb_result(variant_data)

        from bulk_offer import _load_housing_variants
        import bulk_offer
        bulk_offer._variants_cache = None

        result = _load_housing_variants(db)
        assert len(result) == 2
        assert result[0]["width_mm"] == 600
        assert result[1]["airflow"] == 1700.0

        db.connect.assert_called_once()
        bulk_offer._variants_cache = None

    def test_uses_cache_on_second_call(self):
        """Verify caching works — second call doesn't hit DB."""
        import bulk_offer
        bulk_offer._variants_cache = [{"name": "cached", "width_mm": 600}]

        db = MagicMock()
        from bulk_offer import _load_housing_variants
        result = _load_housing_variants(db)
        assert result[0]["name"] == "cached"
        db.connect.assert_not_called()

        bulk_offer._variants_cache = None


# =============================================================================
# Tests for _load_capacity_rules (line 583)
# =============================================================================

class TestLoadCapacityRules:
    """Test _load_capacity_rules which loads CapacityRule nodes."""

    def test_returns_list_of_dicts(self):
        db, mock_graph = _make_mock_db_for_bulk_offer()

        rule_data = [
            {"id": "CAP_GDMI_600x600", "module_descriptor": "600x600", "output_rating": 3400.0},
            {"id": "CAP_GDMI_300x600", "module_descriptor": "300x600", "output_rating": 1700.0},
        ]
        mock_graph.query.return_value = _make_falkordb_result(rule_data)

        import bulk_offer
        bulk_offer._capacity_cache = None

        result = bulk_offer._load_capacity_rules(db)
        assert len(result) == 2
        assert result[0]["module_descriptor"] == "600x600"

        bulk_offer._capacity_cache = None


# =============================================================================
# Tests for _load_filters_for_class (line 632)
# =============================================================================

class TestLoadFiltersForClass:
    """Test _load_filters_for_class which loads FilterConsumable nodes."""

    def test_returns_grouped_dict(self):
        db, mock_graph = _make_mock_db_for_bulk_offer()

        filter_data = [
            {"name": "F7 Full", "model_name": "F7-592x592", "filter_class": "F7",
             "dimensions": "592x592", "part_number": "P001",
             "module_width": 592, "module_height": 592},
            {"name": "F7 Half-W", "model_name": "F7-287x592", "filter_class": "F7",
             "dimensions": "287x592", "part_number": "P002",
             "module_width": 287, "module_height": 592},
        ]
        mock_graph.query.return_value = _make_falkordb_result(filter_data)

        from bulk_offer import _load_filters_for_class
        result = _load_filters_for_class("F7", db)

        assert result["full"]["name"] == "F7 Full"
        assert result["half_width"]["name"] == "F7 Half-W"
        assert result["half_height"] is None  # Not in test data


# =============================================================================
# Tests for _graph_lookup_competitor (line 1643)
# =============================================================================

class TestGraphLookupCompetitor:
    """Test _graph_lookup_competitor which uses result_single()."""

    def test_match_found_returns_dict(self):
        db, mock_graph = _make_mock_db_for_bulk_offer()

        match_data = {
            "competitor_model": "XYZ-600",
            "target_type": "ProductVariant",
            "target_name": "GDB 600x600",
            "part_number": "GDB-600x600-550-R-PG-FZ",
            "confidence": 0.95,
            "match_type": "exact",
            "dimension_note": "Same dimensions",
            "performance_note": None,
        }
        mock_graph.query.return_value = _make_falkordb_single_result(match_data)

        from bulk_offer import _graph_lookup_competitor, CompetitorItem, GraphTrace
        item = CompetitorItem(
            line_id=1,
            raw_text="XYZ-600 panel filter",
            competitor_manufacturer="CompetitorCo",
            competitor_model="XYZ-600",
            competitor_code="XYZ-600",
            category="panel_filter",
            iso_class="F7",
            width_mm=600,
            height_mm=600,
            depth_mm=50,
            quantity=1,
        )
        trace = GraphTrace()
        result = _graph_lookup_competitor(item, db, trace)

        assert result is not None
        assert result["target_name"] == "GDB 600x600"
        assert result["confidence"] == 0.95

    def test_no_match_returns_none(self):
        db, mock_graph = _make_mock_db_for_bulk_offer()

        mock_graph.query.return_value = _make_falkordb_single_result(None)

        from bulk_offer import _graph_lookup_competitor, CompetitorItem, GraphTrace
        item = CompetitorItem(
            line_id=2,
            raw_text="NOEXIST unknown",
            competitor_manufacturer="Unknown",
            competitor_model="NOEXIST",
            competitor_code="NOEXIST",
            category="unknown",
            iso_class="",
            width_mm=0,
            height_mm=0,
            depth_mm=0,
            quantity=1,
        )
        trace = GraphTrace()
        result = _graph_lookup_competitor(item, db, trace)
        assert result is None


# =============================================================================
# Tests for _graph_fuzzy_lookup (line 1688)
# =============================================================================

class TestGraphFuzzyLookup:
    """Test _graph_fuzzy_lookup which uses result_single()."""

    def test_fuzzy_match_found(self):
        db, mock_graph = _make_mock_db_for_bulk_offer()

        match_data = {
            "competitor_model": "ABC-610",
            "target_name": "GDB 600x600",
            "part_number": "GDB-600x600-550-R-PG-FZ",
            "confidence": 0.7,
            "match_type": "fuzzy_dimension",
            "dimension_note": "Width within 20mm tolerance",
            "performance_note": None,
        }
        mock_graph.query.return_value = _make_falkordb_single_result(match_data)

        from bulk_offer import _graph_fuzzy_lookup, CompetitorItem, GraphTrace
        item = CompetitorItem(
            line_id=3,
            raw_text="ABC-610 panel filter",
            competitor_manufacturer="CompetitorCo",
            competitor_model="ABC-610",
            competitor_code="ABC-610",
            category="panel_filter",
            iso_class="F7",
            width_mm=610,
            height_mm=600,
            depth_mm=50,
            quantity=1,
        )
        trace = GraphTrace()
        result = _graph_fuzzy_lookup(item, db, trace)
        assert result is not None
        assert result["confidence"] == 0.7

    def test_fuzzy_no_match(self):
        db, mock_graph = _make_mock_db_for_bulk_offer()

        mock_graph.query.return_value = _make_falkordb_single_result(None)

        from bulk_offer import _graph_fuzzy_lookup, CompetitorItem, GraphTrace
        item = CompetitorItem(
            line_id=4,
            raw_text="NOEXIST unknown",
            competitor_manufacturer="Unknown",
            competitor_model="NOEXIST",
            competitor_code="NOEXIST",
            category="unknown",
            iso_class="",
            width_mm=9999,
            height_mm=9999,
            depth_mm=0,
            quantity=1,
        )
        trace = GraphTrace()
        result = _graph_fuzzy_lookup(item, db, trace)
        assert result is None


# =============================================================================
# Tests for pure logic functions (no DB, migration-safe)
# =============================================================================

class TestBulkOfferPureLogic:
    """Test pure functions in bulk_offer.py that don't touch the DB."""

    def test_find_best_variant_exact_match(self):
        from bulk_offer import _find_best_variant
        variants = [
            {"family": "FAM_GDMI", "width_mm": 300, "height_mm": 600, "airflow": 1700},
            {"family": "FAM_GDMI", "width_mm": 600, "height_mm": 600, "airflow": 3400},
            {"family": "FAM_GDMI", "width_mm": 900, "height_mm": 600, "airflow": 5100},
        ]
        result = _find_best_variant(600, 600, variants)
        assert result["width_mm"] == 600

    def test_find_best_variant_smallest_fitting(self):
        from bulk_offer import _find_best_variant
        variants = [
            {"family": "FAM_GDMI", "width_mm": 600, "height_mm": 600, "airflow": 3400},
            {"family": "FAM_GDMI", "width_mm": 900, "height_mm": 600, "airflow": 5100},
        ]
        result = _find_best_variant(500, 500, variants)
        assert result["width_mm"] == 600  # smallest that fits

    def test_find_best_variant_no_fit_returns_largest(self):
        from bulk_offer import _find_best_variant
        variants = [
            {"family": "FAM_GDMI", "width_mm": 300, "height_mm": 600, "airflow": 1700},
            {"family": "FAM_GDMI", "width_mm": 600, "height_mm": 600, "airflow": 3400},
        ]
        result = _find_best_variant(1200, 1200, variants)
        assert result["width_mm"] == 600  # largest available

    def test_get_capacity_exact(self):
        from bulk_offer import _get_capacity
        rules = [
            {"module_descriptor": "600x600", "output_rating": 3400.0},
            {"module_descriptor": "300x600", "output_rating": 1700.0},
        ]
        assert _get_capacity(600, 600, rules) == 3400.0
        assert _get_capacity(300, 600, rules) == 1700.0

    def test_get_capacity_computed(self):
        from bulk_offer import _get_capacity
        # No exact match → compute from base modules
        cap = _get_capacity(1200, 600, [])
        assert cap == 3400.0 * 2  # 2 horizontal modules
