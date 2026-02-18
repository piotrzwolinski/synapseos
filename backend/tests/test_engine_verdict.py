"""Pin EngineVerdict.to_prompt_injection() output format.

The verdict text is injected into the LLM context. Format changes = LLM behavior regression.
"""

import pytest
from dataclasses import dataclass, field
from typing import Optional


# Minimal dataclass stubs matching the real types used by EngineVerdict
@dataclass
class _TraitMatch:
    product_family_id: str = ""
    product_family_name: str = ""
    trait_score: float = 0.0
    vetoed: bool = False
    veto_reasons: list = field(default_factory=list)


@dataclass
class _AssemblyStage:
    role: str = ""
    product_family_name: str = ""
    provides_trait_name: str = ""
    reason: str = ""


@dataclass
class _GateEvaluation:
    gate_name: str = ""
    state: str = "OPEN"
    stressor_name: str = ""
    physics_explanation: str = ""
    missing_parameters: list = field(default_factory=list)


@dataclass
class _ConstraintOverride:
    property_key: str = ""
    original_value: float = 0
    corrected_value: float = 0
    operator: str = ">="
    error_msg: str = ""


@dataclass
class _AlternativeProduct:
    product_family_id: str = ""
    product_family_name: str = ""
    why_it_works: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class _InstallationViolation:
    constraint_id: str = ""
    constraint_type: str = ""
    severity: str = "WARNING"
    error_msg: str = ""
    details: dict = field(default_factory=dict)
    alternatives: list = field(default_factory=list)


# Import the real EngineVerdict
from backend.logic.universal_engine import EngineVerdict


class TestVerdictEmpty:
    def test_empty_verdict_returns_empty_string(self):
        v = EngineVerdict()
        result = v.to_prompt_injection()
        assert result == "" or result.strip() == ""


class TestVerdictAssembly:
    def test_assembly_section_present(self):
        v = EngineVerdict()
        v.is_assembly = True
        v.assembly_rationale = "Protective pre-stage for grease"
        v.assembly = [
            _AssemblyStage(
                role="PROTECTOR",
                product_family_name="GDP",
                provides_trait_name="Grease protection",
                reason="Pre-filters grease particles",
            ),
            _AssemblyStage(
                role="TARGET",
                product_family_name="GDB",
                provides_trait_name="Particle filtration",
                reason="Main particle filtration stage",
            ),
        ]
        result = v.to_prompt_injection()
        assert "MULTI-STAGE" in result
        assert "GDP" in result
        assert "GDB" in result
        assert "PROTECTOR" in result
        assert "TARGET" in result
        assert "Protective pre-stage for grease" in result

    def test_assembly_suppressed_when_critical_violation(self):
        """Assembly should NOT appear when critical IC violations exist."""
        v = EngineVerdict()
        v.is_assembly = True
        v.assembly = [
            _AssemblyStage(role="PROTECTOR", product_family_name="GDP",
                           provides_trait_name="Protection", reason="Test"),
        ]
        v.installation_violations = [
            _InstallationViolation(
                severity="CRITICAL",
                constraint_type="SET_MEMBERSHIP",
                error_msg="Product not valid for this environment",
                details={"env": "outdoor"},
            ),
        ]
        v.has_installation_block = True
        result = v.to_prompt_injection()
        assert "MULTI-STAGE" not in result
        assert "BLOCKED" in result


class TestVerdictVetoPivot:
    def test_veto_pivot_section(self):
        v = EngineVerdict()
        v.has_veto = True
        v.veto_reason = "GDC cannot handle particle filtration"
        v.auto_pivot_name = "GDB"
        result = v.to_prompt_injection()
        assert "SUBSTITUTION" in result
        assert "VETOED" in result
        assert "GDB" in result
        assert "GDC cannot handle particle filtration" in result

    def test_veto_pivot_suppressed_when_critical_violation(self):
        v = EngineVerdict()
        v.has_veto = True
        v.veto_reason = "Wrong product"
        v.auto_pivot_name = "GDB"
        v.installation_violations = [
            _InstallationViolation(severity="CRITICAL", error_msg="Blocked"),
        ]
        result = v.to_prompt_injection()
        assert "SUBSTITUTION" not in result


