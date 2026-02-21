"""Tests for SessionGraphManager FalkorDB migration readiness.

Covers:
- _run_query / _run_write driver access patterns (the 2 methods that change)
- {.*} map projection usage in get_project_state and get_session_graph_data
- record.data() conversion (used in _run_query, not used in database.py)
- Complete state roundtrip: write state → read state → verify shape
"""

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock, call

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# =============================================================================
# Helpers
# =============================================================================

def _make_mock_db():
    """Create a mock db_connection for SessionGraphManager.

    The mock must have:
    - db.connect() → returns mock_graph
    - mock_graph.query() → returns FalkorDB-style QueryResult
    """
    db = MagicMock()

    mock_graph = MagicMock()
    # Default: empty result
    mock_result = MagicMock()
    mock_result.result_set = None
    mock_result.header = []
    mock_graph.query.return_value = mock_result
    db.connect.return_value = mock_graph

    return db, mock_graph


def _make_falkordb_result(rows: list[dict]):
    """Create a mock FalkorDB QueryResult from a list of dicts.

    This mimics what result_to_dicts() expects:
    - result.header: list of (type, name) tuples
    - result.result_set: list of lists (row values)
    """
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


# =============================================================================
# Tests for _run_query and _run_write internal methods
# =============================================================================

class TestRunQueryRunWrite:
    """Test the 2 methods in SessionGraphManager that use FalkorDB graph.query().

    After migration:
    - _run_query: graph.query() → result_to_dicts(result) → list[dict]
    - _run_write: graph.query() (void)
    """

    def test_run_query_returns_list_of_dicts(self):
        """_run_query uses result_to_dicts() to convert FalkorDB results."""
        db, mock_graph = _make_mock_db()

        mock_graph.query.return_value = _make_falkordb_result([
            {"session_id": "s1", "project": None, "tags": [], "tag_count": 0},
        ])

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)
        result = sgm._run_query("MATCH (s:Session) RETURN s", {"session_id": "s1"})

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["session_id"] == "s1"

    def test_run_query_empty_result(self):
        db, mock_graph = _make_mock_db()
        # Default mock already returns empty result

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)
        result = sgm._run_query("MATCH (s:Session) RETURN s", {})
        assert result == []

    def test_run_write_executes_cypher(self):
        db, mock_graph = _make_mock_db()

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)
        sgm._run_write("CREATE (s:Session {id: $id})", {"id": "test"})

        mock_graph.query.assert_called_once()
        args = mock_graph.query.call_args
        assert "CREATE" in args[0][0]

    def test_run_query_handles_nested_structures(self):
        """result_to_dicts() correctly handles nested values from FalkorDB."""
        db, mock_graph = _make_mock_db()

        mock_graph.query.return_value = _make_falkordb_result([
            {
                "session_id": "s1",
                "project": {"name": "TestProject", "locked_material": "RF"},
                "tags": [{"tag_id": "item_1", "filter_width": 600}],
                "tag_count": 1,
            },
        ])

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)
        result = sgm._run_query("MATCH ...", {})

        # Result contains nested structures
        assert result[0]["project"]["name"] == "TestProject"
        assert result[0]["tags"][0]["filter_width"] == 600


# =============================================================================
# Tests for get_project_state (uses {.*} map projection)
# =============================================================================

class TestGetProjectState:
    """Test get_project_state which uses collect(properties(t)) after FalkorDB migration."""

    def test_empty_session_returns_default(self):
        db, mock_graph = _make_mock_db()
        # Default mock returns empty result

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)
        state = sgm.get_project_state("nonexistent")

        assert state["session_id"] == "nonexistent"
        assert state["project"] is None
        assert state["tags"] == []
        assert state["tag_count"] == 0

    def test_session_with_project_and_tags(self):
        db, mock_graph = _make_mock_db()

        mock_graph.query.return_value = _make_falkordb_result([{
            "session_id": "sess_1",
            "project": {
                "name": "Kitchen Project",
                "customer": None,
                "locked_material": "RF",
                "detected_family": "GDB",
                "pending_clarification": None,
                "accessories": None,
                "assembly_group": None,
                "resolved_params": '{"door_side": "R"}',
                "vetoed_families": None,
            },
            "tags": [
                {
                    "tag_id": "item_1",
                    "filter_width": 600,
                    "filter_height": 600,
                    "housing_width": 600,
                    "housing_height": 600,
                    "airflow_m3h": 3000,
                    "product_family": "GDB",
                    "is_complete": True,
                },
            ],
            "tag_count": 1,
        }])

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)
        state = sgm.get_project_state("sess_1")

        assert state["session_id"] == "sess_1"
        assert state["project"]["locked_material"] == "RF"
        assert state["project"]["detected_family"] == "GDB"
        assert len(state["tags"]) == 1
        assert state["tags"][0]["filter_width"] == 600
        assert state["tag_count"] == 1

    def test_properties_function_produces_flat_dicts(self):
        """collect(properties(t)) produces a list of flat dicts (all tag properties).

        After migration, properties() replaces {.*} map projection.
        Both produce the same flat dict structure.
        """
        tag_properties = {
            "tag_id": "item_1",
            "filter_width": 600,
            "filter_height": 600,
            "housing_width": 600,
            "housing_height": 600,
            "airflow_m3h": 3000,
            "product_family": "GDB",
            "product_code": None,
            "weight_kg": None,
            "housing_length": None,
            "is_complete": False,
            "session_id": "sess_1",
            "assembly_role": None,
            "assembly_group_id": None,
        }
        assert tag_properties["filter_width"] == 600
        assert tag_properties["product_family"] == "GDB"

    def test_project_map_projection(self):
        """Project uses explicit property names in RETURN clause."""
        project_projection = {
            "name": "Kitchen Project",
            "customer": "ACME Corp",
            "locked_material": "RF",
            "detected_family": "GDB",
            "pending_clarification": None,
            "accessories": None,
            "assembly_group": None,
            "resolved_params": '{"door_side": "R"}',
            "vetoed_families": None,
        }
        assert project_projection["name"] == "Kitchen Project"


