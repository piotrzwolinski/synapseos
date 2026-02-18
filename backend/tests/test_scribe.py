"""Pin Scribe parsing and action resolution (no LLM calls — mocked).

Tests _parse_scribe_response() and resolve_derived_actions() which are
pure-function transformers: JSON in → SemanticIntent out.
"""

import pytest
from backend.logic.scribe import (
    _parse_scribe_response,
    _repair_scribe_json,
    _safe_int,
    resolve_derived_actions,
    ScribeEntity,
    ScribeAction,
    SemanticIntent,
)
from backend.logic.state import TechnicalState


# =============================================================================
# _parse_scribe_response
# =============================================================================

class TestParseScribeResponse:
    def test_basic_entity_extraction(self):
        data = {
            "entities": [
                {"tag_ref": "item_1", "action": "CREATE",
                 "dimensions": {"width": 600, "height": 900, "depth": 292},
                 "airflow_m3h": 3400, "product_family": "GDB", "material": "RF"}
            ],
            "parameters": {},
            "actions": [],
            "intent_type": "CONFIGURE",
            "language": "en",
            "confidence": 0.9,
        }
        intent = _parse_scribe_response(data)
        assert len(intent.entities) == 1
        ent = intent.entities[0]
        assert ent.tag_ref == "item_1"
        assert ent.action == "CREATE"
        assert ent.dimensions == {"width": 600, "height": 900, "depth": 292}
        assert ent.airflow_m3h == 3400
        assert ent.product_family == "GDB"
        assert ent.material == "RF"

    def test_entity_without_tag_ref_skipped(self):
        data = {
            "entities": [
                {"action": "CREATE", "dimensions": {"width": 600}},  # No tag_ref
                {"tag_ref": "item_1", "action": "UPDATE"},
            ],
        }
        intent = _parse_scribe_response(data)
        assert len(intent.entities) == 1
        assert intent.entities[0].tag_ref == "item_1"

    def test_actions_parsed(self):
        data = {
            "actions": [
                {"type": "set", "target_tag": "item_2", "field": "airflow_m3h",
                 "derivation": "SAME_AS:item_1"},
            ],
        }
        intent = _parse_scribe_response(data)
        assert len(intent.actions) == 1
        assert intent.actions[0].type == "SET"  # uppercased
        assert intent.actions[0].target_tag == "item_2"
        assert intent.actions[0].derivation == "SAME_AS:item_1"

    def test_invalid_intent_type_defaults(self):
        data = {"intent_type": "INVALID_TYPE"}
        intent = _parse_scribe_response(data)
        assert intent.intent_type == "CONFIGURE"

    def test_question_intent_type(self):
        data = {"intent_type": "QUESTION"}
        intent = _parse_scribe_response(data)
        assert intent.intent_type == "QUESTION"

    def test_compatibility_check_intent(self):
        data = {"intent_type": "COMPATIBILITY_CHECK"}
        intent = _parse_scribe_response(data)
        assert intent.intent_type == "COMPATIBILITY_CHECK"

    def test_parameters_extracted(self):
        data = {
            "parameters": {
                "max_width_mm": 700,
                "installation_environment": "ENV_INDOOR",
                "chlorine_ppm": 60,
            },
        }
        intent = _parse_scribe_response(data)
        assert intent.parameters["max_width_mm"] == 700
        assert intent.parameters["installation_environment"] == "ENV_INDOOR"

    def test_clarification_answers(self):
        data = {
            "clarification_answers": {"airflow_m3h": 3000},
        }
        intent = _parse_scribe_response(data)
        assert intent.clarification_answers["airflow_m3h"] == 3000

    def test_v4_expanded_fields(self):
        data = {
            "action_intent": "compare",
            "project_name": "Nouryon",
            "accessories": ["EXL", "Round duct O500mm"],
            "entity_codes": ["GDB", "GDC-600x600"],
        }
        intent = _parse_scribe_response(data)
        assert intent.action_intent == "compare"
        assert intent.project_name == "Nouryon"
        assert len(intent.accessories) == 2
        assert "EXL" in intent.accessories
        assert "GDB" in intent.entity_codes

    def test_invalid_action_intent_defaults(self):
        data = {"action_intent": "INVALID"}
        intent = _parse_scribe_response(data)
        assert intent.action_intent == "select"

    def test_accessories_non_list_normalized(self):
        data = {"accessories": "EXL"}
        intent = _parse_scribe_response(data)
        assert intent.accessories == []

    def test_project_name_non_string_normalized(self):
        data = {"project_name": 123}
        intent = _parse_scribe_response(data)
        assert intent.project_name is None


# =============================================================================
# _repair_scribe_json
# =============================================================================

