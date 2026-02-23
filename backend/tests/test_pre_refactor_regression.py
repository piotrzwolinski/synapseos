"""Pre-refactor regression tests — pin current behavior before universalization.

Every test in this file captures EXACT current behavior of components that will
be modified during the 5-phase MH structural extraction. If any test breaks
during refactoring, the refactor introduced a behavioral regression.

Sections:
1. TagSpecification compute methods (housing mapping, orientation, completeness)
2. to_prompt_context() snapshot (exact output pinning)
3. resolved_context mapping (retriever.py key production)
4. _merge_scribe_into_state routing (Scribe → TechnicalState field map)
5. Session graph field map (persist/load round-trip)
"""

import json
import pytest
from dataclasses import dataclass
from typing import Optional, Any
from unittest.mock import MagicMock, patch

from backend.logic.state import TechnicalState, TagSpecification, MaterialCode


# =============================================================================
# SECTION 1: TagSpecification Compute Methods
# =============================================================================

class TestComputeHousingFromFilter:
    """Pin filter→housing dimension mapping via compute_housing_from_filter()."""

    def test_305_maps_to_300(self):
        tag = TagSpecification(tag_id="t1", filter_width=305, filter_height=610)
        tag.compute_housing_from_filter()
        assert tag.housing_width == 300
        assert tag.housing_height == 600

    def test_610_maps_to_600(self):
        tag = TagSpecification(tag_id="t1", filter_width=610, filter_height=610)
        tag.compute_housing_from_filter()
        assert tag.housing_width == 600
        assert tag.housing_height == 600

    def test_no_mapping_keeps_value(self):
        """Dimensions without a map entry pass through unchanged."""
        tag = TagSpecification(tag_id="t1", filter_width=900, filter_height=900)
        tag.compute_housing_from_filter()
        assert tag.housing_width == 900
        assert tag.housing_height == 900

    def test_none_width_skipped(self):
        """None dimensions → no crash, no housing set."""
        tag = TagSpecification(tag_id="t1")
        tag.compute_housing_from_filter()
        assert tag.housing_width is None
        assert tag.housing_height is None

    def test_partial_dims_only_maps_present(self):
        """Only width set → only housing_width mapped."""
        tag = TagSpecification(tag_id="t1", filter_width=305)
        tag.compute_housing_from_filter()
        assert tag.housing_width == 300
        assert tag.housing_height is None

    def test_calls_normalize_after_mapping(self):
        """compute_housing_from_filter calls normalize_orientation at the end."""
        tag = TagSpecification(tag_id="t1", filter_width=610, filter_height=305)
        tag.compute_housing_from_filter()
        # 600x300 with threshold 600 → swapped to 300x600
        assert tag.housing_width == 300
        assert tag.housing_height == 600


class TestNormalizeOrientation:
    """Pin orientation normalization (width ≤ height for small modules)."""

    def test_swaps_when_width_gt_height_small(self):
        tag = TagSpecification(tag_id="t1", housing_width=600, housing_height=300)
        tag.normalize_orientation()
        assert tag.housing_width == 300
        assert tag.housing_height == 600

    def test_no_swap_when_height_gte_width(self):
        tag = TagSpecification(tag_id="t1", housing_width=300, housing_height=600)
        tag.normalize_orientation()
        assert tag.housing_width == 300
        assert tag.housing_height == 600

    def test_equal_dims_no_swap(self):
        tag = TagSpecification(tag_id="t1", housing_width=600, housing_height=600)
        tag.normalize_orientation()
        assert tag.housing_width == 600
        assert tag.housing_height == 600

    def test_no_swap_for_large_dimensions(self):
        """Dimensions above threshold are NOT swapped."""
        tag = TagSpecification(tag_id="t1", housing_width=900, housing_height=600)
        tag.normalize_orientation()
        # 900 > threshold → no swap
        assert tag.housing_width == 900
        assert tag.housing_height == 600

    def test_also_swaps_filter_dimensions(self):
        tag = TagSpecification(
            tag_id="t1",
            filter_width=610, filter_height=305,
            housing_width=600, housing_height=300,
        )
        tag.normalize_orientation()
        assert tag.filter_width == 305
        assert tag.filter_height == 610
        assert tag.housing_width == 300
        assert tag.housing_height == 600

    def test_noop_when_missing_dims(self):
        tag = TagSpecification(tag_id="t1")
        tag.normalize_orientation()  # should not crash
        assert tag.housing_width is None
        assert tag.housing_height is None

    def test_noop_when_only_width(self):
        tag = TagSpecification(tag_id="t1", housing_width=600)
        tag.normalize_orientation()
        assert tag.housing_width == 600


