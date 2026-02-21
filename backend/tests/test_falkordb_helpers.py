"""Tests for the FalkorDB migration adapter layer (db_result_helpers.py).

These tests validate the production helper functions (result_to_dicts, result_single,
result_value) that convert FalkorDB's list-of-lists result format back into the
dict-based format that all 140 database.py methods expect.

Tests use FakeQueryResult/FakeNode/FakeEdge to simulate FalkorDB driver output
without requiring the falkordb package to be installed.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db_result_helpers import result_to_dicts, result_single, result_value, _unwrap_value


# =============================================================================
# Simulate FalkorDB QueryResult for testing helper methods
# =============================================================================

class FakeQueryResult:
    """Simulates FalkorDB's QueryResult object.

    FalkorDB returns:
      - header: list of (type_int, column_name) tuples
      - result_set: list of lists (positional, NOT named dicts)
    """
    def __init__(self, header: list[tuple], result_set: list[list]):
        self._header = header
        self._result_set = result_set

    @property
    def header(self):
        return self._header

    @property
    def result_set(self):
        return self._result_set


class FakeNode:
    """Simulates FalkorDB's Node object returned for full node queries."""
    def __init__(self, node_id, labels, properties):
        self.id = node_id
        self.labels = labels
        self.properties = properties

    def __repr__(self):
        return f"Node({self.labels}, {self.properties})"


class FakeEdge:
    """Simulates FalkorDB's Edge object returned for full relationship queries."""
    def __init__(self, edge_id, relation, src_id, dest_id, properties):
        self.id = edge_id
        self.relation = relation
        self.src_node = src_id
        self.dest_node = dest_id
        self.properties = properties


# =============================================================================
# TESTS: Basic dict conversion from list-of-lists
# =============================================================================

class TestResultToDictConversion:
    """Test the core conversion that underpins all 140 database.py methods."""

    def test_empty_result_returns_empty_list(self):
        result = FakeQueryResult(header=[], result_set=[])
        assert result_to_dicts(result) == []

    def test_none_result_set_returns_empty_list(self):
        result = FakeQueryResult(header=[], result_set=None)
        assert result_to_dicts(result) == []

    def test_single_row_single_column(self):
        result = FakeQueryResult(
            header=[(1, "count")],
            result_set=[[42]],
        )
        rows = result_to_dicts(result)
        assert rows == [{"count": 42}]

    def test_single_row_multiple_columns(self):
        """The most common pattern: RETURN n.name AS name, n.age AS age"""
        result = FakeQueryResult(
            header=[(1, "name"), (1, "age"), (1, "active")],
            result_set=[["Alice", 30, True]],
        )
        rows = result_to_dicts(result)
        assert rows == [{"name": "Alice", "age": 30, "active": True}]

    def test_multiple_rows(self):
        """Validates the [dict(record) for record in result] pattern (70 occurrences)."""
        result = FakeQueryResult(
            header=[(1, "id"), (1, "name")],
            result_set=[
                ["STR_GREASE", "Grease Aerosol"],
                ["STR_DUST", "Dust Particles"],
                ["STR_ODOR", "Odor Molecules"],
            ],
        )
        rows = result_to_dicts(result)
        assert len(rows) == 3
        assert rows[0] == {"id": "STR_GREASE", "name": "Grease Aerosol"}
        assert rows[2] == {"id": "STR_ODOR", "name": "Odor Molecules"}

    def test_null_values_preserved(self):
        """Some columns may be NULL (e.g., OPTIONAL MATCH returns)."""
        result = FakeQueryResult(
            header=[(1, "name"), (1, "description")],
            result_set=[["GDB", None]],
        )
        rows = result_to_dicts(result)
        assert rows[0]["description"] is None

    def test_nested_list_values(self):
        """FalkorDB preserves list properties (e.g., matched_keywords)."""
        result = FakeQueryResult(
            header=[(1, "id"), (1, "matched_keywords"), (1, "match_count")],
            result_set=[["STR_GREASE", ["kitchen", "grease"], 2]],
        )
        rows = result_to_dicts(result)
        assert rows[0]["matched_keywords"] == ["kitchen", "grease"]

    def test_float_and_int_types_preserved(self):
        """Numeric types must survive conversion (engine uses >=, <= operators)."""
        result = FakeQueryResult(
            header=[(1, "width_mm"), (1, "height_mm"), (1, "rated_airflow"), (1, "score")],
            result_set=[[600, 600, 3400.0, 0.95]],
        )
        rows = result_to_dicts(result)
        assert isinstance(rows[0]["width_mm"], int)
        assert isinstance(rows[0]["rated_airflow"], float)
        assert isinstance(rows[0]["score"], float)

    def test_boolean_values(self):
        """Boolean values from graph properties."""
        result = FakeQueryResult(
            header=[(1, "feasible"), (1, "indoor_only")],
            result_set=[[True, False]],
        )
        rows = result_to_dicts(result)
        assert rows[0]["feasible"] is True
        assert rows[0]["indoor_only"] is False