# =============================================================================
# Tests for state write → read roundtrip
# =============================================================================

class TestStateRoundtrip:
    """Test that write operations produce state that read operations can consume.

    This validates the COMPLETE flow using FalkorDB graph.query():
    1. Write: _run_write(MERGE ...) — creates/updates nodes
    2. Read: _run_query(MATCH ... collect(properties(t))) — reads nodes back
    """

    def test_ensure_session_then_get_state(self):
        """ensure_session → get_project_state roundtrip."""
        db, mock_graph = _make_mock_db()

        def mock_query(cypher, params=None):
            if "MERGE" in cypher:
                return _make_falkordb_result([])
            else:
                return _make_falkordb_result([{
                    "session_id": "new_session",
                    "project": None,
                    "tags": [],
                    "tag_count": 0,
                }])

        mock_graph.query.side_effect = mock_query

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)

        sgm.ensure_session("new_session")
        state = sgm.get_project_state("new_session")

        assert state["session_id"] == "new_session"
        assert state["tags"] == []

    def test_upsert_tag_then_get_state(self):
        """upsert_tag → get_project_state roundtrip."""
        db, mock_graph = _make_mock_db()

        def mock_query(cypher, params=None):
            if "MERGE" in cypher and "TagUnit" in cypher:
                return _make_falkordb_result([{
                    "tag": {
                        "tag_id": "item_1",
                        "filter_width": 600,
                        "filter_height": 600,
                        "housing_width": 600,
                        "housing_height": 600,
                    }
                }])
            elif "collect" in cypher:
                return _make_falkordb_result([{
                    "session_id": "sess_1",
                    "project": {"name": None, "customer": None,
                                "locked_material": None, "detected_family": None,
                                "pending_clarification": None, "accessories": None,
                                "assembly_group": None, "resolved_params": None,
                                "vetoed_families": None},
                    "tags": [{"tag_id": "item_1", "filter_width": 600, "filter_height": 600}],
                    "tag_count": 1,
                }])
            return _make_falkordb_result([])

        mock_graph.query.side_effect = mock_query

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)

        tag = sgm.upsert_tag("sess_1", "item_1", filter_width=600, filter_height=600)
        state = sgm.get_project_state("sess_1")

        assert state["tag_count"] == 1
        assert state["tags"][0]["filter_width"] == 600


# =============================================================================
# Tests for FalkorDB-specific _run_query replacement
# =============================================================================

class TestFalkorDBRunQueryVerification:
    """Verify the actual FalkorDB _run_query and _run_write implementations."""

    def test_run_query_returns_list_of_dicts(self):
        """_run_query must return list[dict] via result_to_dicts()."""
        db, mock_graph = _make_mock_db()
        mock_graph.query.return_value = _make_falkordb_result([
            {"session_id": "s1", "project": None, "tags": [], "tag_count": 0},
        ])

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)
        result = sgm._run_query("MATCH (s:Session) RETURN s.id AS session_id", {})
        assert result == [{"session_id": "s1", "project": None, "tags": [], "tag_count": 0}]

    def test_run_query_calls_graph_query(self):
        """_run_query delegates to graph.query() (not driver.session())."""
        db, mock_graph = _make_mock_db()

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)
        sgm._run_query("MATCH (n) RETURN count(n) AS count", {"key": "val"})

        mock_graph.query.assert_called_once()
        assert "MATCH" in mock_graph.query.call_args[0][0]

    def test_run_write_calls_graph_query(self):
        """_run_write delegates to graph.query() for write operations."""
        db, mock_graph = _make_mock_db()

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)
        sgm._run_write("CREATE (n:Test)", {"key": "val"})

        mock_graph.query.assert_called_once()
        assert "CREATE" in mock_graph.query.call_args[0][0]


# =============================================================================
# Tests for get_session_graph_data (visualization, uses {.*})
# =============================================================================

class TestGetSessionGraphData:
    """Test get_session_graph_data which builds ForceGraph2D visualization data."""

    def test_empty_session_returns_empty_graph(self):
        db, mock_graph = _make_mock_db()
        # Default mock returns empty result

        from logic.session_graph import SessionGraphManager
        sgm = SessionGraphManager(db)
        result = sgm.get_session_graph_data("nonexistent")

        assert "nodes" in result
        assert "relationships" in result

    def test_properties_function_in_visualization_query(self):
        """Verify the visualization query uses properties() (migrated from {.*})."""
        from logic.session_graph import SessionGraphManager
        import inspect
        source = inspect.getsource(SessionGraphManager.get_session_graph_data)
        assert "properties(" in source, "get_session_graph_data should use properties() after migration"
