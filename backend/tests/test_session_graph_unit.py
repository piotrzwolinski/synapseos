"""Session Graph Manager unit tests — Layer 4 state management.

Tests the SessionGraphManager logic with a mocked DB driver.
Verifies:
- Correct Cypher queries are constructed
- Parameters are passed correctly
- FOREACH patterns work (migration-critical: FalkorDB doesn't support FOREACH)
- Sibling sync in assembly groups
- State retrieval formatting
"""

import json
import pytest
from unittest.mock import MagicMock, call, patch

from backend.logic.session_graph import SessionGraphManager


@pytest.fixture
def mock_driver():
    """Mock Neo4j driver with session context manager."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session


@pytest.fixture
def sgm(mock_driver):
    """SessionGraphManager with mocked driver."""
    driver, session = mock_driver
    db = MagicMock()
    db.driver = driver
    db.database = "neo4j"
    return SessionGraphManager(db), session


# =============================================================================
# SESSION LIFECYCLE
# =============================================================================

class TestSessionLifecycle:
    def test_ensure_session_calls_merge(self, sgm):
        mgr, session = sgm
        mgr.ensure_session("test_session_1")
        session.run.assert_called_once()
        cypher = session.run.call_args[0][0]
        assert "MERGE (s:Session {id: $session_id})" in cypher
        params = session.run.call_args[0][1]
        assert params["session_id"] == "test_session_1"

    def test_clear_session_detach_deletes(self, sgm):
        mgr, session = sgm
        mgr.clear_session("test_session_1")
        cypher = session.run.call_args[0][0]
        assert "DETACH DELETE" in cypher
        assert "Session {id: $session_id}" in cypher

    def test_cleanup_stale_sessions_uses_cutoff(self, sgm):
        mgr, session = sgm
        session.run.return_value = iter([{"cleaned": 3}])
        # Mock _run_query to return list of dicts
        mgr._run_query = MagicMock(return_value=[{"cleaned": 3}])
        cleaned = mgr.cleanup_stale_sessions(max_age_ms=3600000)
        assert cleaned == 3


# =============================================================================
# PROJECT MANAGEMENT
# =============================================================================

class TestProjectManagement:
    def test_set_project_creates_active_project(self, sgm):
        mgr, session = sgm
        mgr.set_project("sess1", "MyProject", customer="Acme")
        cypher = session.run.call_args[0][0]
        assert "ActiveProject" in cypher
        assert "MERGE" in cypher
        params = session.run.call_args[0][1]
        assert params["project_name"] == "MyProject"
        assert params["customer"] == "Acme"

    def test_lock_material_links_to_layer1(self, sgm):
        mgr, session = sgm
        mgr.lock_material("sess1", "RF")
        cypher = session.run.call_args[0][0]
        assert "USES_MATERIAL" in cypher
        assert "Material {code: $material_code}" in cypher
        params = session.run.call_args[0][1]
        assert params["material_code"] == "RF"

    def test_lock_material_uppercases_code(self, sgm):
        mgr, session = sgm
        mgr.lock_material("sess1", "rf")
        params = session.run.call_args[0][1]
        assert params["material_code"] == "RF"

    def test_set_detected_family_links_to_layer1(self, sgm):
        mgr, session = sgm
        mgr.set_detected_family("sess1", "GDB")
        cypher = session.run.call_args[0][0]
        assert "TARGETS_FAMILY" in cypher
        assert "ProductFamily {id: $family_id}" in cypher
        params = session.run.call_args[0][1]
        assert params["family"] == "GDB"
        assert params["family_id"] == "FAM_GDB"

    def test_set_pending_clarification(self, sgm):
        mgr, session = sgm
        mgr.set_pending_clarification("sess1", "door_side")
        params = session.run.call_args[0][1]
        assert params["param_name"] == "door_side"

    def test_clear_pending_clarification(self, sgm):
        mgr, session = sgm
        mgr.set_pending_clarification("sess1", None)
        params = session.run.call_args[0][1]
        assert params["param_name"] is None

    def test_set_accessories(self, sgm):
        mgr, session = sgm
        mgr.set_accessories("sess1", ["ACC_RAIN_HOOD", "ACC_FILTER_RACK"])
        params = session.run.call_args[0][1]
        assert params["accessories"] == ["ACC_RAIN_HOOD", "ACC_FILTER_RACK"]

    def test_set_assembly_group_stores_json(self, sgm):
        mgr, session = sgm
        assembly = {
            "group_id": "asm_1",
            "stages": [
                {"role": "PROTECTOR", "product_family": "GDP"},
                {"role": "TARGET", "product_family": "GDC"},
            ],
        }
        mgr.set_assembly_group("sess1", assembly)
        params = session.run.call_args[0][1]
        parsed = json.loads(params["assembly_json"])
        assert parsed["group_id"] == "asm_1"
        assert len(parsed["stages"]) == 2

    def test_set_resolved_params_stores_json(self, sgm):
        mgr, session = sgm
        mgr.set_resolved_params("sess1", {"connection_type": "PG", "door_side": "R"})
        params = session.run.call_args[0][1]
        parsed = json.loads(params["params_json"])
        assert parsed["connection_type"] == "PG"

    def test_set_vetoed_families_stores_json(self, sgm):
        mgr, session = sgm
        mgr.set_vetoed_families("sess1", ["FAM_GDC_FLEX", "FAM_GDMI"])
        params = session.run.call_args[0][1]
        parsed = json.loads(params["vetoed_json"])
        assert "FAM_GDC_FLEX" in parsed


# =============================================================================
# CONVERSATION HISTORY
# =============================================================================

class TestConversationHistory:
    def test_store_turn_creates_node(self, sgm):
        mgr, session = sgm
        mgr.store_turn("sess1", "user", "Hello, I need a filter", 1)
        cypher = session.run.call_args[0][0]
        assert "ConversationTurn" in cypher
        assert "MERGE" in cypher
        params = session.run.call_args[0][1]
        assert params["role"] == "user"
        assert params["turn_number"] == 1

    def test_store_turn_truncates_message(self, sgm):
        mgr, session = sgm
        long_msg = "x" * 3000
        mgr.store_turn("sess1", "user", long_msg, 1)
        params = session.run.call_args[0][1]
        assert len(params["message"]) == 2000

    def test_get_recent_turns_reverses_order(self, sgm):
        mgr, _ = sgm
        # Mock _run_query to return turns in DESC order (as query does)
        mgr._run_query = MagicMock(return_value=[
            {"role": "assistant", "message": "Answer 2", "turn_number": 3},
            {"role": "user", "message": "Question 2", "turn_number": 2},
            {"role": "user", "message": "Question 1", "turn_number": 1},
        ])
        turns = mgr.get_recent_turns("sess1", n=3)
        # Should be reversed to chronological (oldest first)
        assert turns[0]["turn_number"] == 1
        assert turns[-1]["turn_number"] == 3


# =============================================================================
# TAG UNIT MANAGEMENT
# =============================================================================

class TestTagUnitManagement:
    def test_upsert_tag_builds_dynamic_set(self, sgm):
        mgr, _ = sgm
        mgr._run_query = MagicMock(return_value=[{
            "tag": {"tag_id": "item_1", "filter_width": 600, "housing_width": 600}
        }])
        mgr._run_write = MagicMock()
        result = mgr.upsert_tag("sess1", "item_1", filter_width=600, filter_height=600)
        cypher = mgr._run_query.call_args[0][0]
        assert "t.filter_width = $filter_width" in cypher
        assert "t.filter_height = $filter_height" in cypher
        assert "t.housing_width = $housing_width" in cypher

    def test_upsert_tag_computes_housing_dimensions(self, sgm):
        mgr, _ = sgm
        mgr._run_query = MagicMock(return_value=[{
            "tag": {"tag_id": "item_1", "housing_width": 600, "housing_height": 600}
        }])
        mgr._run_write = MagicMock()
        mgr.upsert_tag("sess1", "item_1", filter_width=610, filter_height=305)
        params = mgr._run_query.call_args[0][1]
        # 610 → 600 housing, 305 → 300 housing (dimension mapping)
        assert params["housing_width"] == 600
        assert params["housing_height"] == 300

    def test_upsert_tag_null_fields_not_in_set(self, sgm):
        mgr, _ = sgm
        mgr._run_query = MagicMock(return_value=[{
            "tag": {"tag_id": "item_1", "filter_width": 600}
        }])
        mgr._run_write = MagicMock()
        mgr.upsert_tag("sess1", "item_1", filter_width=600)
        cypher = mgr._run_query.call_args[0][0]
        # airflow_m3h was not passed, should NOT be in SET clause
        assert "t.airflow_m3h" not in cypher

    def test_upsert_tag_links_dimension_module(self, sgm):
        mgr, _ = sgm
        mgr._run_query = MagicMock(return_value=[{
            "tag": {"tag_id": "item_1", "housing_width": 600, "housing_height": 600}
        }])
        mgr._run_write = MagicMock()
        mgr.upsert_tag("sess1", "item_1", filter_width=600, filter_height=600)
        # Should call _run_write for DimensionModule linking
        assert mgr._run_write.called
        link_cypher = mgr._run_write.call_args[0][0]
        assert "SIZED_AS" in link_cypher
        assert "DimensionModule" in link_cypher

    def test_upsert_tag_with_assembly_syncs_siblings(self, sgm):
        mgr, _ = sgm
        mgr._run_query = MagicMock(return_value=[{
            "tag": {"tag_id": "item_1_stage_1", "assembly_group_id": "asm_1"}
        }])
        mgr._run_write = MagicMock()
        mgr.upsert_tag("sess1", "item_1_stage_1",
                        filter_width=600, filter_height=600,
                        assembly_group_id="asm_1")
        cypher = mgr._run_query.call_args[0][0]
        # Sibling sync should be present
        assert "sibling" in cypher.lower()
        assert "assembly_group_id" in cypher


# =============================================================================
# STATE RETRIEVAL
# =============================================================================

class TestStateRetrieval:
    def test_get_project_state_empty_session(self, sgm):
        mgr, _ = sgm
        mgr._run_query = MagicMock(return_value=[])
        state = mgr.get_project_state("nonexistent")
        assert state["session_id"] == "nonexistent"
        assert state["project"] is None
        assert state["tags"] == []
        assert state["tag_count"] == 0

    def test_get_project_state_with_data(self, sgm):
        mgr, _ = sgm
        mgr._run_query = MagicMock(return_value=[{
            "session_id": "sess1",
            "project": {
                "name": "TestProject",
                "locked_material": "RF",
                "detected_family": "GDB",
                "pending_clarification": None,
                "accessories": None,
                "assembly_group": None,
                "resolved_params": '{"connection_type": "PG"}',
                "vetoed_families": None,
                "customer": None,
            },
            "tags": [
                {"tag_id": "item_1", "filter_width": 600, "housing_width": 600,
                 "airflow_m3h": 3000, "is_complete": True},
            ],
            "tag_count": 1,
        }])
        state = mgr.get_project_state("sess1")
        assert state["session_id"] == "sess1"
        assert state["project"]["locked_material"] == "RF"
        assert len(state["tags"]) == 1
        assert state["tag_count"] == 1

    def test_get_tag_count_returns_int(self, sgm):
        mgr, _ = sgm
        mgr._run_query = MagicMock(return_value=[{"cnt": 3}])
        count = mgr.get_tag_count("sess1")
        assert count == 3

    def test_get_project_state_for_prompt_empty(self, sgm):
        mgr, _ = sgm
        mgr.get_project_state = MagicMock(return_value={
            "session_id": "s", "project": None, "tags": [], "tag_count": 0,
        })
        result = mgr.get_project_state_for_prompt("s")
        assert result == ""

    def test_get_project_state_for_prompt_with_data(self, sgm):
        mgr, _ = sgm
        mgr.get_project_state = MagicMock(return_value={
            "session_id": "s",
            "project": {
                "name": "Test", "locked_material": "RF",
                "detected_family": "GDB", "customer": None,
                "pending_clarification": None, "accessories": None,
                "assembly_group": None, "resolved_params": None,
                "vetoed_families": None,
            },
            "tags": [
                {"tag_id": "item_1", "filter_width": 600, "filter_height": 600,
                 "housing_width": 600, "housing_height": 600,
                 "airflow_m3h": 3000, "is_complete": True},
            ],
            "tag_count": 1,
        })
        result = mgr.get_project_state_for_prompt("s")
        assert "RF" in result
        assert "GDB" in result
        assert "600" in result
        assert "LOCKED" in result
        assert "PROHIBITIONS" in result


# =============================================================================
# MIGRATION-CRITICAL: FOREACH PATTERNS
# =============================================================================

class TestForeachPatterns:
    """FalkorDB doesn't support FOREACH — these tests document every usage
    so they can be systematically replaced during migration."""

    def test_lock_material_uses_foreach(self, sgm):
        mgr, session = sgm
        mgr.lock_material("sess1", "RF")
        cypher = session.run.call_args[0][0]
        assert "FOREACH" in cypher, \
            "lock_material must use FOREACH — migration target for FalkorDB"

    def test_set_detected_family_uses_foreach(self, sgm):
        mgr, session = sgm
        mgr.set_detected_family("sess1", "GDB")
        cypher = session.run.call_args[0][0]
        assert "FOREACH" in cypher, \
            "set_detected_family must use FOREACH — migration target for FalkorDB"

    def test_upsert_tag_dimension_link_uses_foreach(self, sgm):
        mgr, _ = sgm
        mgr._run_query = MagicMock(return_value=[{
            "tag": {"tag_id": "item_1", "housing_width": 600, "housing_height": 600}
        }])
        mgr._run_write = MagicMock()
        mgr.upsert_tag("sess1", "item_1", filter_width=600, filter_height=600)
        link_cypher = mgr._run_write.call_args[0][0]
        assert "FOREACH" in link_cypher, \
            "upsert_tag DimensionModule link uses FOREACH — migration target"
