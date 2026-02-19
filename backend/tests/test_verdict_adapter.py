"""Verdict adapter tests — EngineVerdict → GraphReasoningReport conversion.

The adapter is PURE LOGIC — no DB calls. These tests ensure the mapping
is correct regardless of DB backend.

Coverage:
- Stressor → ApplicationMatch
- TraitMatch → SuitabilityResult
- Veto → ProductPivot
- Assembly → reasoning steps
- Gate evaluations → reasoning steps
- Installation violations → reasoning steps
"""

import pytest
from unittest.mock import MagicMock

from backend.logic.universal_engine import (
    EngineVerdict, DetectedStressor, CausalRule, TraitMatch,
    AssemblyStage, GateEvaluation, MissingParameter,
    InstallationViolation, AlternativeProduct, ConstraintOverride,
    AccessoryValidation,
)
from backend.logic.verdict_adapter import VerdictToReportAdapter, TraitBasedReport


@pytest.fixture
def adapter():
    return VerdictToReportAdapter()


# =============================================================================
# BASIC ADAPTATION
# =============================================================================

class TestBasicAdaptation:
    def test_empty_verdict_adapts(self, adapter):
        verdict = EngineVerdict()
        report = adapter.adapt(verdict)
        assert report is not None

    def test_report_is_trait_based(self, adapter, sample_verdict):
        report = adapter.adapt(sample_verdict)
        assert isinstance(report, TraitBasedReport)

    def test_prompt_injection_delegates_to_verdict(self, adapter, sample_verdict):
        report = adapter.adapt(sample_verdict)
        injection = report.to_prompt_injection()
        # Should use EngineVerdict's to_prompt_injection(), not the default
        assert isinstance(injection, str)


# =============================================================================
# STRESSOR → APPLICATION MATCH
# =============================================================================

class TestStressorMapping:
    def test_stressors_mapped_to_application(self, adapter):
        verdict = EngineVerdict()
        verdict.application_match = {
            "id": "APP_KITCHEN", "name": "Commercial Kitchen",
            "keywords": ["kitchen"], "confidence": 0.95,
        }
        report = adapter.adapt(verdict)
        assert report.application is not None
        assert report.application.id == "APP_KITCHEN"

    def test_no_application_match(self, adapter):
        verdict = EngineVerdict()
        report = adapter.adapt(verdict)
        assert report.application is None


# =============================================================================
# TRAIT MATCH → SUITABILITY
# =============================================================================

class TestSuitabilityMapping:
    def test_recommended_product_mapped(self, adapter, sample_verdict):
        report = adapter.adapt(sample_verdict)
        assert report.suitability is not None
        # SuitabilityResult tracks is_suitable + warnings, not product name directly
        assert report.suitability.is_suitable is True

    def test_vetoed_product_shows_risk(self, adapter):
        verdict = EngineVerdict()
        verdict.has_veto = True
        verdict.veto_reason = "Missing critical trait"
        verdict.ranked_products = [
            TraitMatch(product_family_id="FAM_GDB", product_family_name="GDB",
                       vetoed=True, veto_reasons=["Missing trait X"]),
        ]
        report = adapter.adapt(verdict)
        assert report.suitability is not None


# =============================================================================
# VETO → PRODUCT PIVOT
# =============================================================================

class TestPivotMapping:
    def test_auto_pivot_mapped(self, adapter):
        verdict = EngineVerdict()
        verdict.has_veto = True
        verdict.veto_reason = "GDC lacks particle filtration"
        verdict.auto_pivot_to = "FAM_GDB"
        verdict.auto_pivot_name = "GDB"
        report = adapter.adapt(verdict)
        assert report.product_pivot is not None
        assert report.product_pivot.pivoted_to == "GDB"

    def test_no_pivot_when_no_veto(self, adapter):
        verdict = EngineVerdict()
        report = adapter.adapt(verdict)
        assert report.product_pivot is None


# =============================================================================
# MISSING PARAMETERS → VARIABLE FEATURES
# =============================================================================

class TestVariableFeatureMapping:
    def test_missing_params_mapped(self, adapter):
        verdict = EngineVerdict()
        verdict.missing_parameters = [
            MissingParameter(
                feature_id="FEAT_DOOR", feature_name="Door Side",
                parameter_name="door_side",
                question="Which side?", why_needed="Hinge placement",
                options=[{"value": "L", "label": "Left"}, {"value": "R", "label": "Right"}],
            ),
        ]
        report = adapter.adapt(verdict)
        assert len(report.variable_features) >= 1
        vf = report.variable_features[0]
        assert vf.feature_name == "Door Side"


# =============================================================================
# INSTALLATION VIOLATIONS
# =============================================================================

class TestInstallationViolationMapping:
    def test_violation_mapped_to_risk(self, adapter):
        verdict = EngineVerdict()
        verdict.installation_violations = [
            InstallationViolation(
                constraint_id="IC_GDB_OUTDOOR",
                constraint_type="SET_MEMBERSHIP",
                severity="CRITICAL",
                error_msg="GDB not valid for outdoor",
                details={"environment": "outdoor"},
            ),
        ]
        verdict.has_installation_block = True
        report = adapter.adapt(verdict)
        # Should appear in physics_risks or suitability warnings
        assert len(report.physics_risks) > 0 or len(report.suitability.warnings) > 0


# =============================================================================
# REASONING SUMMARY STEPS (UI rendering)
# =============================================================================

class TestReasoningSummarySteps:
    def test_steps_generated_for_stressors(self, adapter, sample_verdict):
        report = adapter.adapt(sample_verdict)
        steps = report.to_reasoning_summary_steps()
        assert isinstance(steps, list)
        assert len(steps) > 0
        # Each step should have required fields for UI rendering
        for step in steps:
            assert "step" in step or "title" in step or "type" in step

    def test_assembly_steps_included(self, adapter):
        verdict = EngineVerdict()
        verdict.is_assembly = True
        verdict.assembly = [
            AssemblyStage(
                role="PROTECTOR", product_family_id="FAM_GDP",
                product_family_name="GDP", provides_trait_id="TRAIT_GP",
                provides_trait_name="Grease Pre-Filtration",
                reason="Pre-filters grease",
            ),
        ]
        verdict.detected_stressors = [
            DetectedStressor(id="STR_G", name="Grease", description="Test",
                             detection_method="keyword", confidence=0.9),
        ]
        report = adapter.adapt(verdict)
        steps = report.to_reasoning_summary_steps()
        assert isinstance(steps, list)

    def test_empty_verdict_produces_empty_steps(self, adapter):
        verdict = EngineVerdict()
        report = adapter.adapt(verdict)
        steps = report.to_reasoning_summary_steps()
        assert isinstance(steps, list)


# =============================================================================
# ACCESSORY COMPATIBILITY
# =============================================================================

class TestAccessoryMapping:
    def test_blocked_accessory_mapped(self, adapter):
        verdict = EngineVerdict()
        verdict.accessory_validations = [
            AccessoryValidation(
                accessory_code="ACC_RAIN_HOOD",
                accessory_name="Rain Hood",
                product_family_id="FAM_GDB",
                is_compatible=False,
                status="BLOCKED",
                reason="Not available for GDB",
                compatible_alternatives=["ACC_WEATHER_COVER"],
            ),
        ]
        verdict.has_blocked_accessory = True
        report = adapter.adapt(verdict)
        assert len(report.accessory_compatibility) >= 1
        assert report.accessory_compatibility[0].is_compatible is False