# =============================================================================
# TESTS: Single-record extraction (result.single() replacement)
# =============================================================================

class TestSingleRecordConversion:
    """Test _query_single — replaces result.single() (50 occurrences)."""

    def test_empty_result_returns_none(self):
        result = FakeQueryResult(header=[], result_set=[])
        assert result_single(result) is None

    def test_single_row_returns_dict(self):
        result = FakeQueryResult(
            header=[(1, "count")],
            result_set=[[150]],
        )
        row = result_single(result)
        assert row == {"count": 150}

    def test_multiple_rows_returns_first(self):
        """When multiple rows exist, return the first (matches Neo4j .single() for 1-row queries)."""
        result = FakeQueryResult(
            header=[(1, "name")],
            result_set=[["first"], ["second"]],
        )
        row = result_single(result)
        assert row == {"name": "first"}

    def test_single_field_extraction_pattern(self):
        """Validates: record["count"] if record else 0"""
        result = FakeQueryResult(
            header=[(1, "count")],
            result_set=[[42]],
        )
        row = result_single(result)
        assert row["count"] == 42

    def test_none_result_with_default(self):
        """Validates: return row["count"] if row else 0"""
        result = FakeQueryResult(header=[], result_set=[])
        row = result_single(result)
        value = row["count"] if row else 0
        assert value == 0

    def test_dict_conversion_from_single(self):
        """Validates: dict(record) if record else None — the record IS already a dict."""
        result = FakeQueryResult(
            header=[(1, "session_id"), (1, "project_name"), (1, "detected_family")],
            result_set=[["sess_123", "TestProject", "GDB"]],
        )
        row = result_single(result)
        # dict(row) should be idempotent since row is already a dict
        assert dict(row) == {"session_id": "sess_123", "project_name": "TestProject", "detected_family": "GDB"}


# =============================================================================
# TESTS: Node/Edge object handling
# =============================================================================

class TestNodeEdgeConversion:
    """Test that FalkorDB Node/Edge objects are properly converted to dicts.

    When Cypher returns `RETURN n` (full node) instead of `RETURN n.name`,
    FalkorDB returns a Node object, not a dict.
    """

    def test_node_converted_to_dict(self):
        node = FakeNode(
            node_id=42,
            labels=["ProductFamily"],
            properties={"name": "GDB", "type": "particle_filter", "selection_priority": 10},
        )
        result = FakeQueryResult(
            header=[(1, "node")],
            result_set=[[node]],
        )
        rows = result_to_dicts(result)
        assert rows[0]["node"]["name"] == "GDB"
        assert rows[0]["node"]["_labels"] == ["ProductFamily"]
        assert rows[0]["node"]["selection_priority"] == 10

    def test_edge_converted_to_dict(self):
        edge = FakeEdge(
            edge_id=99,
            relation="HAS_TRAIT",
            src_id=1,
            dest_id=2,
            properties={"confidence": 0.95, "source": "direct"},
        )
        result = FakeQueryResult(
            header=[(1, "rel")],
            result_set=[[edge]],
        )
        rows = result_to_dicts(result)
        assert rows[0]["rel"]["_type"] == "HAS_TRAIT"
        assert rows[0]["rel"]["confidence"] == 0.95

    def test_mixed_node_and_scalars(self):
        """Common pattern: RETURN n, score — node + scalar in same row."""
        node = FakeNode(42, ["Concept"], {"name": "Kitchen ventilation", "description": "Cooking exhaust"})
        result = FakeQueryResult(
            header=[(1, "node"), (1, "score")],
            result_set=[[node, 0.92]],
        )
        rows = result_to_dicts(result)
        assert rows[0]["score"] == 0.92
        assert rows[0]["node"]["name"] == "Kitchen ventilation"

    def test_null_node_in_optional_match(self):
        """OPTIONAL MATCH returns None for unmatched nodes."""
        result = FakeQueryResult(
            header=[(1, "s_id"), (1, "p_props")],
            result_set=[["sess_1", None]],
        )
        rows = result_to_dicts(result)
        assert rows[0]["p_props"] is None