class TestVerdictGateEvaluations:
    def test_gate_validation_required(self):
        v = EngineVerdict()
        v.gate_evaluations = [
            _GateEvaluation(
                gate_name="Chlorine Gate",
                state="VALIDATION_REQUIRED",
                stressor_name="Chlorine",
                missing_parameters=[
                    {"property_key": "chlorine_ppm", "name": "Chlorine concentration", "question": "What is the chlorine level?"},
                ],
            ),
        ]
        result = v.to_prompt_injection()
        assert "LOGIC GATE" in result
        assert "Chlorine Gate" in result
        assert "VALIDATION_REQUIRED" in result
        assert "chlorine_ppm" in result
        assert "MUST ask" in result

    def test_gate_fired_shows_physics(self):
        v = EngineVerdict()
        v.gate_evaluations = [
            _GateEvaluation(
                gate_name="Grease Gate",
                state="FIRED",
                stressor_name="Grease",
                physics_explanation="Grease blocks filter pores rapidly",
            ),
        ]
        result = v.to_prompt_injection()
        assert "FIRED" in result
        assert "Grease" in result
        assert "blocks filter pores" in result

    def test_gate_deferred_when_blocked(self):
        """When all products are vetoed, gate questions should be deferred."""
        v = EngineVerdict()
        v.ranked_products = [
            _TraitMatch(product_family_id="FAM_GDB", vetoed=True),
            _TraitMatch(product_family_id="FAM_GDP", vetoed=True),
        ]
        v.gate_evaluations = [
            _GateEvaluation(
                gate_name="Chlorine Gate",
                state="VALIDATION_REQUIRED",
                stressor_name="Chlorine",
                missing_parameters=[{"property_key": "chlorine_ppm"}],
            ),
        ]
        result = v.to_prompt_injection()
        assert "Deferred" in result
        assert "MUST ask" not in result


class TestVerdictConstraintOverrides:
    def test_constraint_override_shown(self):
        v = EngineVerdict()
        v.constraint_overrides = [
            _ConstraintOverride(
                property_key="housing_length",
                original_value=400,
                corrected_value=550,
                operator=">=",
                error_msg="Minimum housing length for this depth",
            ),
        ]
        result = v.to_prompt_injection()
        assert "CONSTRAINT" in result or "OVERRIDE" in result
        assert "housing_length" in result
        assert "400" in result
        assert "550" in result


class TestVerdictInstallationViolations:
    def test_critical_violation_shows_blocked(self):
        v = EngineVerdict()
        v.installation_violations = [
            _InstallationViolation(
                severity="CRITICAL",
                constraint_type="SET_MEMBERSHIP",
                error_msg="GDB not valid for outdoor installation",
                details={"environment": "outdoor", "product": "GDB"},
            ),
        ]
        v.has_installation_block = True
        result = v.to_prompt_injection()
        assert "BLOCKED" in result
        assert "GDB not valid" in result
        assert "outdoor" in result

    def test_alternatives_shown_after_violation(self):
        alt = _AlternativeProduct(
            product_family_id="FAM_GDR",
            product_family_name="GDR",
            why_it_works="Designed for outdoor environments",
            details={"material_code": "RF"},
        )
        v = EngineVerdict()
        v.installation_violations = [
            _InstallationViolation(
                severity="CRITICAL",
                constraint_type="SET_MEMBERSHIP",
                error_msg="GDB blocked for outdoor",
                details={},
                alternatives=[alt],
            ),
        ]
        v.has_installation_block = True
        result = v.to_prompt_injection()
        assert "ALTERNATIVE" in result
        assert "GDR" in result

    def test_material_swap_alts_stripped_on_product_block(self):
        """When SET_MEMBERSHIP blocks a product, same-product material swaps are removed."""
        mat_alt = _AlternativeProduct(
            product_family_id="FAM_GDB",
            product_family_name="GDB",
            why_it_works="With RF material",
            details={"is_material_change": True, "material_code": "RF"},
        )
        other_alt = _AlternativeProduct(
            product_family_id="FAM_GDR",
            product_family_name="GDR",
            why_it_works="Outdoor-rated product",
            details={"material_code": "RF"},
        )
        v = EngineVerdict()
        v.installation_violations = [
            _InstallationViolation(
                severity="CRITICAL",
                constraint_type="SET_MEMBERSHIP",
                error_msg="GDB blocked for outdoor",
                details={},
                alternatives=[mat_alt, other_alt],
            ),
        ]
        v.has_installation_block = True
        result = v.to_prompt_injection()
        # GDR should appear (not a material swap), GDB material swap should be stripped
        assert "GDR" in result
        # The material swap alt (GDB with RF) should be removed
        lines = result.split("\n")
        alt_section_lines = [l for l in lines if "GDB" in l and "With RF" in l]
        assert len(alt_section_lines) == 0


class TestVerdictCapacity:
    def test_capacity_section(self):
        v = EngineVerdict()
        v.capacity_calculation = {
            "input_value": 6000,
            "input_requirement": "m³/h",
            "output_rating": 3400,
            "modules_needed": 2,
            "module_descriptor": "GDB-600x600",
        }
        result = v.to_prompt_injection()
        assert "CAPACITY" in result
        assert "6000" in result
        assert "3400" in result
        assert "2" in result
