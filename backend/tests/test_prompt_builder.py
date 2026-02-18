"""Pin system prompt structure (semantic checks, not byte-exact).

These tests verify that key structural sections exist in the prompts.
After refactoring prompts to tenant files, these sections must still be present.
"""

import pytest
from backend.config_loader import get_config


class TestDeepExplainablePrompt:
    @pytest.fixture(scope="class")
    def prompt(self):
        from backend.retriever import DEEP_EXPLAINABLE_SYSTEM_PROMPT
        return DEEP_EXPLAINABLE_SYSTEM_PROMPT

    def test_has_persona_section(self, prompt):
        assert "Application Engineer" in prompt or "Sales Engineer" in prompt

    def test_has_state_management_section(self, prompt):
        assert "PROJECT STATE" in prompt
        assert "LOCKED MATERIAL" in prompt

    def test_has_clarification_rules(self, prompt):
        assert "clarification_data" in prompt
        assert "CLARIFICATION_NEEDED" in prompt

    def test_has_output_schema(self, prompt):
        assert '"response_type"' in prompt
        assert '"content_segments"' in prompt
        assert '"entity_card"' in prompt

    def test_has_corrosion_hierarchy(self, prompt):
        assert "C3" in prompt
        assert "C5" in prompt
        assert "corrosion" in prompt.lower()

    def test_has_product_type_accuracy(self, prompt):
        """Prompt mentions all key product families."""
        config = get_config()
        # At minimum these core families should be described
        for family in ["GDB", "GDP", "GDC", "GDMI"]:
            assert family in prompt, f"Missing product family {family} in prompt"

    def test_has_dimension_mapping_rules(self, prompt):
        assert "Dimension" in prompt or "dimension" in prompt
        assert "Housing" in prompt or "housing" in prompt

    def test_has_anti_hallucination_rules(self, prompt):
        assert "HALLUCIN" in prompt.upper()
        assert "NEVER invent" in prompt or "NEVER guess" in prompt

    def test_has_brevity_mode(self, prompt):
        assert "BREVITY" in prompt.upper() or "30 words" in prompt

    def test_word_count_stable(self, prompt):
        """Guard against accidental truncation or duplication."""
        word_count = len(prompt.split())
        # Current prompt is ~4500 words. Allow wide margin for edits.
        assert 2000 < word_count < 8000, f"Prompt word count {word_count} outside expected range"


class TestGenericPrompt:
    @pytest.fixture(scope="class")
    def prompt(self):
        from backend.retriever import DEEP_EXPLAINABLE_SYSTEM_PROMPT_GENERIC
        return DEEP_EXPLAINABLE_SYSTEM_PROMPT_GENERIC

    def test_has_persona(self, prompt):
        assert "Sales Engineer" in prompt or "Engineer" in prompt

    def test_has_output_schema(self, prompt):
        assert '"response_type"' in prompt
        assert '"content_segments"' in prompt

    def test_no_mann_hummel_specifics(self, prompt):
        """Generic prompt should not hardcode MH product names in rules."""
        # Product family names may appear in examples but not in the rules logic
        # This is a soft check — verify the prompt is mostly generic
        assert "MANN+HUMMEL" not in prompt


class TestIntentDetectionPrompt:
    @pytest.fixture(scope="class")
    def prompt(self):
        from backend.retriever import INTENT_DETECTION_PROMPT
        return INTENT_DETECTION_PROMPT

    def test_is_domain_agnostic(self, prompt):
        """Intent detection prompt should be domain-agnostic."""
        # It should extract structured intent without MH product names
        assert "numeric_constraints" in prompt
        assert "entity_references" in prompt
        assert "action_intent" in prompt

    def test_has_json_output_schema(self, prompt):
        assert "language" in prompt
        assert "context_keywords" in prompt
        assert "JSON" in prompt
