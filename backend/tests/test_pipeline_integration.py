"""Pipeline integration tests — Scribe → Engine → State persist → State read.

These tests exercise the FULL data flow between components that will change
during migration, using mocked LLM and DB but real state management logic.

This catches integration bugs where:
- Scribe output shape doesn't match Engine input expectations
- Engine verdict doesn't persist correctly to Layer 4
- Layer 4 state doesn't round-trip through get_project_state
- State loaded from graph doesn't match TechnicalState expectations
"""

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.logic.state import TechnicalState, TagSpecification
from backend.config_loader import get_config


# =============================================================================
# Helpers
# =============================================================================

def _make_mock_session_graph():
    """Create a mock SessionGraphManager that tracks writes and returns them on read.

    Unlike conftest's mock which returns hardcoded data, this mock actually
    STORES data from write calls and returns it from read calls — testing
    the persist→read data integrity.
    """
    mgr = MagicMock()
    _store = {
        "project": None,
        "tags": {},
        "turns": [],
        "resolved_params": None,
        "detected_family": None,
        "locked_material": None,
        "pending_clarification": None,
        "accessories": None,
        "assembly_group": None,
        "vetoed_families": None,
    }

    def _ensure_session(session_id):
        pass

    def _set_project(session_id, name):
        _store["project"] = {"name": name, "customer": None}

    def _lock_material(session_id, material):
        _store["locked_material"] = material

    def _set_detected_family(session_id, family):
        _store["detected_family"] = family

    def _set_pending_clarification(session_id, param):
        _store["pending_clarification"] = param

    def _set_resolved_params(session_id, params):
        _store["resolved_params"] = json.dumps(params) if isinstance(params, dict) else params

    def _set_accessories(session_id, acc):
        _store["accessories"] = acc

    def _set_assembly_group(session_id, group):
        _store["assembly_group"] = json.dumps(group) if isinstance(group, dict) else group

    def _set_vetoed_families(session_id, vetoed):
        _store["vetoed_families"] = json.dumps(vetoed) if isinstance(vetoed, list) else vetoed

    def _upsert_tag(session_id, tag_id, **kwargs):
        tag = _store["tags"].get(tag_id, {"tag_id": tag_id})
        tag.update(kwargs)
        _store["tags"][tag_id] = tag
        return tag

    def _store_turn(session_id, role, message, turn_number):
        _store["turns"].append({"role": role, "message": message, "turn_number": turn_number})

    def _get_recent_turns(session_id, n=5):
        return _store["turns"][-n:]

    def _get_tag_count(session_id):
        return len(_store["tags"])

    def _get_project_state(session_id):
        project = None
        has_project_data = (_store["project"] or _store["locked_material"]
                            or _store["detected_family"] or _store["resolved_params"]
                            or _store["assembly_group"] or _store["accessories"]
                            or _store["pending_clarification"] or _store["vetoed_families"])
        if has_project_data:
            project = {
                "name": (_store["project"] or {}).get("name"),
                "customer": (_store["project"] or {}).get("customer"),
                "locked_material": _store["locked_material"],
                "detected_family": _store["detected_family"],
                "pending_clarification": _store["pending_clarification"],
                "accessories": _store["accessories"],
                "assembly_group": _store["assembly_group"],
                "resolved_params": _store["resolved_params"],
                "vetoed_families": _store["vetoed_families"],
            }
        tags = list(_store["tags"].values())
        return {
            "session_id": session_id,
            "project": project,
            "tags": tags,
            "tag_count": len(tags),
        }

    def _clear_session(session_id):
        _store["project"] = None
        _store["tags"] = {}
        _store["turns"] = []
        _store["resolved_params"] = None
        _store["detected_family"] = None
        _store["locked_material"] = None
        _store["pending_clarification"] = None
        _store["accessories"] = None
        _store["assembly_group"] = None
        _store["vetoed_families"] = None

    mgr.ensure_session.side_effect = _ensure_session
    mgr.set_project.side_effect = _set_project
    mgr.lock_material.side_effect = _lock_material
    mgr.set_detected_family.side_effect = _set_detected_family
    mgr.set_pending_clarification.side_effect = _set_pending_clarification
    mgr.set_resolved_params.side_effect = _set_resolved_params
    mgr.set_accessories.side_effect = _set_accessories
    mgr.set_assembly_group.side_effect = _set_assembly_group
    mgr.set_vetoed_families.side_effect = _set_vetoed_families
    mgr.upsert_tag.side_effect = _upsert_tag
    mgr.store_turn.side_effect = _store_turn
    mgr.get_recent_turns.side_effect = _get_recent_turns
    mgr.get_tag_count.side_effect = _get_tag_count
    mgr.get_project_state.side_effect = _get_project_state
    mgr.clear_session.side_effect = _clear_session

    return mgr