class TestRepairScribeJson:
    def test_repair_missing_closing_brace(self):
        raw = '{"entities": [], "intent_type": "CONFIGURE"'
        result = _repair_scribe_json(raw)
        assert result is not None
        assert result["intent_type"] == "CONFIGURE"

    def test_repair_missing_closing_bracket_and_brace(self):
        raw = '{"entities": [{"tag_ref": "item_1"}'
        result = _repair_scribe_json(raw)
        assert result is not None
        assert len(result["entities"]) == 1

    def test_repair_empty_returns_none(self):
        assert _repair_scribe_json("") is None
        assert _repair_scribe_json(None) is None

    def test_repair_valid_json_unchanged(self):
        raw = '{"entities": [], "confidence": 0.9}'
        result = _repair_scribe_json(raw)
        assert result["confidence"] == 0.9

    def test_repair_hopeless_returns_none(self):
        raw = 'not json at all {{'
        result = _repair_scribe_json(raw)
        assert result is None


# =============================================================================
# _safe_int
# =============================================================================

class TestSafeInt:
    def test_int_passthrough(self):
        assert _safe_int(42) == 42

    def test_float_to_int(self):
        assert _safe_int(3.7) == 3

    def test_string_to_int(self):
        assert _safe_int("600") == 600

    def test_none_returns_none(self):
        assert _safe_int(None) is None

    def test_invalid_returns_none(self):
        assert _safe_int("abc") is None


# =============================================================================
# resolve_derived_actions
# =============================================================================

class TestResolveDerivedActions:
    @pytest.fixture
    def state_with_tags(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                        airflow_m3h=3000)
        state.lock_material("RF")
        return state

    def test_same_as_copies_airflow(self, state_with_tags):
        intent = SemanticIntent(
            actions=[
                ScribeAction(
                    type="SET",
                    target_tag="item_2",
                    field="airflow_m3h",
                    derivation="SAME_AS:item_1",
                ),
            ],
        )
        resolved = resolve_derived_actions(intent, state_with_tags)
        assert len(resolved.actions) == 1
        assert resolved.actions[0].value == 3000
        assert resolved.actions[0].type == "SET"

    def test_same_as_copies_dimensions(self, state_with_tags):
        intent = SemanticIntent(
            actions=[
                ScribeAction(
                    type="SET",
                    target_tag="item_2",
                    field="dimensions",
                    derivation="SAME_AS:item_1",
                ),
            ],
        )
        resolved = resolve_derived_actions(intent, state_with_tags)
        assert resolved.actions[0].value["width"] == 600
        assert resolved.actions[0].value["height"] == 600

    def test_same_as_unknown_tag_dropped(self, state_with_tags):
        intent = SemanticIntent(
            actions=[
                ScribeAction(
                    type="SET",
                    target_tag="item_2",
                    field="airflow_m3h",
                    derivation="SAME_AS:item_99",
                ),
            ],
        )
        resolved = resolve_derived_actions(intent, state_with_tags)
        assert len(resolved.actions) == 0

    def test_double_airflow(self, state_with_tags):
        intent = SemanticIntent(
            actions=[
                ScribeAction(
                    type="SET",
                    target_tag="item_2",
                    field="airflow_m3h",
                    derivation="DOUBLE:item_1.airflow_m3h",
                ),
            ],
        )
        resolved = resolve_derived_actions(intent, state_with_tags)
        assert resolved.actions[0].value == 6000

    def test_half_airflow(self, state_with_tags):
        intent = SemanticIntent(
            actions=[
                ScribeAction(
                    type="SET",
                    target_tag="item_2",
                    field="airflow_m3h",
                    derivation="HALF:item_1.airflow_m3h",
                ),
            ],
        )
        resolved = resolve_derived_actions(intent, state_with_tags)
        assert resolved.actions[0].value == 1500

    def test_correct_passthrough(self):
        intent = SemanticIntent(
            actions=[
                ScribeAction(
                    type="CORRECT",
                    target_tag="item_1",
                    field="airflow_m3h",
                    value=5000,
                    derivation="",
                ),
            ],
        )
        state = TechnicalState()
        resolved = resolve_derived_actions(intent, state)
        assert resolved.actions[0].value == 5000
        assert resolved.actions[0].type == "CORRECT"

    def test_no_derivation_no_value_dropped(self):
        intent = SemanticIntent(
            actions=[
                ScribeAction(
                    type="SET",
                    target_tag="item_2",
                    field="airflow_m3h",
                    value=None,
                    derivation="",
                ),
            ],
        )
        state = TechnicalState()
        resolved = resolve_derived_actions(intent, state)
        assert len(resolved.actions) == 0