# =============================================================================
# TESTS: Return shape contract — validates mock_db fixtures match
# =============================================================================

class TestReturnShapeContract:
    """Validate that FalkorDB helper output matches the shapes in conftest.py.

    Each test constructs a FakeQueryResult mimicking what FalkorDB would return,
    then verifies the conversion produces the same shape as the conftest mock.
    """

    def test_stressor_shape(self):
        """Matches conftest mock_db.get_stressors_by_keywords shape."""
        result = FakeQueryResult(
            header=[
                (1, "id"), (1, "name"), (1, "description"),
                (1, "category"), (1, "matched_keywords"), (1, "match_count"),
            ],
            result_set=[[
                "STR_GREASE", "Grease Aerosol", "Airborne grease particles from cooking",
                "Contamination", ["kitchen", "grease"], 2,
            ]],
        )
        rows = result_to_dicts(result)
        stressor = rows[0]
        assert stressor["id"] == "STR_GREASE"
        assert stressor["name"] == "Grease Aerosol"
        assert stressor["matched_keywords"] == ["kitchen", "grease"]
        assert stressor["match_count"] == 2

    def test_product_family_shape(self):
        """Matches conftest mock_db.get_all_product_families_with_traits shape."""
        result = FakeQueryResult(
            header=[
                (1, "product_id"), (1, "product_name"), (1, "product_type"),
                (1, "selection_priority"), (1, "direct_trait_ids"),
                (1, "material_trait_ids"), (1, "all_trait_ids"),
            ],
            result_set=[[
                "FAM_GDB", "GDB", "particle_filter",
                10, ["TRAIT_PARTICLE"], [], ["TRAIT_PARTICLE"],
            ]],
        )
        rows = result_to_dicts(result)
        pf = rows[0]
        assert pf["product_id"] == "FAM_GDB"
        assert pf["selection_priority"] == 10
        assert pf["direct_trait_ids"] == ["TRAIT_PARTICLE"]

    def test_dimension_module_shape(self):
        """Matches conftest mock_db.get_available_dimension_modules shape."""
        result = FakeQueryResult(
            header=[
                (1, "variant_id"), (1, "width_mm"), (1, "height_mm"),
                (1, "rated_airflow"), (1, "name"),
            ],
            result_set=[
                ["GDB-600x600", 600, 600, 3400, "GDB 600x600"],
                ["GDB-300x600", 300, 600, 1700, "GDB 300x600"],
            ],
        )
        rows = result_to_dicts(result)
        assert len(rows) == 2
        assert rows[0]["width_mm"] == 600
        assert rows[1]["rated_airflow"] == 1700

    def test_vector_search_shape(self):
        """Matches conftest mock_db.vector_search_concepts shape."""
        result = FakeQueryResult(
            header=[(1, "concept"), (1, "description"), (1, "score")],
            result_set=[
                ["Kitchen ventilation", "Cooking exhaust systems", 0.92],
            ],
        )
        rows = result_to_dicts(result)
        assert rows[0]["concept"] == "Kitchen ventilation"
        assert rows[0]["score"] == 0.92

    def test_causal_rule_shape(self):
        """Matches conftest mock_db.get_causal_rules_for_stressors shape."""
        result = FakeQueryResult(
            header=[
                (1, "rule_type"), (1, "stressor_id"), (1, "stressor_name"),
                (1, "trait_id"), (1, "trait_name"), (1, "severity"), (1, "explanation"),
            ],
            result_set=[[
                "NEUTRALIZED_BY", "STR_GREASE", "Grease Aerosol",
                "TRAIT_GREASE_PRE", "Grease Pre-Filtration", "CRITICAL",
                "Grease clogs carbon filters; pre-filtration required",
            ]],
        )
        rows = result_to_dicts(result)
        rule = rows[0]
        assert rule["rule_type"] == "NEUTRALIZED_BY"
        assert rule["severity"] == "CRITICAL"

    def test_application_shape(self):
        """Matches conftest mock_db.get_all_applications shape."""
        result = FakeQueryResult(
            header=[(1, "id"), (1, "name"), (1, "keywords")],
            result_set=[
                ["APP_KITCHEN", "Commercial Kitchen", ["kitchen", "restaurant", "cooking"]],
            ],
        )
        rows = result_to_dicts(result)
        assert rows[0]["keywords"] == ["kitchen", "restaurant", "cooking"]