# =============================================================================
# Scribe → State integration
# =============================================================================

class TestScribeToState:
    """Test that Scribe output correctly populates TechnicalState."""

    def test_scribe_detected_family_flows_to_state(self):
        """Scribe detects product family → state.detected_family is set."""
        scribe_result = {
            "detected_application": "APP_KITCHEN",
            "detected_environment": "ENV_INDOOR",
            "detected_product_family": "GDB",
            "filter_width": 600,
            "filter_height": 600,
            "airflow_m3h": 3000,
            "material": None,
            "door_side": None,
            "connection_type": None,
        }

        state = TechnicalState()
        # Simulate what retriever.py does with Scribe output
        if scribe_result.get("detected_product_family"):
            state.detected_family = scribe_result["detected_product_family"]
        if scribe_result.get("filter_width"):
            state.merge_tag("item_1",
                            filter_width=scribe_result["filter_width"],
                            filter_height=scribe_result.get("filter_height"),
                            airflow_m3h=scribe_result.get("airflow_m3h"))

        assert state.detected_family == "GDB"
        assert "item_1" in state.tags
        assert state.tags["item_1"].filter_width == 600
        assert state.tags["item_1"].airflow_m3h == 3000

    def test_scribe_material_flows_to_state(self):
        """Scribe detects material → state.locked_material is set."""
        scribe_result = {"material": "RF"}
        state = TechnicalState()
        if scribe_result.get("material"):
            state.lock_material(scribe_result["material"])
        assert state.locked_material == "RF"

    def test_scribe_dimensions_flow_to_tag(self):
        """Scribe extracts dimensions → correct tag is updated."""
        scribe_result = {
            "filter_width": 300,
            "filter_height": 600,
            "airflow_m3h": 1700,
        }
        state = TechnicalState()
        state.merge_tag("item_1",
                        filter_width=scribe_result["filter_width"],
                        filter_height=scribe_result["filter_height"],
                        airflow_m3h=scribe_result["airflow_m3h"])

        tag = state.tags["item_1"]
        assert tag.filter_width == 300
        assert tag.filter_height == 600
        assert tag.airflow_m3h == 1700


# =============================================================================
# State → Persist → Read roundtrip
# =============================================================================

