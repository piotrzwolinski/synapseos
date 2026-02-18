"""Pin TechnicalState behavior: merge_tag, serialization, completeness."""

import pytest
from backend.logic.state import TechnicalState, TagSpecification, MaterialCode


class TestMergeTag:
    def test_creates_new_tag(self, empty_state):
        tag = empty_state.merge_tag("item_1", filter_width=305, filter_height=610)
        assert "item_1" in empty_state.tags
        assert tag.filter_width == 305
        # Dimension mapping applied:
        assert tag.housing_width == 300
        assert tag.housing_height == 600

    def test_updates_existing_tag(self, empty_state):
        empty_state.merge_tag("item_1", filter_width=600, filter_height=600)
        empty_state.merge_tag("item_1", airflow_m3h=3000)
        tag = empty_state.tags["item_1"]
        assert tag.airflow_m3h == 3000
        assert tag.housing_width == 600  # Not lost

    def test_none_values_do_not_overwrite(self, empty_state):
        empty_state.merge_tag("item_1", filter_width=600, filter_height=600)
        empty_state.merge_tag("item_1", filter_width=None)
        assert empty_state.tags["item_1"].filter_width == 600

    def test_auto_derives_housing_length(self, empty_state):
        empty_state.merge_tag("item_1", filter_width=600, filter_height=600, filter_depth=292)
        assert empty_state.tags["item_1"].housing_length == 550

    def test_auto_checks_completeness(self, empty_state):
        empty_state.merge_tag("item_1", filter_width=600, filter_height=600, filter_depth=292, airflow_m3h=3000)
        assert empty_state.tags["item_1"].is_complete is True


class TestSerialization:
    def test_to_dict_from_dict_roundtrip(self, state_fully_populated):
        d = state_fully_populated.to_dict()
        restored = TechnicalState.from_dict(d)
        assert restored.to_dict() == d

    def test_material_serializes_as_string(self, state_with_material):
        d = state_with_material.to_dict()
        assert d["locked_material"] == "RF"
        assert isinstance(d["locked_material"], str)

    def test_material_deserializes_to_enum(self, state_with_material):
        d = state_with_material.to_dict()
        restored = TechnicalState.from_dict(d)
        assert isinstance(restored.locked_material, MaterialCode)
        assert restored.locked_material == MaterialCode.RF

    def test_assembly_group_roundtrip(self, state_with_assembly):
        d = state_with_assembly.to_dict()
        assert d["assembly_group"] is not None
        assert len(d["assembly_group"]["stages"]) == 2
        restored = TechnicalState.from_dict(d)
        assert restored.assembly_group is not None
        assert len(restored.assembly_group["stages"]) == 2

    def test_resolved_params_roundtrip(self, state_fully_populated):
        d = state_fully_populated.to_dict()
        assert d["resolved_params"]["connection_type"] == "PG"
        restored = TechnicalState.from_dict(d)
        assert restored.resolved_params["connection_type"] == "PG"

    def test_from_dict_recomputes_completeness(self):
        """from_dict should recompute is_complete, not rely on stored value."""
        d = {
            "tags": {
                "item_1": {
                    "tag_id": "item_1",
                    "filter_width": 600, "filter_height": 600,
                    "filter_depth": 292, "airflow_m3h": 3000,
                    "housing_width": None, "housing_height": None,
                    "housing_length": None, "product_family": None,
                    "product_code": None, "quantity": 1,
                    "weight_kg": None, "modules_needed": 1,
                    "total_weight_kg": None, "total_airflow_m3h": None,
                    "is_complete": False,  # Stored as False
                    "missing_params": ["everything"],
                    "assembly_role": None, "assembly_group_id": None,
                }
            }
        }
        restored = TechnicalState.from_dict(d)
        # Should be recomputed as True (all needed params are present)
        assert restored.tags["item_1"].is_complete is True


class TestCompactSummary:
    def test_format_includes_tag_data(self, state_fully_populated):
        summary = state_fully_populated.to_compact_summary()
        assert "item_1" in summary
        assert "300x600" in summary
        assert "3000" in summary

    def test_format_includes_material(self, state_with_material):
        summary = state_with_material.to_compact_summary()
        assert "RF" in summary

    def test_empty_state_returns_marker(self, empty_state):
        summary = empty_state.to_compact_summary()
        assert summary == "(empty state)"


class TestAllTagsComplete:
    def test_incomplete_if_no_tags(self, empty_state):
        assert empty_state.all_tags_complete() is False

    def test_incomplete_if_missing_airflow(self, empty_state):
        empty_state.merge_tag("item_1", filter_width=600, filter_height=600)
        assert empty_state.all_tags_complete() is False

    def test_complete_when_all_params_present(self, empty_state):
        empty_state.merge_tag("item_1", filter_width=600, filter_height=600,
                              filter_depth=292, airflow_m3h=3000)
        assert empty_state.all_tags_complete() is True

    def test_mixed_completeness(self, empty_state):
        empty_state.merge_tag("item_1", filter_width=600, filter_height=600,
                              filter_depth=292, airflow_m3h=3000)
        empty_state.merge_tag("item_2", filter_width=600, filter_height=600)
        assert empty_state.all_tags_complete() is False


class TestVetoedFamilies:
    def test_vetoed_families_serialization(self):
        state = TechnicalState()
        state.vetoed_families = ["FAM_GDC_FLEX", "FAM_GDMI"]
        d = state.to_dict()
        # vetoed_families not in to_dict (not in the explicit fields), check in prompt context
        ctx = state.to_prompt_context()
        assert "GDC_FLEX" in ctx or "GDC-FLEX" in ctx
        assert "VETOED" in ctx