class TestCheckCompletenessExhaustive:
    """Pin check_completeness() behavior for all missing-parameter cases."""

    def test_all_present_complete(self):
        tag = TagSpecification(
            tag_id="t1",
            housing_width=600, housing_height=600, housing_length=550,
            airflow_m3h=3000,
        )
        is_ok, missing = tag.check_completeness()
        assert is_ok is True
        assert missing == []

    def test_housing_direct_no_filter_complete(self):
        """Housing dims set directly (no filter) → NOT missing filter_dimensions."""
        tag = TagSpecification(
            tag_id="t1",
            housing_width=600, housing_height=600,
            housing_length=550, airflow_m3h=3000,
        )
        is_ok, missing = tag.check_completeness()
        assert is_ok is True
        assert "filter_dimensions" not in missing

    def test_only_airflow_missing(self):
        tag = TagSpecification(
            tag_id="t1",
            housing_width=600, housing_height=600, housing_length=550,
        )
        is_ok, missing = tag.check_completeness()
        assert is_ok is False
        assert missing == ["airflow"]

    def test_only_depth_and_length_missing(self):
        """No depth, no length → missing filter_depth."""
        tag = TagSpecification(
            tag_id="t1",
            housing_width=600, housing_height=600,
            airflow_m3h=3000,
        )
        is_ok, missing = tag.check_completeness()
        assert is_ok is False
        assert "filter_depth" in missing

    def test_depth_present_but_length_not_yet_derived(self):
        """filter_depth set but housing_length not yet computed.

        check_completeness checks housing_length OR filter_depth — if filter_depth
        is present, that arm passes even without housing_length.
        """
        tag = TagSpecification(
            tag_id="t1",
            housing_width=600, housing_height=600,
            filter_depth=292,
            airflow_m3h=3000,
        )
        is_ok, missing = tag.check_completeness()
        # filter_depth is present → the "housing_length OR filter_depth" check passes
        assert is_ok is True
        assert "filter_depth" not in missing

    def test_length_present_depth_absent_is_complete(self):
        """housing_length set directly → no need for filter_depth."""
        tag = TagSpecification(
            tag_id="t1",
            housing_width=600, housing_height=600,
            housing_length=550, airflow_m3h=3000,
        )
        is_ok, missing = tag.check_completeness()
        assert is_ok is True

    def test_only_dims_missing(self):
        tag = TagSpecification(
            tag_id="t1",
            housing_length=550,
            airflow_m3h=3000,
        )
        is_ok, missing = tag.check_completeness()
        assert is_ok is False
        assert "filter_dimensions" in missing

    def test_nothing_set(self):
        tag = TagSpecification(tag_id="t1")
        is_ok, missing = tag.check_completeness()
        assert is_ok is False
        assert "filter_dimensions" in missing
        assert "filter_depth" in missing
        assert "airflow" in missing

    def test_sets_is_complete_flag(self):
        tag = TagSpecification(
            tag_id="t1",
            housing_width=600, housing_height=600,
            housing_length=550, airflow_m3h=3000,
        )
        tag.check_completeness()
        assert tag.is_complete is True
        assert tag.missing_params == []

    def test_sets_missing_params_list(self):
        tag = TagSpecification(tag_id="t1")
        tag.check_completeness()
        assert tag.is_complete is False
        assert len(tag.missing_params) == 3


# =============================================================================
# SECTION 2: to_prompt_context() Snapshot
# =============================================================================