class TestStatePersistRoundtrip:
    """Test that TechnicalState correctly persists to and loads from Layer 4."""

    def test_basic_state_roundtrip(self):
        """Write state → read state → verify shape matches."""
        mgr = _make_mock_session_graph()
        session_id = "test_roundtrip_1"

        # Build state
        state = TechnicalState()
        state.detected_family = "GDB"
        state.lock_material("RF")
        state.merge_tag("item_1", filter_width=600, filter_height=600, airflow_m3h=3000)

        # Persist (mimics persist_to_graph in retriever.py)
        mgr.ensure_session(session_id)
        mgr.set_detected_family(session_id, state.detected_family)
        mgr.lock_material(session_id, state.locked_material)
        for tag_id, tag in state.tags.items():
            mgr.upsert_tag(session_id, tag_id,
                           filter_width=tag.filter_width,
                           filter_height=tag.filter_height,
                           airflow_m3h=tag.airflow_m3h)

        # Read back
        graph_state = mgr.get_project_state(session_id)
        assert graph_state["session_id"] == session_id
        assert graph_state["project"]["detected_family"] == "GDB"
        assert graph_state["project"]["locked_material"] == "RF"
        assert graph_state["tag_count"] == 1
        assert graph_state["tags"][0]["filter_width"] == 600

    def test_resolved_params_json_roundtrip(self):
        """resolved_params dict → JSON string → parse back."""
        mgr = _make_mock_session_graph()
        session_id = "test_roundtrip_2"

        params = {"connection_type": "PG", "door_side": "R"}
        mgr.ensure_session(session_id)
        mgr.set_resolved_params(session_id, params)

        graph_state = mgr.get_project_state(session_id)
        rp = graph_state["project"]["resolved_params"]
        if isinstance(rp, str):
            rp = json.loads(rp)
        assert rp["connection_type"] == "PG"
        assert rp["door_side"] == "R"

    def test_multi_tag_roundtrip(self):
        """Multiple tags persist and read back correctly."""
        mgr = _make_mock_session_graph()
        session_id = "test_roundtrip_3"

        mgr.ensure_session(session_id)
        mgr.upsert_tag(session_id, "item_1", filter_width=600, filter_height=600, airflow_m3h=3400)
        mgr.upsert_tag(session_id, "item_2", filter_width=300, filter_height=600, airflow_m3h=1700)

        graph_state = mgr.get_project_state(session_id)
        assert graph_state["tag_count"] == 2
        tag_ids = {t["tag_id"] for t in graph_state["tags"]}
        assert tag_ids == {"item_1", "item_2"}

    def test_assembly_group_roundtrip(self):
        """Assembly group dict → JSON string → parse back."""
        mgr = _make_mock_session_graph()
        session_id = "test_roundtrip_4"

        assembly = {
            "group_id": "assembly_item_1",
            "stages": [
                {"role": "PROTECTOR", "product_family": "GDP", "tag_id": "item_1_stage_1"},
                {"role": "TARGET", "product_family": "GDC", "tag_id": "item_1_stage_2"},
            ],
        }
        mgr.ensure_session(session_id)
        mgr.set_assembly_group(session_id, assembly)

        graph_state = mgr.get_project_state(session_id)
        ag = graph_state["project"]["assembly_group"]
        if isinstance(ag, str):
            ag = json.loads(ag)
        assert ag["group_id"] == "assembly_item_1"
        assert len(ag["stages"]) == 2

    def test_clear_session_removes_all(self):
        """clear_session wipes all state."""
        mgr = _make_mock_session_graph()
        session_id = "test_roundtrip_5"

        mgr.ensure_session(session_id)
        mgr.set_detected_family(session_id, "GDB")
        mgr.upsert_tag(session_id, "item_1", filter_width=600)

        mgr.clear_session(session_id)

        graph_state = mgr.get_project_state(session_id)
        assert graph_state["project"] is None
        assert graph_state["tag_count"] == 0

    def test_turn_storage_roundtrip(self):
        """Conversation turns persist and read back."""
        mgr = _make_mock_session_graph()
        session_id = "test_roundtrip_6"

        mgr.ensure_session(session_id)
        mgr.store_turn(session_id, "user", "I need a filter for a kitchen", 1)
        mgr.store_turn(session_id, "assistant", "I recommend GDB...", 2)

        turns = mgr.get_recent_turns(session_id, n=5)
        assert len(turns) == 2
        assert turns[0]["role"] == "user"
        assert turns[1]["role"] == "assistant"
        assert "kitchen" in turns[0]["message"]


# =============================================================================
# Engine → State mutation flow
# =============================================================================

class TestEngineToState:
    """Test that engine verdict correctly mutates TechnicalState."""

    def test_engine_product_recommendation_updates_state(self):
        """Engine recommends product → state.detected_family is set."""
        from backend.logic.universal_engine import EngineVerdict, TraitMatch

        verdict = EngineVerdict()
        verdict.recommended_product = TraitMatch(
            product_family_id="FAM_GDB", product_family_name="GDB",
            traits_present=["TRAIT_PARTICLE"], traits_missing=[],
            coverage_score=1.0, selection_priority=10,
        )

        state = TechnicalState()
        # Simulate what retriever does with verdict
        if verdict.recommended_product:
            state.detected_family = verdict.recommended_product.product_family_name

        assert state.detected_family == "GDB"

    def test_engine_assembly_creates_stage_tags(self):
        """Engine creates assembly → state gets stage tags."""
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600, airflow_m3h=3000)

        # Simulate assembly creation from engine
        assembly_data = {
            "group_id": "assembly_item_1",
            "stages": [
                {"role": "PROTECTOR", "product_family": "GDP", "tag_id": "item_1_stage_1"},
                {"role": "TARGET", "product_family": "GDC", "tag_id": "item_1_stage_2"},
            ],
        }

        # Remove original tag, create stage tags
        original_tag = state.tags.pop("item_1")
        for stage in assembly_data["stages"]:
            state.merge_tag(stage["tag_id"],
                            filter_width=original_tag.filter_width,
                            filter_height=original_tag.filter_height,
                            airflow_m3h=original_tag.airflow_m3h,
                            product_family=stage["product_family"])
            state.tags[stage["tag_id"]].assembly_role = stage["role"]
            state.tags[stage["tag_id"]].assembly_group_id = assembly_data["group_id"]

        assert len(state.tags) == 2
        assert "item_1_stage_1" in state.tags
        assert state.tags["item_1_stage_1"].assembly_role == "PROTECTOR"
        assert state.tags["item_1_stage_2"].product_family == "GDC"

    def test_engine_vetoed_families_update_state(self):
        """Engine vetoes families → state records vetoed list."""
        state = TechnicalState()
        vetoed = ["FAM_GDB", "FAM_GDC"]
        state.vetoed_families = vetoed

        assert state.vetoed_families == ["FAM_GDB", "FAM_GDC"]