# =============================================================================
# TESTS: Peek guard replacement (3 occurrences in database.py)
# =============================================================================

class TestPeekGuardReplacement:
    """Validate that _query_single replaces result.peek() + result.single() correctly.

    Neo4j pattern:  dict(result.single()) if result.peek() else {default}
    FalkorDB:       row if (row := _query_single(...)) else {default}
    """

    def test_peek_with_data_returns_dict(self):
        """Lines 4081, 4244, 4333: result exists → return dict(record)."""
        result = FakeQueryResult(
            header=[
                (1, "housing_corrosion_class"), (1, "indoor_only"),
                (1, "outdoor_safe"), (1, "construction_type"),
            ],
            result_set=[["C2", False, True, "BOLTED"]],
        )
        row = result_single(result)
        # Simulates: dict(pf_result.single()) if pf_result.peek() else {}
        pf_meta = row if row else {}
        assert pf_meta["housing_corrosion_class"] == "C2"
        assert pf_meta["indoor_only"] is False

    def test_peek_empty_returns_default(self):
        """Lines 4081, 4244, 4333: no result → return default dict."""
        result = FakeQueryResult(header=[], result_set=[])
        row = result_single(result)
        # Simulates: dict(result.single()) if result.peek() else {default}
        pf_meta = row if row else {}
        assert pf_meta == {}

    def test_conversation_detail_peek_pattern(self):
        """Line 4244: proj_result.peek() for conversation detail."""
        # Has data
        result = FakeQueryResult(
            header=[
                (1, "session_id"), (1, "project_name"),
                (1, "detected_family"), (1, "locked_material"), (1, "resolved_params"),
            ],
            result_set=[["sess_1", "Kitchen Project", "GDB", "RF", '{"door_side": "R"}']],
        )
        row = result_single(result)
        proj = row if row else {
            "session_id": "sess_1", "project_name": None,
            "detected_family": None, "locked_material": None, "resolved_params": None,
        }
        assert proj["project_name"] == "Kitchen Project"

    def test_expert_reviews_summary_peek_pattern(self):
        """Line 4333: stats_result.peek() for expert reviews."""
        result = FakeQueryResult(
            header=[(1, "total"), (1, "positive"), (1, "negative")],
            result_set=[[10, 7, 3]],
        )
        row = result_single(result)
        stats = row if row else {"total": 0, "positive": 0, "negative": 0}
        assert stats["total"] == 10
        assert stats["positive"] == 7


# =============================================================================
# TESTS: result_value helper (single-value extraction)
# =============================================================================

class TestResultValue:
    """Test result_value — shorthand for extracting a single field."""

    def test_extracts_value(self):
        result = FakeQueryResult(
            header=[(1, "count")],
            result_set=[[42]],
        )
        assert result_value(result, "count") == 42

    def test_returns_default_on_empty(self):
        result = FakeQueryResult(header=[], result_set=[])
        assert result_value(result, "count", 0) == 0

    def test_returns_default_on_missing_key(self):
        result = FakeQueryResult(
            header=[(1, "name")],
            result_set=[["Alice"]],
        )
        assert result_value(result, "age", -1) == -1

    def test_returns_none_as_default(self):
        result = FakeQueryResult(header=[], result_set=[])
        assert result_value(result, "anything") is None


# =============================================================================
# TESTS: _unwrap_value duck-typing
# =============================================================================

class TestUnwrapValue:
    """Test that _unwrap_value correctly duck-types Node/Edge objects."""

    def test_none_passthrough(self):
        assert _unwrap_value(None) is None

    def test_scalar_passthrough(self):
        assert _unwrap_value(42) == 42
        assert _unwrap_value("hello") == "hello"
        assert _unwrap_value(3.14) == 3.14

    def test_list_passthrough(self):
        assert _unwrap_value([1, 2, 3]) == [1, 2, 3]

    def test_node_unwrap(self):
        node = FakeNode(1, ["Session"], {"session_id": "s1", "last_active": 123})
        result = _unwrap_value(node)
        assert result["session_id"] == "s1"
        assert result["_labels"] == ["Session"]
        assert result["_id"] == 1

    def test_edge_unwrap(self):
        edge = FakeEdge(99, "HAS_TAG", 1, 2, {"weight": 1.0})
        result = _unwrap_value(edge)
        assert result["_type"] == "HAS_TAG"
        assert result["weight"] == 1.0
        assert result["_id"] == 99
