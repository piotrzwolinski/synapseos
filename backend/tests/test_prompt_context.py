"""Pin to_prompt_context() and _build_entity_cards() output format.

These generate the LLM-facing state injection. Format changes = LLM behavior regression.
"""

import pytest
from backend.logic.state import TechnicalState, MaterialCode


class TestPromptContextMaterial:
    def test_rf_shows_corrosion_class(self, state_with_material):
        ctx = state_with_material.to_prompt_context()
        assert "RF" in ctx
        assert "C5" in ctx
        assert "corrosion class" in ctx.lower()

    def test_fz_shows_c3(self):
        state = TechnicalState()
        state.lock_material("FZ")
        ctx = state.to_prompt_context()
        assert "FZ" in ctx
        assert "C3" in ctx

    def test_prohibits_material_revert(self, state_with_material):
        ctx = state_with_material.to_prompt_context()
        assert "Do NOT use FZ" in ctx or "Do NOT revert" in ctx


class TestPromptContextResolvedParams:
    def test_includes_resolved_params(self):
        state = TechnicalState()
        state.resolved_params = {"chlorine_ppm": "0.5", "door_side": "L"}
        state.lock_material("RF")
        ctx = state.to_prompt_context()
        assert "chlorine_ppm" in ctx
        assert "DO NOT ask for chlorine_ppm" in ctx
        assert "door_side" in ctx

    def test_detected_family_appears_in_context(self):
        """detected_family is shown in prompt context (no hardcoded rules about it)."""
        state = TechnicalState()
        state.detected_family = "GDMI"
        ctx = state.to_prompt_context()
        assert "GDMI" in ctx


class TestPromptContextTags:
    def test_complete_tag_shows_ready(self, state_fully_populated):
        ctx = state_fully_populated.to_prompt_context()
        assert "COMPLETE" in ctx

    def test_incomplete_tag_shows_missing(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        ctx = state.to_prompt_context()
        assert "Missing" in ctx or "airflow" in ctx.lower()

    def test_tag_dimensions_shown(self, state_fully_populated):
        ctx = state_fully_populated.to_prompt_context()
        assert "300x600" in ctx
        assert "DO NOT ask" in ctx


class TestPromptContextStructure:
    def test_has_prohibition_section(self, state_with_material):
        ctx = state_with_material.to_prompt_context()
        assert "PROHIBITIONS" in ctx
        assert "NEVER" in ctx

    def test_has_derivation_rules(self, state_with_material):
        ctx = state_with_material.to_prompt_context()
        assert "AUTO-DERIVATION" in ctx
        assert "292" in ctx
        assert "550" in ctx

    def test_has_cumulative_header(self, state_with_material):
        ctx = state_with_material.to_prompt_context()
        assert "CUMULATIVE PROJECT STATE" in ctx
        assert "ABSOLUTE TRUTH" in ctx


class TestBuildEntityCards:
    def test_entity_card_has_corrosion(self, state_fully_populated):
        cards = state_fully_populated._build_entity_cards()
        # Single tag → dict, not list
        assert isinstance(cards, dict)
        assert "specs" in cards
        assert "C5" in cards["specs"]["Material"]

    def test_entity_card_has_product_code(self, state_fully_populated):
        cards = state_fully_populated._build_entity_cards()
        assert "GDB-300x600-550-R-PG-RF" in cards["specs"]["Product Code"]

    def test_entity_card_multi_tag_returns_list(self, state_with_assembly):
        # Complete both tags so cards are generated
        for tag in state_with_assembly.tags.values():
            tag.is_complete = True
            tag.product_code = f"GDP-600x600-550-R-PG-FZ"
        cards = state_with_assembly._build_entity_cards()
        assert isinstance(cards, list)
        assert len(cards) == 2

    def test_entity_card_assembly_label(self, state_with_assembly):
        for tag in state_with_assembly.tags.values():
            tag.is_complete = True
            tag.product_code = "GDP-600x600-550-R-PG-FZ"
        cards = state_with_assembly._build_entity_cards()
        titles = [c["title"] for c in cards]
        assert any("PROTECTOR" in t for t in titles)
        assert any("TARGET" in t for t in titles)