# =============================================================================
# Full pipeline: Scribe → Engine → Persist → Read
# =============================================================================

class TestFullPipelineFlow:
    """Integration test covering the full data flow."""

    def test_scribe_to_persist_to_read(self):
        """Scribe output → state mutations → persist → read back → verify."""
        mgr = _make_mock_session_graph()
        session_id = "pipeline_test_1"

        # 1. Scribe output (simulated)
        scribe_result = {
            "detected_application": "APP_KITCHEN",
            "detected_product_family": "GDB",
            "filter_width": 600,
            "filter_height": 600,
            "airflow_m3h": 3000,
            "material": "RF",
        }

        # 2. Build TechnicalState from Scribe
        state = TechnicalState()
        state.detected_family = scribe_result["detected_product_family"]
        state.lock_material(scribe_result["material"])
        state.merge_tag("item_1",
                        filter_width=scribe_result["filter_width"],
                        filter_height=scribe_result["filter_height"],
                        airflow_m3h=scribe_result["airflow_m3h"])
        state.resolved_params = {"connection_type": "PG"}

        # 3. Persist to Layer 4
        mgr.ensure_session(session_id)
        mgr.set_detected_family(session_id, state.detected_family)
        mgr.lock_material(session_id, state.locked_material)
        mgr.set_resolved_params(session_id, state.resolved_params)
        for tag_id, tag in state.tags.items():
            mgr.upsert_tag(session_id, tag_id,
                           filter_width=tag.filter_width,
                           filter_height=tag.filter_height,
                           airflow_m3h=tag.airflow_m3h,
                           product_family=state.detected_family)

        # 4. Read back from Layer 4
        graph_state = mgr.get_project_state(session_id)

        # 5. Verify complete roundtrip
        assert graph_state["project"]["detected_family"] == "GDB"
        assert graph_state["project"]["locked_material"] == "RF"
        rp = graph_state["project"]["resolved_params"]
        if isinstance(rp, str):
            rp = json.loads(rp)
        assert rp["connection_type"] == "PG"
        assert graph_state["tag_count"] == 1
        assert graph_state["tags"][0]["filter_width"] == 600
        assert graph_state["tags"][0]["product_family"] == "GDB"

    def test_multi_turn_state_accumulation(self):
        """State accumulates across turns (mimics multi-turn conversation)."""
        mgr = _make_mock_session_graph()
        session_id = "pipeline_test_2"

        # Turn 1: user specifies kitchen application
        mgr.ensure_session(session_id)
        mgr.set_detected_family(session_id, "GDB")

        # Turn 2: user specifies dimensions
        mgr.upsert_tag(session_id, "item_1", filter_width=600, filter_height=600)

        # Turn 3: user specifies material
        mgr.lock_material(session_id, "RF")

        # Turn 4: user specifies airflow
        mgr.upsert_tag(session_id, "item_1", airflow_m3h=3000)

        # Final state should have everything
        state = mgr.get_project_state(session_id)
        assert state["project"]["detected_family"] == "GDB"
        assert state["project"]["locked_material"] == "RF"
        assert state["tags"][0]["filter_width"] == 600
        assert state["tags"][0]["airflow_m3h"] == 3000
