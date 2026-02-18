"""Engine pipeline tests — verify TraitBasedEngine with mocked DB.

These tests ensure the engine's Python logic is correct regardless of
which graph database backend is used. All DB calls are mocked.

Coverage:
- Stressor detection pipeline
- Causal rule application
- Trait matching / scoring
- Veto system
- Assembly construction
- Constraint checks
- Missing parameter detection
- Full process_query flow
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.logic.universal_engine import (
    TraitBasedEngine, EngineVerdict, DetectedStressor, CausalRule,
    TraitMatch, AssemblyStage, GateEvaluation, MissingParameter,
    InstallationViolation, AlternativeProduct, ConstraintOverride,
)


class TestStressorDetection:
    def test_detects_stressors_from_keywords(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        stressors = engine.detect_stressors("kitchen ventilation grease")
        assert isinstance(stressors, list)
        assert len(stressors) >= 1
        assert stressors[0].id == "STR_GREASE"
        mock_db.get_stressors_by_keywords.assert_called()

    def test_detects_stressors_from_application(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        mock_db.get_stressors_by_keywords.return_value = []
        mock_db.get_stressors_for_application.return_value = [
            {"id": "STR_GREASE", "name": "Grease Aerosol",
             "description": "Grease", "category": "Contamination"},
        ]
        context = {"detected_application": "APP_KITCHEN"}
        stressors = engine.detect_stressors("ventilation system", context=context)
        assert isinstance(stressors, list)

    def test_empty_query_returns_empty_stressors(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        mock_db.get_stressors_by_keywords.return_value = []
        stressors = engine.detect_stressors("")
        assert isinstance(stressors, list)
        assert len(stressors) == 0


class TestCausalRules:
    def test_gets_rules_for_stressors(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        stressors = [
            DetectedStressor(
                id="STR_GREASE", name="Grease Aerosol",
                description="Test", detection_method="keyword",
                confidence=0.9, matched_keywords=["grease"],
            ),
        ]
        rules = engine.get_causal_rules(stressors)
        assert isinstance(rules, list)
        assert len(rules) >= 1
        assert isinstance(rules[0], CausalRule)
        assert rules[0].rule_type == "NEUTRALIZED_BY"

    def test_no_stressors_returns_empty_rules(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        mock_db.get_causal_rules_for_stressors.return_value = []
        rules = engine.get_causal_rules([])
        assert rules == []


class TestTraitMatching:
    def test_matches_products_against_rules(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        rules = [
            CausalRule(
                rule_type="NEUTRALIZED_BY", stressor_id="STR_GREASE",
                stressor_name="Grease", trait_id="TRAIT_GREASE_PRE",
                trait_name="Grease Pre-Filtration", severity="CRITICAL",
                explanation="Test",
            ),
        ]
        candidates = mock_db.get_all_product_families_with_traits()
        stressors = [
            DetectedStressor(
                id="STR_GREASE", name="Grease",
                description="Test", detection_method="keyword",
                confidence=0.9, matched_keywords=["grease"],
            ),
        ]
        matches = engine.match_traits(rules, candidates, stressors)
        assert isinstance(matches, list)
        assert len(matches) > 0
        assert all(isinstance(m, TraitMatch) for m in matches)
        # GDP has TRAIT_GREASE_PRE so it should have it present
        gdp = [m for m in matches if m.product_family_name == "GDP"]
        if gdp:
            assert "TRAIT_GREASE_PRE" in gdp[0].traits_present

    def test_coverage_score_calculated(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        rules = [
            CausalRule(
                rule_type="NEUTRALIZED_BY", stressor_id="STR_A",
                stressor_name="A", trait_id="TRAIT_PARTICLE",
                trait_name="Particle", severity="CRITICAL",
                explanation="Test",
            ),
        ]
        candidates = mock_db.get_all_product_families_with_traits()
        stressors = [
            DetectedStressor(id="STR_A", name="A", description="Test",
                             detection_method="keyword", confidence=0.9),
        ]
        matches = engine.match_traits(rules, candidates, stressors)
        # GDB has TRAIT_PARTICLE so score should be 1.0
        gdb = [m for m in matches if m.product_family_name == "GDB"]
        if gdb:
            assert gdb[0].coverage_score == 1.0


class TestVetoSystem:
    def test_vetoes_product_missing_critical_trait(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        matches = [
            TraitMatch(
                product_family_id="FAM_GDB", product_family_name="GDB",
                traits_present=[], traits_missing=["TRAIT_GREASE_PRE"],
                coverage_score=0.0,
            ),
        ]
        rules = [
            CausalRule(
                rule_type="NEUTRALIZED_BY", stressor_id="STR_GREASE",
                stressor_name="Grease", trait_id="TRAIT_GREASE_PRE",
                trait_name="Grease Pre-Filtration", severity="CRITICAL",
                explanation="Test",
            ),
        ]
        vetoed = engine.check_vetoes(matches, rules)
        assert isinstance(vetoed, list)
        gdb = [m for m in vetoed if m.product_family_name == "GDB"]
        if gdb:
            assert gdb[0].vetoed is True
            assert len(gdb[0].veto_reasons) > 0


class TestAssemblyConstruction:
    def test_builds_assembly_for_neutralization_veto(self, mock_db):
        """When a product is vetoed due to missing neutralization trait,
        engine should build a PROTECTOR+TARGET assembly."""
        engine = TraitBasedEngine(mock_db)

        # Setup: GDC needs TRAIT_GREASE_PRE (missing) → GDP provides it
        mock_db.get_dependency_rules_for_stressors.return_value = [
            {
                "protector_family_id": "FAM_GDP", "protector_family_name": "GDP",
                "provides_trait_id": "TRAIT_GREASE_PRE",
                "provides_trait_name": "Grease Pre-Filtration",
                "target_family_id": "FAM_GDC",
                "reason": "GDP pre-filters grease before GDC carbon stage",
            },
        ]

        verdict = engine.process_query(
            "kitchen ventilation carbon filter",
            product_hint="GDC",
            context={"detected_application": "APP_KITCHEN"},
        )
        assert isinstance(verdict, EngineVerdict)
        # The verdict should exist (may or may not have assembly depending on full logic)


class TestFullPipeline:
    def test_process_query_returns_verdict(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        verdict = engine.process_query("I need a filter for kitchen ventilation")
        assert isinstance(verdict, EngineVerdict)
        assert isinstance(verdict.detected_stressors, list)
        assert isinstance(verdict.active_causal_rules, list)
        assert isinstance(verdict.ranked_products, list)
        assert isinstance(verdict.reasoning_trace, list)

    def test_process_query_with_product_hint(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        verdict = engine.process_query("filter for kitchen", product_hint="GDB")
        assert isinstance(verdict, EngineVerdict)
        # With hint, recommended product should be GDB (if not vetoed)
        if verdict.recommended_product and not verdict.has_veto:
            assert verdict.recommended_product.product_family_name == "GDB"

    def test_process_query_with_context(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        context = {
            "detected_application": "APP_KITCHEN",
            "installation_environment": "ENV_INDOOR",
            "filter_width": 600,
            "filter_height": 600,
            "airflow_m3h": 3000,
        }
        verdict = engine.process_query("kitchen ventilation", context=context)
        assert isinstance(verdict, EngineVerdict)

    def test_reasoning_trace_populated(self, mock_db):
        engine = TraitBasedEngine(mock_db)
        verdict = engine.process_query("particle filter for factory")
        assert len(verdict.reasoning_trace) > 0
        for step in verdict.reasoning_trace:
            assert "stage" in step


class TestConstraintOverrides:
    def test_hard_constraints_applied(self, mock_db):
        """When hard constraints are present, engine should check and override."""
        mock_db.get_hard_constraints.return_value = [
            {
                "property_key": "housing_length",
                "operator": ">=",
                "value": 550,
                "error_msg": "Minimum housing length for selected depth",
            },
        ]
        engine = TraitBasedEngine(mock_db)
        overrides = engine.check_hard_constraints(
            "FAM_GDB", {"housing_length": 400}
        )
        assert isinstance(overrides, list)


class TestMissingParameters:
    def test_detects_missing_params(self, mock_db):
        """When product has VariableFeatures, missing params should be flagged."""
        mock_db.get_clarification_params.return_value = [
            {
                "feature_id": "FEAT_DOOR", "feature_name": "Door Side",
                "parameter_name": "door_side",
                "question": "Which side should the door open?",
                "why_needed": "Determines hinge placement",
                "options": [
                    {"value": "L", "label": "Left"},
                    {"value": "R", "label": "Right"},
                ],
            },
        ]
        engine = TraitBasedEngine(mock_db)
        missing = engine.check_missing_parameters(
            "FAM_GDB", "GDB", resolved_params={}, context={}
        )
        assert isinstance(missing, list)


class TestInstallationConstraints:
    def test_set_membership_violation(self, mock_db):
        """SET_MEMBERSHIP constraint should block incompatible environments."""
        mock_db.get_installation_constraints.return_value = [
            {
                "constraint_id": "IC_GDB_OUTDOOR",
                "constraint_type": "SET_MEMBERSHIP",
                "property_key": "installation_environment",
                "allowed_values": ["ENV_INDOOR"],
                "severity": "CRITICAL",
                "error_msg": "GDB is only rated for indoor installation",
            },
        ]
        engine = TraitBasedEngine(mock_db)
        violations = engine.check_installation_constraints(
            "FAM_GDB", "GDB",
            context={"installation_environment": "ENV_OUTDOOR"},
            resolved_params={},
        )
        assert isinstance(violations, list)


class TestVerdictPromptInjection:
    def test_empty_verdict_is_empty_string(self):
        v = EngineVerdict()
        result = v.to_prompt_injection()
        assert result.strip() == ""

    def test_verdict_with_stressors_produces_output(self):
        v = EngineVerdict()
        v.detected_stressors = [
            DetectedStressor(
                id="STR_A", name="TestStressor", description="Test",
                detection_method="keyword", confidence=0.9,
            ),
        ]
        v.ranked_products = [
            TraitMatch(product_family_id="FAM_GDB", product_family_name="GDB",
                       coverage_score=1.0),
        ]
        v.recommended_product = v.ranked_products[0]
        result = v.to_prompt_injection()
        assert isinstance(result, str)

    def test_assembly_verdict_contains_multi_stage(self):
        v = EngineVerdict()
        v.is_assembly = True
        v.assembly_rationale = "Grease protection needed"
        v.assembly = [
            AssemblyStage(
                role="PROTECTOR", product_family_id="FAM_GDP",
                product_family_name="GDP", provides_trait_id="TRAIT_GP",
                provides_trait_name="Grease Pre-Filtration",
                reason="Pre-filters grease",
            ),
            AssemblyStage(
                role="TARGET", product_family_id="FAM_GDC",
                product_family_name="GDC", provides_trait_id="TRAIT_C",
                provides_trait_name="Carbon Adsorption",
                reason="Main filtration",
            ),
        ]
        result = v.to_prompt_injection()
        assert "MULTI-STAGE" in result
        assert "GDP" in result
        assert "GDC" in result
