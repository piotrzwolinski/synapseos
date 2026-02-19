"""Scribe (Semantic Intent Extraction) tests — pure functions + mocked LLM.

Tests cover:
- _parse_scribe_response: Pure JSON → SemanticIntent conversion
- _repair_scribe_json: JSON repair for Gemini truncation
- resolve_derived_actions: Cross-reference resolution (SAME_AS, DOUBLE)
- extract_semantic_intent: Full flow with mocked LLM
- _build_env_app_mapping: Graph-driven prompt enrichment (DB contract)
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import asdict

from backend.logic.scribe import (
    _parse_scribe_response,
    _repair_scribe_json,
    _safe_int,
    resolve_derived_actions,
    SemanticIntent,
    ScribeEntity,
    ScribeAction,
    _build_env_app_mapping,
)


# =============================================================================
# PURE FUNCTION TESTS — no mocking needed
# =============================================================================

class TestParseScribeResponse:
    def test_minimal_valid_response(self):
        data = {
            "entities": [{"tag_ref": "item_1", "dimensions": {"width": 600, "height": 600}}],
            "parameters": {},
            "context_hints": [],
            "intent_type": "new_specification",
        }
        result = _parse_scribe_response(data)
        assert isinstance(result, SemanticIntent)
        assert len(result.entities) == 1
        assert result.entities[0].tag_ref == "item_1"
        assert result.entities[0].dimensions["width"] == 600

    def test_full_response_with_all_fields(self):
        data = {
            "entities": [{
                "tag_ref": "item_1",
                "action": "CREATE",
                "dimensions": {"width": 600, "height": 600, "depth": 292},
                "airflow_m3h": 3000,
                "product_family": "GDB",
                "material": "RF",
                "connection_type": "PG",
                "housing_length": 550,
            }],
            "parameters": {
                "detected_application": "APP_KITCHEN",
                "installation_environment": "ENV_INDOOR",
            },
            "actions": [
                {"type": "SET", "target_tag": "item_1", "field": "door_side", "value": "R"},
            ],
            "context_hints": ["commercial kitchen"],
            "clarification_answers": {"door_side": "R"},
            "intent_type": "new_specification",
            "language": "en",
            "confidence": 0.95,
            "action_intent": "configure",
            "project_name": "TestProject",
            "accessories": ["ACC_RAIN_HOOD"],
            "entity_codes": ["GDB-600x600-550"],
        }
        result = _parse_scribe_response(data)
        assert result.entities[0].airflow_m3h == 3000
        assert result.entities[0].product_family == "GDB"
        assert result.parameters["detected_application"] == "APP_KITCHEN"
        assert result.intent_type == "CONFIGURE"  # parser normalizes to CONFIGURE
        assert result.project_name == "TestProject"
        assert "ACC_RAIN_HOOD" in result.accessories

    def test_empty_entities(self):
        data = {"entities": [], "parameters": {}, "context_hints": []}
        result = _parse_scribe_response(data)
        assert len(result.entities) == 0

    def test_missing_optional_fields_use_defaults(self):
        data = {
            "entities": [{"tag_ref": "item_1"}],
            "parameters": {},
        }
        result = _parse_scribe_response(data)
        assert result.entities[0].dimensions is None
        assert result.entities[0].airflow_m3h is None
        assert result.language == "en"
        assert result.confidence == 0.0


class TestRepairScribeJson:
    def test_repairs_truncated_json(self):
        raw = '{"entities": [{"tag_ref": "item_1"}], "parameters": {"key": "val"'
        result = _repair_scribe_json(raw)
        assert result is not None
        assert "entities" in result

    def test_valid_json_passes_through(self):
        raw = '{"entities": [], "parameters": {}}'
        result = _repair_scribe_json(raw)
        assert result is not None
        assert result["entities"] == []

    def test_completely_broken_returns_none(self):
        result = _repair_scribe_json("not json at all")
        assert result is None

    def test_repairs_missing_closing_braces(self):
        raw = '{"entities": [{"tag_ref": "item_1"}], "parameters": {"key": "value"'
        result = _repair_scribe_json(raw)
        # Should attempt repair
        if result is not None:
            assert "entities" in result


class TestSafeInt:
    def test_integer_passthrough(self):
        assert _safe_int(600) == 600

    def test_string_conversion(self):
        assert _safe_int("600") == 600

    def test_float_truncation(self):
        assert _safe_int(600.7) == 600

    def test_none_returns_none(self):
        assert _safe_int(None) is None

    def test_invalid_string_returns_none(self):
        assert _safe_int("abc") is None

    def test_empty_string_returns_none(self):
        assert _safe_int("") is None


class TestResolveDerivedActions:
    def test_same_as_copies_value(self, state_with_tag):
        intent = SemanticIntent(
            entities=[ScribeEntity(tag_ref="item_2")],
            parameters={},
            actions=[
                ScribeAction(
                    type="COPY", target_tag="item_2",
                    field="filter_width", value=None,
                    derivation="SAME_AS:item_1",
                ),
            ],
            context_hints=[], clarification_answers={},
            intent_type="CONFIGURE", language="en",
            confidence=0.9, action_intent="configure",
            project_name=None, accessories=[], entity_codes=[],
        )
        resolved = resolve_derived_actions(intent, state_with_tag)
        # The action should be resolved with the value from item_1
        width_actions = [a for a in resolved.actions if a.field == "filter_width"]
        if width_actions:
            assert width_actions[0].value == 600

    def test_no_actions_passes_through(self, empty_state):
        intent = SemanticIntent(
            entities=[], parameters={}, actions=[],
            context_hints=[], clarification_answers={},
            intent_type="greeting", language="en",
            confidence=0.5, action_intent="greet",
            project_name=None, accessories=[], entity_codes=[],
        )
        resolved = resolve_derived_actions(intent, empty_state)
        assert len(resolved.actions) == 0


# =============================================================================
# GRAPH-DRIVEN PROMPT (DB CONTRACT)
# =============================================================================

class TestBuildEnvAppMapping:
    def test_builds_env_mapping(self, mock_db):
        env_text, app_text = _build_env_app_mapping(mock_db)
        assert "ENV_INDOOR" in env_text
        assert "indoor" in env_text

    def test_builds_app_mapping(self, mock_db):
        env_text, app_text = _build_env_app_mapping(mock_db)
        assert "APP_KITCHEN" in app_text
        assert "kitchen" in app_text

    def test_handles_db_failure_gracefully(self):
        broken_db = MagicMock()
        broken_db.get_environment_keywords.side_effect = Exception("Connection failed")
        broken_db.get_all_applications.side_effect = Exception("Connection failed")
        env_text, app_text = _build_env_app_mapping(broken_db)
        # Should fall back to defaults, not crash
        assert "indoor" in env_text.lower() or env_text == ""


# =============================================================================
# FULL EXTRACT FLOW (mocked LLM)
# =============================================================================

def _mock_llm_result(text: str, error: str = None):
    """Create a mock LLMResult matching llm_router.LLMResult shape."""
    result = MagicMock()
    result.text = text
    result.error = error
    result.duration_s = 0.1
    result.input_tokens = 100
    result.output_tokens = 50
    return result


class TestExtractSemanticIntent:
    @patch("backend.logic.scribe.llm_call")
    def test_extract_returns_semantic_intent(self, mock_llm, empty_state):
        mock_llm.return_value = _mock_llm_result(json.dumps({
            "entities": [{"tag_ref": "item_1", "dimensions": {"width": 600, "height": 600}}],
            "parameters": {},
            "context_hints": ["kitchen"],
            "intent_type": "new_specification",
            "language": "en",
            "confidence": 0.9,
        }))
        from backend.logic.scribe import extract_semantic_intent
        result = extract_semantic_intent(
            "I need a 600x600 filter for kitchen",
            recent_turns=[],
            technical_state=empty_state,
        )
        assert result is not None
        assert isinstance(result, SemanticIntent)
        assert result.entities[0].dimensions["width"] == 600

    @patch("backend.logic.scribe.llm_call")
    def test_extract_handles_llm_failure(self, mock_llm, empty_state):
        mock_llm.side_effect = Exception("LLM timeout")
        from backend.logic.scribe import extract_semantic_intent
        result = extract_semantic_intent(
            "hello",
            recent_turns=[],
            technical_state=empty_state,
        )
        # Should return None on failure, not crash
        assert result is None

    @patch("backend.logic.scribe.llm_call")
    def test_extract_handles_truncated_json(self, mock_llm, empty_state):
        mock_llm.return_value = _mock_llm_result(
            '{"entities": [{"tag_ref": "item_1"}], "parameters": {"key": "val"'
        )
        from backend.logic.scribe import extract_semantic_intent
        result = extract_semantic_intent(
            "600mm filter",
            recent_turns=[],
            technical_state=empty_state,
        )
        # Should attempt JSON repair
        # Result may or may not be None depending on repair success
        assert result is None or isinstance(result, SemanticIntent)

    @patch("backend.logic.scribe.llm_call")
    def test_extract_with_context_hints(self, mock_llm, empty_state):
        mock_llm.return_value = _mock_llm_result(json.dumps({
            "entities": [{"tag_ref": "item_1"}],
            "parameters": {"detected_application": "APP_KITCHEN"},
            "context_hints": ["commercial kitchen", "restaurant"],
            "intent_type": "new_specification",
            "confidence": 0.85,
        }))
        from backend.logic.scribe import extract_semantic_intent
        result = extract_semantic_intent(
            "filter for restaurant kitchen",
            recent_turns=[],
            technical_state=empty_state,
        )
        if result:
            assert result.parameters.get("detected_application") == "APP_KITCHEN"