class TestPromptContextSnapshot:
    """Pin exact structure and content of to_prompt_context() output."""

    @pytest.fixture
    def full_state(self):
        state = TechnicalState()
        state.project_name = "TestProject"
        state.lock_material("RF")
        state.detected_family = "GDB"
        state.resolved_params = {"connection_type": "PG", "door_side": "R"}
        state.merge_tag("item_1", filter_width=610, filter_height=305,
                         filter_depth=292, airflow_m3h=3000, product_family="GDB")
        state.tags["item_1"].product_code = "GDB-300x600-550-R-PG-RF"
        state.tags["item_1"].weight_kg = 45.0
        return state

    def test_header_present(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "CUMULATIVE PROJECT STATE" in ctx
        assert "ABSOLUTE TRUTH" in ctx
        assert "LOCKED" in ctx

    def test_locked_params_section(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "LOCKED PARAMETERS" in ctx
        assert "TestProject" in ctx
        assert "RF" in ctx
        assert "GDB" in ctx

    def test_resolved_params_shown(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "connection_type" in ctx
        assert "PG" in ctx
        assert "door_side" in ctx
        assert "DO NOT ask for connection_type" in ctx

    def test_tag_dimensions_shown(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "300x600" in ctx
        assert "Housing Size" in ctx
        assert "DO NOT ask for duct dimensions" in ctx

    def test_tag_depth_shown(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "292" in ctx
        assert "Depth KNOWN" in ctx

    def test_tag_housing_length_shown(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "550" in ctx
        assert "Length RESOLVED" in ctx

    def test_tag_airflow_shown(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "3000" in ctx
        assert "Airflow KNOWN" in ctx

    def test_tag_product_code_shown(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "GDB-300x600-550-R-PG-RF" in ctx
        assert "USE THIS EXACT CODE" in ctx

    def test_tag_weight_shown(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "45" in ctx
        assert "kg" in ctx

    def test_tag_complete_status(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "COMPLETE" in ctx

    def test_prohibition_rules_all_six(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "STRICT PROHIBITIONS" in ctx
        # All 6 prohibition lines
        assert "NEVER ask for data shown above" in ctx
        assert "NEVER revert material to FZ" in ctx
        assert "NEVER ask for housing length" in ctx
        assert "NEVER ask for filter depth" in ctx
        assert "ALWAYS use locked material suffix" in ctx
        assert "ALWAYS acknowledge previous input" in ctx

    def test_derivation_table_rows(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "AUTO-DERIVATION RULES" in ctx
        assert "Filter Depth ≤292mm" in ctx
        assert "Housing Length = 550mm" in ctx
        assert "Filter Depth ≤450mm" in ctx
        assert "Housing Length = 750mm" in ctx
        assert "Filter Depth >450mm" in ctx
        assert "Housing Length = 900mm" in ctx
        assert "Filter 305mm" in ctx
        assert "Housing 300mm" in ctx
        assert "Filter 610mm" in ctx
        assert "Housing 600mm" in ctx

    def test_corrosion_reference_present(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "Corrosion Class Reference" in ctx
        # Dynamic from config — verify structure
        assert "RF=" in ctx
        assert "FZ=" in ctx

    def test_entity_card_present_when_complete(self, full_state):
        ctx = full_state.to_prompt_context()
        assert "ALL DATA COMPLETE" in ctx
        assert "PRE-COMPUTED ENTITY CARD" in ctx
        assert "entity_card" in ctx

    def test_known_marker_count(self, full_state):
        """Pin the number of ✓ KNOWN/RESOLVED markers for a fully populated state."""
        ctx = full_state.to_prompt_context()
        known_count = ctx.count("✓")
        # At minimum: dimensions, depth, length, airflow, product code,
        # + 2 resolved params (connection_type, door_side)
        assert known_count >= 6

    def test_assembly_context_format(self):
        state = TechnicalState()
        state.lock_material("FZ")
        state.detected_family = "GDC"
        state.assembly_group = {
            "group_id": "assembly_item_1",
            "rationale": "Kitchen environment requires grease pre-filter",
            "stages": [
                {"role": "PROTECTOR", "product_family": "GDP", "tag_id": "item_1_stage_1",
                 "provides_trait": "Grease Pre-Filtration"},
                {"role": "TARGET", "product_family": "GDC", "tag_id": "item_1_stage_2",
                 "provides_trait": "Carbon Adsorption"},
            ],
        }
        state.merge_tag("item_1_stage_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000, product_family="GDP")
        state.tags["item_1_stage_1"].assembly_role = "PROTECTOR"
        state.tags["item_1_stage_1"].assembly_group_id = "assembly_item_1"
        state.merge_tag("item_1_stage_2", filter_width=600, filter_height=600,
                         airflow_m3h=3000, product_family="GDC")
        state.tags["item_1_stage_2"].assembly_role = "TARGET"
        state.tags["item_1_stage_2"].assembly_group_id = "assembly_item_1"

        ctx = state.to_prompt_context()
        assert "MULTI-STAGE ASSEMBLY" in ctx
        assert "ALL STAGES REQUIRED" in ctx
        assert "PROTECTOR" in ctx
        assert "TARGET" in ctx
        assert "GDP" in ctx
        assert "GDC" in ctx
        assert "Grease Pre-Filtration" in ctx
        assert "ALL stages MUST be included" in ctx

    def test_multi_module_airflow_format(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         filter_depth=292, airflow_m3h=3000)
        state.tags["item_1"].modules_needed = 2
        state.tags["item_1"].total_airflow_m3h = 6000
        ctx = state.to_prompt_context()
        assert "6000" in ctx
        assert "2×3000" in ctx or "2x3000" in ctx.replace("×", "x")

    def test_vetoed_families_shown(self):
        state = TechnicalState()
        state.lock_material("FZ")
        state.vetoed_families = ["FAM_GDC_FLEX", "FAM_GDMI"]
        ctx = state.to_prompt_context()
        assert "VETOED" in ctx
        assert "GDC_FLEX" in ctx or "GDC-FLEX" in ctx
        assert "GDMI" in ctx
        assert "Do NOT recommend" in ctx or "DO NOT recommend" in ctx

    def test_incomplete_tag_shows_missing(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        ctx = state.to_prompt_context()
        assert "Missing" in ctx or "MISSING" in ctx or "airflow" in ctx.lower()


# =============================================================================
# SECTION 3: resolved_context Mapping
# =============================================================================

class TestResolvedContextMapping:
    """Pin the key mapping from TechnicalState → resolved_context dict.

    This tests the resolved_context building logic from retriever.py lines 3738-3829.
    We replicate the exact logic here to test it in isolation without importing
    the full retriever (which has heavy dependencies).
    """

    @staticmethod
    def _build_resolved_context(technical_state, user_max_width_mm=None,
                                 user_max_height_mm=None,
                                 db=None):
        """Replicate the resolved_context building from retriever.py:3738-3829.

        This is a faithful copy used ONLY for regression testing. Any divergence
        from the source is a test bug.
        """
        resolved_context = {}

        for tag_id, tag in technical_state.tags.items():
            if tag.filter_depth:
                resolved_context['filter_depth'] = tag.filter_depth
                resolved_context['depth'] = tag.filter_depth
            if tag.housing_length:
                resolved_context['housing_length'] = tag.housing_length
                resolved_context['length'] = tag.housing_length
            if tag.airflow_m3h:
                resolved_context['airflow'] = tag.airflow_m3h
                resolved_context['airflow_m3h'] = tag.airflow_m3h
            if tag.housing_width and tag.housing_height:
                resolved_context['housing_size'] = f"{tag.housing_width}x{tag.housing_height}"
                resolved_context['housing_width'] = int(tag.housing_width)
                resolved_context['housing_height'] = int(tag.housing_height)
                resolved_context['width'] = int(tag.housing_width)
                resolved_context['height'] = int(tag.housing_height)
            if tag.filter_width and tag.filter_height:
                resolved_context['filter_width'] = int(tag.filter_width)
                resolved_context['filter_height'] = int(tag.filter_height)
                resolved_context['dimensions'] = f"{tag.filter_width}x{tag.filter_height}"

        # Airflow fallback from resolved_params
        if 'airflow' not in resolved_context and technical_state.resolved_params.get("airflow_m3h"):
            stored_airflow = technical_state.resolved_params["airflow_m3h"]
            resolved_context['airflow'] = stored_airflow
            resolved_context['airflow_m3h'] = stored_airflow

        # Filter depth fallback from resolved_params
        if 'filter_depth' not in resolved_context and technical_state.resolved_params.get("filter_depth"):
            stored_depth = technical_state.resolved_params["filter_depth"]
            try:
                depth_int = int(stored_depth)
                resolved_context['filter_depth'] = depth_int
                resolved_context['depth'] = depth_int
            except (ValueError, TypeError):
                pass

        if technical_state.locked_material:
            resolved_context['material'] = technical_state.locked_material

        # _mm suffix aliases
        for _key in ['housing_length', 'housing_width', 'housing_height']:
            _val = resolved_context.get(_key)
            if _val is not None:
                resolved_context[f'{_key}_mm'] = _val

        if user_max_width_mm:
            resolved_context['max_width_mm'] = int(user_max_width_mm)
        if user_max_height_mm:
            resolved_context['max_height_mm'] = int(user_max_height_mm)

        # Merge generic resolved params
        if technical_state.resolved_params:
            for rp_key, rp_value in technical_state.resolved_params.items():
                if rp_key not in resolved_context:
                    resolved_context[rp_key] = rp_value

        return resolved_context

    def test_filter_depth_produces_two_keys(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         filter_depth=292, airflow_m3h=3000)
        ctx = self._build_resolved_context(state)
        assert ctx['filter_depth'] == 292
        assert ctx['depth'] == 292

    def test_housing_length_produces_two_keys(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         filter_depth=292, airflow_m3h=3000)
        ctx = self._build_resolved_context(state)
        assert ctx['housing_length'] == 550
        assert ctx['length'] == 550

    def test_airflow_produces_two_keys(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)
        ctx = self._build_resolved_context(state)
        assert ctx['airflow'] == 3000
        assert ctx['airflow_m3h'] == 3000

    def test_housing_size_produces_five_keys(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)
        ctx = self._build_resolved_context(state)
        assert ctx['housing_size'] == "600x600"
        assert ctx['housing_width'] == 600
        assert ctx['housing_height'] == 600
        assert ctx['width'] == 600
        assert ctx['height'] == 600

    def test_filter_dims_produce_three_keys(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)
        ctx = self._build_resolved_context(state)
        assert ctx['filter_width'] == 600
        assert ctx['filter_height'] == 600
        assert ctx['dimensions'] == "600x600"

    def test_material_from_lock(self):
        state = TechnicalState()
        state.lock_material("RF")
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)
        ctx = self._build_resolved_context(state)
        assert ctx['material'] == "RF"

    def test_mm_suffix_aliases(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         filter_depth=292, airflow_m3h=3000)
        ctx = self._build_resolved_context(state)
        assert ctx['housing_length_mm'] == 550
        assert ctx['housing_width_mm'] == 600
        assert ctx['housing_height_mm'] == 600

    def test_resolved_params_merge(self):
        state = TechnicalState()
        state.resolved_params = {"connection_type": "PG", "door_side": "R"}
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)
        ctx = self._build_resolved_context(state)
        assert ctx['connection_type'] == "PG"
        assert ctx['door_side'] == "R"

    def test_resolved_params_do_not_override_tag_data(self):
        """Tag data takes precedence over resolved_params for same key."""
        state = TechnicalState()
        state.resolved_params = {"airflow_m3h": "999"}
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)
        ctx = self._build_resolved_context(state)
        assert ctx['airflow_m3h'] == 3000  # From tag, not resolved_params

    def test_airflow_fallback_from_resolved_params(self):
        """When no tag has airflow, fall back to resolved_params."""
        state = TechnicalState()
        state.resolved_params = {"airflow_m3h": "3000"}
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        ctx = self._build_resolved_context(state)
        assert ctx['airflow'] == "3000"
        assert ctx['airflow_m3h'] == "3000"

    def test_depth_fallback_from_resolved_params(self):
        """When no tag has filter_depth, fall back to resolved_params."""
        state = TechnicalState()
        state.resolved_params = {"filter_depth": "292"}
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)
        ctx = self._build_resolved_context(state)
        assert ctx['filter_depth'] == 292
        assert ctx['depth'] == 292

    def test_max_width_height_constraints(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)
        ctx = self._build_resolved_context(state, user_max_width_mm=700,
                                            user_max_height_mm=1000)
        assert ctx['max_width_mm'] == 700
        assert ctx['max_height_mm'] == 1000

    def test_no_material_when_unlocked(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)
        ctx = self._build_resolved_context(state)
        assert 'material' not in ctx

    def test_multi_tag_last_wins(self):
        """With multiple tags, last tag's values win (loop overwrites)."""
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)
        state.merge_tag("item_2", filter_width=300, filter_height=600,
                         airflow_m3h=1500)
        ctx = self._build_resolved_context(state)
        # item_2 processed last → its values win
        assert ctx['airflow'] == 1500
        assert ctx['housing_width'] == 300


# =============================================================================
# SECTION 4: _merge_scribe_into_state Routing
# =============================================================================

class TestMergeScribeRouting:
    """Pin field routing from SemanticIntent → TechnicalState.

    We import and call _merge_scribe_into_state directly with mock intents.
    """

    @pytest.fixture(autouse=True)
    def _import_merge(self):
        """Import _merge_scribe_into_state from retriever.

        This import is heavy — isolate it so failures are clear.
        """
        try:
            from backend.retriever import _merge_scribe_into_state
            self._merge = _merge_scribe_into_state
        except ImportError:
            pytest.skip("Cannot import _merge_scribe_into_state from retriever")

    @pytest.fixture
    def _import_scribe_types(self):
        from backend.logic.scribe import SemanticIntent, ScribeEntity, ScribeAction
        return SemanticIntent, ScribeEntity, ScribeAction

    def _make_intent(self, _import_scribe_types, **kwargs):
        SemanticIntent, _, _ = _import_scribe_types
        return SemanticIntent(**kwargs)

    def _make_entity(self, _import_scribe_types, **kwargs):
        _, ScribeEntity, _ = _import_scribe_types
        return ScribeEntity(**kwargs)

    def _make_action(self, _import_scribe_types, **kwargs):
        _, _, ScribeAction = _import_scribe_types
        return ScribeAction(**kwargs)

    def test_entity_dimensions_route_to_tag(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1")  # Create empty tag
        entity = self._make_entity(_import_scribe_types,
            tag_ref="item_1",
            dimensions={"width": 600, "height": 900, "depth": 292})
        intent = self._make_intent(_import_scribe_types,
            entities=[entity])
        self._merge(intent, state, "GDB")
        tag = state.tags["item_1"]
        assert tag.filter_depth == 292
        # Housing dims derived from filter via mapping + orientation
        assert tag.housing_width is not None
        assert tag.housing_height is not None

    def test_entity_airflow_routes_to_tag(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        entity = self._make_entity(_import_scribe_types,
            tag_ref="item_1",
            airflow_m3h=3000)
        intent = self._make_intent(_import_scribe_types,
            entities=[entity])
        self._merge(intent, state, "GDB")
        assert state.tags["item_1"].airflow_m3h == 3000

    def test_entity_material_locks_state(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        entity = self._make_entity(_import_scribe_types,
            tag_ref="item_1",
            material="RF")
        intent = self._make_intent(_import_scribe_types,
            entities=[entity])
        self._merge(intent, state, "GDB")
        assert state.locked_material == MaterialCode.RF

    def test_entity_product_family_overrides(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         product_family="GDB")
        entity = self._make_entity(_import_scribe_types,
            tag_ref="item_1",
            product_family="GDC")
        intent = self._make_intent(_import_scribe_types,
            entities=[entity])
        self._merge(intent, state, "GDB")
        assert state.tags["item_1"].product_family == "GDC"

    def test_entity_housing_length_overrides_auto(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         filter_depth=292)
        # Auto-derived length should be 550
        assert state.tags["item_1"].housing_length == 550
        entity = self._make_entity(_import_scribe_types,
            tag_ref="item_1",
            housing_length=750)
        intent = self._make_intent(_import_scribe_types,
            entities=[entity])
        self._merge(intent, state, "GDB")
        assert state.tags["item_1"].housing_length == 750

    def test_entity_connection_type_to_resolved(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        entity = self._make_entity(_import_scribe_types,
            tag_ref="item_1",
            connection_type="PG")
        intent = self._make_intent(_import_scribe_types,
            entities=[entity])
        self._merge(intent, state, "GDB")
        assert state.resolved_params["connection_type"] == "PG"

    def test_entity_corrosion_class_to_resolved(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        entity = self._make_entity(_import_scribe_types,
            tag_ref="item_1",
            required_corrosion_class="C5")
        intent = self._make_intent(_import_scribe_types,
            entities=[entity])
        self._merge(intent, state, "GDB")
        assert state.resolved_params["required_corrosion_class"] == "C5"

    def test_parameters_route_to_resolved_params(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        intent = self._make_intent(_import_scribe_types,
            parameters={"max_width_mm": 700, "door_side": "L"})
        self._merge(intent, state, "GDB")
        assert state.resolved_params["max_width_mm"] == "700"
        assert state.resolved_params["door_side"] == "L"

    def test_filter_depth_param_routes_to_tag_and_params(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        intent = self._make_intent(_import_scribe_types,
            parameters={"filter_depth": 292})
        self._merge(intent, state, "GDB")
        assert state.resolved_params["filter_depth"] == "292"
        assert state.tags["item_1"].filter_depth == 292

    def test_project_name_routes_to_state(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        intent = self._make_intent(_import_scribe_types,
            project_name="Big Project")
        self._merge(intent, state, "GDB")
        assert state.project_name == "Big Project"

    def test_project_name_not_overwritten(self, _import_scribe_types):
        state = TechnicalState()
        state.set_project("Original")
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        intent = self._make_intent(_import_scribe_types,
            project_name="New Name")
        self._merge(intent, state, "GDB")
        assert state.project_name == "Original"

    def test_clarification_airflow_routes_to_all_tags(self, _import_scribe_types):
        state = TechnicalState()
        state.pending_clarification = "airflow"
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        state.merge_tag("item_2", filter_width=300, filter_height=600)
        intent = self._make_intent(_import_scribe_types,
            clarification_answers={"airflow": 3000})
        self._merge(intent, state, "GDB")
        assert state.tags["item_1"].airflow_m3h == 3000
        assert state.tags["item_2"].airflow_m3h == 3000

    def test_clarification_depth_routes_to_all_tags(self, _import_scribe_types):
        state = TechnicalState()
        state.pending_clarification = "filter_depth"
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        state.merge_tag("item_2", filter_width=300, filter_height=600)
        intent = self._make_intent(_import_scribe_types,
            clarification_answers={"filter_depth": 292})
        self._merge(intent, state, "GDB")
        assert state.tags["item_1"].filter_depth == 292
        assert state.tags["item_2"].filter_depth == 292

    def test_clarification_ignored_without_pending(self, _import_scribe_types):
        """Clarification answers are ignored when no pending_clarification."""
        state = TechnicalState()
        state.pending_clarification = None  # No pending
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        intent = self._make_intent(_import_scribe_types,
            clarification_answers={"airflow": 3000})
        self._merge(intent, state, "GDB")
        assert state.tags["item_1"].airflow_m3h is None

    def test_correct_action_overrides_dimensions(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600)
        action = self._make_action(_import_scribe_types,
            type="CORRECT", target_tag="item_1", field="dimensions",
            value={"width": 900, "height": 600})
        intent = self._make_intent(_import_scribe_types,
            actions=[action])
        self._merge(intent, state, "GDB")
        # 900x600 — above orientation threshold → NOT swapped
        assert state.tags["item_1"].housing_width == 900
        assert state.tags["item_1"].housing_height == 600

    def test_set_action_only_fills_empty(self, _import_scribe_types):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)
        action = self._make_action(_import_scribe_types,
            type="SET", target_tag="item_1", field="airflow_m3h",
            value=5000)
        intent = self._make_intent(_import_scribe_types,
            actions=[action])
        self._merge(intent, state, "GDB")
        # SET should NOT override existing airflow
        assert state.tags["item_1"].airflow_m3h == 3000

    def test_new_tag_creation_from_entity(self, _import_scribe_types):
        state = TechnicalState()
        entity = self._make_entity(_import_scribe_types,
            tag_ref="item_1",
            dimensions={"width": 600, "height": 900},
            product_family="GDB")
        intent = self._make_intent(_import_scribe_types,
            entities=[entity])
        self._merge(intent, state, "GDB")
        assert "item_1" in state.tags
        assert state.tags["item_1"].product_family == "GDB"

    def test_phantom_entity_without_data_not_created(self, _import_scribe_types):
        """Entity with no meaningful data → no tag created."""
        state = TechnicalState()
        entity = self._make_entity(_import_scribe_types,
            tag_ref="item_99")  # No dims, no airflow, no family
        intent = self._make_intent(_import_scribe_types,
            entities=[entity])
        self._merge(intent, state, "GDB")
        assert "item_99" not in state.tags


# =============================================================================
# SECTION 5: Session Graph Field Map (persist/load round-trip)
# =============================================================================

class TestPersistToGraph:
    """Pin which fields persist_to_graph sends to SessionGraphManager."""

    def test_persist_calls_all_project_methods(self):
        state = TechnicalState()
        state.project_name = "TestProject"
        state.lock_material("RF")
        state.detected_family = "GDB"
        state.pending_clarification = "airflow"
        state.accessories = ["ACC_RAIN_HOOD"]
        state.resolved_params = {"connection_type": "PG"}
        state.assembly_group = {"group_id": "asm_1", "stages": []}
        state.vetoed_families = ["FAM_GDC_FLEX"]
        state.merge_tag("item_1", filter_width=600, filter_height=600,
                         airflow_m3h=3000)

        mgr = MagicMock()
        state.persist_to_graph(mgr, "sess1")

        mgr.ensure_session.assert_called_once_with("sess1")
        mgr.set_project.assert_called_once_with("sess1", "TestProject")
        mgr.lock_material.assert_called_once_with("sess1", "RF")
        mgr.set_detected_family.assert_called_once_with("sess1", "GDB")
        mgr.set_pending_clarification.assert_called_once_with("sess1", "airflow")
        mgr.set_accessories.assert_called_once_with("sess1", ["ACC_RAIN_HOOD"])
        mgr.set_resolved_params.assert_called_once_with("sess1", {"connection_type": "PG"})
        mgr.set_assembly_group.assert_called_once_with("sess1", state.assembly_group)
        mgr.set_vetoed_families.assert_called_once_with("sess1", ["FAM_GDC_FLEX"])

    def test_persist_tag_fields_sent_to_upsert(self):
        state = TechnicalState()
        state.merge_tag("item_1",
                         filter_width=610, filter_height=305,
                         filter_depth=292, airflow_m3h=3000,
                         product_family="GDB")
        state.tags["item_1"].product_code = "GDB-300x600-550-R-PG-RF"
        state.tags["item_1"].weight_kg = 45.0
        state.tags["item_1"].assembly_group_id = "asm_1"
        state.turn_count = 3

        mgr = MagicMock()
        state.persist_to_graph(mgr, "sess1")

        upsert_call = mgr.upsert_tag.call_args
        args = upsert_call[0]
        kwargs = upsert_call[1]
        # session_id and tag_id are now positional args
        assert args[0] == "sess1"
        assert args[1] == "item_1"
        # merge_tag(610, 305) → housing(600, 300) → orientation swap → filter(305, 610)
        assert kwargs["filter_width"] == 305
        assert kwargs["filter_height"] == 610
        assert kwargs["filter_depth"] == 292
        assert kwargs["airflow_m3h"] == 3000
        assert kwargs["product_family"] == "GDB"
        assert kwargs["product_code"] == "GDB-300x600-550-R-PG-RF"
        assert kwargs["weight_kg"] == 45.0
        assert kwargs["quantity"] == 1
        assert kwargs["assembly_group_id"] == "asm_1"
        assert kwargs["source_message"] == 3

    def test_persist_skips_none_project_fields(self):
        """Empty state → only ensure_session + set_pending_clarification called."""
        state = TechnicalState()
        mgr = MagicMock()
        state.persist_to_graph(mgr, "sess1")
        mgr.ensure_session.assert_called_once()
        mgr.set_pending_clarification.assert_called_once()  # always called (even None)
        mgr.set_project.assert_not_called()
        mgr.lock_material.assert_not_called()
        mgr.set_detected_family.assert_not_called()

    def test_persist_multiple_tags(self):
        state = TechnicalState()
        state.merge_tag("item_1", filter_width=600, filter_height=600, airflow_m3h=3000)
        state.merge_tag("item_2", filter_width=300, filter_height=600, airflow_m3h=1500)
        mgr = MagicMock()
        state.persist_to_graph(mgr, "sess1")
        assert mgr.upsert_tag.call_count == 2
        tag_ids = [c[0][1] for c in mgr.upsert_tag.call_args_list]
        assert "item_1" in tag_ids
        assert "item_2" in tag_ids


class TestLoadFromGraph:
    """Pin which fields load_from_graph restores from SessionGraphManager data."""

    def test_load_restores_project_fields(self):
        mgr = MagicMock()
        mgr.get_project_state.return_value = {
            "project": {
                "name": "TestProject",
                "locked_material": "RF",
                "detected_family": "GDB",
                "pending_clarification": "airflow",
                "resolved_params": json.dumps({"connection_type": "PG", "door_side": "R"}),
                "accessories": ["ACC_RAIN_HOOD"],
                "assembly_group": json.dumps({
                    "group_id": "asm_1",
                    "stages": [{"role": "PROTECTOR", "tag_id": "item_1_stage_1"}],
                }),
                "vetoed_families": json.dumps(["FAM_GDC_FLEX"]),
                "customer": None,
            },
            "tags": [],
        }
        state = TechnicalState.load_from_graph(mgr, "sess1")
        assert state.project_name == "TestProject"
        assert state.locked_material == MaterialCode.RF
        assert state.detected_family == "GDB"
        assert state.pending_clarification == "airflow"
        assert state.resolved_params == {"connection_type": "PG", "door_side": "R"}
        assert state.accessories == ["ACC_RAIN_HOOD"]
        assert state.assembly_group["group_id"] == "asm_1"
        assert state.vetoed_families == ["FAM_GDC_FLEX"]

    def test_load_restores_tag_fields(self):
        mgr = MagicMock()
        mgr.get_project_state.return_value = {
            "project": None,
            "tags": [{
                "tag_id": "item_1",
                "filter_width": 610,
                "filter_height": 305,
                "filter_depth": 292,
                "housing_length": 550,
                "airflow_m3h": 3000,
                "product_family": "GDB",
                "product_code": "GDB-300x600-550-R-PG-RF",
                "weight_kg": 45.0,
                "quantity": 2,
            }],
        }
        state = TechnicalState.load_from_graph(mgr, "sess1")
        tag = state.tags["item_1"]
        # load_from_graph calls merge_tag → orientation swap (610/305 → 305/610)
        assert tag.filter_width == 305
        assert tag.filter_height == 610
        assert tag.filter_depth == 292
        assert tag.housing_length == 550
        assert tag.airflow_m3h == 3000
        assert tag.product_family == "GDB"
        assert tag.product_code == "GDB-300x600-550-R-PG-RF"
        assert tag.weight_kg == 45.0
        assert tag.quantity == 2
        # Housing dims auto-computed from filter via merge_tag (300x600)
        assert tag.housing_width == 300
        assert tag.housing_height == 600

    def test_load_restores_assembly_roles(self):
        mgr = MagicMock()
        mgr.get_project_state.return_value = {
            "project": {
                "name": "Test", "locked_material": None,
                "detected_family": None, "pending_clarification": None,
                "resolved_params": None, "accessories": None,
                "assembly_group": json.dumps({
                    "group_id": "assembly_item_1",
                    "stages": [
                        {"role": "PROTECTOR", "tag_id": "item_1_stage_1"},
                        {"role": "TARGET", "tag_id": "item_1_stage_2"},
                    ],
                }),
                "vetoed_families": None,
                "customer": None,
            },
            "tags": [
                {"tag_id": "item_1_stage_1", "filter_width": 600, "filter_height": 600,
                 "airflow_m3h": 3000},
                {"tag_id": "item_1_stage_2", "filter_width": 600, "filter_height": 600,
                 "airflow_m3h": 3000},
            ],
        }
        state = TechnicalState.load_from_graph(mgr, "sess1")
        assert state.tags["item_1_stage_1"].assembly_role == "PROTECTOR"
        assert state.tags["item_1_stage_1"].assembly_group_id == "assembly_item_1"
        assert state.tags["item_1_stage_2"].assembly_role == "TARGET"
        assert state.tags["item_1_stage_2"].assembly_group_id == "assembly_item_1"

    def test_load_empty_session(self):
        mgr = MagicMock()
        mgr.get_project_state.return_value = {
            "project": None,
            "tags": [],
        }
        state = TechnicalState.load_from_graph(mgr, "sess1")
        assert state.project_name is None
        assert state.locked_material is None
        assert state.detected_family is None
        assert len(state.tags) == 0

    def test_load_recomputes_completeness(self):
        mgr = MagicMock()
        mgr.get_project_state.return_value = {
            "project": None,
            "tags": [{
                "tag_id": "item_1",
                "filter_width": 600, "filter_height": 600,
                "filter_depth": 292,
                "airflow_m3h": 3000,
            }],
        }
        state = TechnicalState.load_from_graph(mgr, "sess1")
        # merge_tag → check_completeness called
        assert state.tags["item_1"].is_complete is True
        assert state.tags["item_1"].housing_length == 550  # auto-derived


class TestUpsertTagFieldCompleteness:
    """Pin the EXACT field names that upsert_tag accepts in session_graph.py."""

    def test_all_14_fields_accepted(self):
        """upsert_tag must accept these exact keyword arguments."""
        from backend.logic.session_graph import SessionGraphManager
        mgr = SessionGraphManager.__new__(SessionGraphManager)
        mgr._run_query = MagicMock(return_value=[{
            "tag": {"tag_id": "item_1", "housing_width": 600, "housing_height": 600}
        }])
        mgr._run_write = MagicMock()

        # Call with all known fields — must not raise TypeError
        mgr.upsert_tag(
            session_id="sess1",
            tag_id="item_1",
            filter_width=600,
            filter_height=600,
            filter_depth=292,
            airflow_m3h=3000,
            product_family="GDB",
            product_code="GDB-600x600-550-R-PG-RF",
            weight_kg=45.0,
            quantity=2,
            source_message=1,
            assembly_group_id="asm_1",
        )
        # If we get here without TypeError, all fields are accepted
        assert mgr._run_query.called

    def test_dynamic_set_clause_contains_field_names(self):
        """Verify the Cypher SET clause includes provided field names."""
        from backend.logic.session_graph import SessionGraphManager
        mgr = SessionGraphManager.__new__(SessionGraphManager)
        mgr._run_query = MagicMock(return_value=[{
            "tag": {"tag_id": "item_1", "housing_width": 600, "housing_height": 600}
        }])
        mgr._run_write = MagicMock()

        mgr.upsert_tag(
            session_id="sess1",
            tag_id="item_1",
            filter_width=600,
            filter_height=600,
            airflow_m3h=3000,
        )
        cypher = mgr._run_query.call_args[0][0]
        assert "t.filter_width" in cypher
        assert "t.filter_height" in cypher
        assert "t.airflow_m3h" in cypher
        # Housing dims should be computed and included
        assert "t.housing_width" in cypher
        assert "t.housing_height" in cypher
