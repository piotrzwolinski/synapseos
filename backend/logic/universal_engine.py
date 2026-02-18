"""
Trait-Based Reasoning Engine (Domain-Agnostic)

A generic reasoning engine that evaluates product suitability by matching
Physical Traits against Environmental Stressors using Causal Rules stored
in the graph database.

Algorithm:
1. DETECT STRESSORS: Find environmental attack vectors from user query
2. GET CAUSAL RULES: Traverse NEUTRALIZED_BY and DEMANDS_TRAIT relationships
3. GET CANDIDATES: Find product families with their trait sets
4. MATCH TRAITS: Compute trait coverage score for each product
5. CHECK VETOES: Block products missing CRITICAL-severity traits
6. GET CLARIFICATIONS: Determine missing parameters for recommended product
7. ASSEMBLE VERDICT: Build complete EngineVerdict

NO HARDCODED DOMAIN LOGIC — all knowledge is in the graph.
"""

import re
import math
import logging
import operator as op
from dataclasses import dataclass, field
from typing import Optional, Any

logger = logging.getLogger(__name__)


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class DetectedStressor:
    """An environmental stressor detected from the query."""
    id: str
    name: str
    description: str
    detection_method: str  # "keyword", "application_link", "environment_link"
    confidence: float
    source_context: Optional[str] = None
    matched_keywords: list[str] = field(default_factory=list)


@dataclass
class CausalRule:
    """A causal rule linking stressors to traits."""
    rule_type: str  # "NEUTRALIZED_BY" or "DEMANDS_TRAIT"
    stressor_id: str
    stressor_name: str
    trait_id: str
    trait_name: str
    severity: str  # "CRITICAL", "WARNING", "INFO"
    explanation: str


@dataclass
class TraitMatch:
    """A product's trait coverage evaluation result."""
    product_family_id: str
    product_family_name: str
    product_type: Optional[str] = None
    traits_present: list[str] = field(default_factory=list)
    traits_missing: list[str] = field(default_factory=list)
    traits_neutralized: list[str] = field(default_factory=list)
    coverage_score: float = 1.0
    vetoed: bool = False
    veto_reasons: list[str] = field(default_factory=list)
    selection_priority: int = 50  # Graph-driven: lower = preferred (v2.8)


@dataclass
class DetectedGoal:
    """A functional goal detected from the user query."""
    id: str
    name: str
    description: str
    required_trait_id: str
    required_trait_name: str
    confidence: float
    matched_keywords: list[str] = field(default_factory=list)


@dataclass
class AssemblyStage:
    """One unit in a multi-stage assembly."""
    role: str  # "PROTECTOR" or "TARGET"
    product_family_id: str
    product_family_name: str
    provides_trait_id: str
    provides_trait_name: str
    reason: str


@dataclass
class GateEvaluation:
    """Result of evaluating a LogicGate — domain-agnostic."""
    gate_id: str
    gate_name: str
    stressor_id: str
    stressor_name: str
    physics_explanation: str
    state: str  # "FIRED" | "PASSED" | "VALIDATION_REQUIRED"
    missing_parameters: list[dict] = field(default_factory=list)
    # [{param_id, name, property_key, question, priority, unit}]
    condition_logic: str = ""


@dataclass
class ConstraintOverride:
    """Record of a hard constraint auto-override — property_key is graph-supplied."""
    item_id: str
    property_key: str       # graph-supplied string, not hardcoded
    original_value: Any
    corrected_value: Any
    operator: str
    error_msg: str


@dataclass
class MissingParameter:
    """An unresolved parameter that must be provided before configuration is final."""
    feature_id: str
    feature_name: str
    parameter_name: str      # graph-supplied key for context lookup
    question: str
    why_needed: str
    options: list[dict] = field(default_factory=list)  # discrete choices if applicable


@dataclass
class AccessoryValidation:
    """Result of validating an accessory against a product family."""
    accessory_code: str
    accessory_name: str
    product_family_id: str
    is_compatible: bool
    status: str  # "ALLOWED", "BLOCKED", "UNKNOWN"
    reason: Optional[str] = None
    compatible_alternatives: list[str] = field(default_factory=list)


@dataclass
class AlternativeProduct:
    """A product/material that satisfies a violated installation constraint."""
    product_family_id: str
    product_family_name: str
    why_it_works: str
    selection_priority: int = 50
    details: dict = field(default_factory=dict)


@dataclass
class InstallationViolation:
    """Result of checking an installation constraint against context."""
    constraint_id: str
    constraint_type: str  # COMPUTED_FORMULA, SET_MEMBERSHIP, CROSS_NODE_THRESHOLD
    severity: str  # CRITICAL, WARNING
    error_msg: str
    details: dict = field(default_factory=dict)  # {required, available, ...}
    alternatives: list = field(default_factory=list)  # list[AlternativeProduct]


# Operator map for generic constraint comparison
_OPS = {">=": op.ge, "<=": op.le, "==": op.eq, ">": op.gt, "<": op.lt, "!=": op.ne}


@dataclass
class EngineVerdict:
    """The complete output of the trait-based reasoning engine."""
    # Input analysis
    detected_stressors: list[DetectedStressor] = field(default_factory=list)
    active_causal_rules: list[CausalRule] = field(default_factory=list)

    # Product evaluation
    ranked_products: list[TraitMatch] = field(default_factory=list)
    vetoed_products: list[TraitMatch] = field(default_factory=list)
    recommended_product: Optional[TraitMatch] = None

    # Veto system
    has_veto: bool = False
    veto_reason: Optional[str] = None
    auto_pivot_to: Optional[str] = None
    auto_pivot_name: Optional[str] = None

    # Clarifications
    needs_clarification: bool = False
    clarification_questions: list[dict] = field(default_factory=list)

    # Reasoning trace for explainability
    reasoning_trace: list[dict] = field(default_factory=list)

    # Application context (for adapter compatibility)
    application_match: Optional[dict] = None

    # Assembly (multi-stage filtration sequence)
    assembly: Optional[list] = None  # list[AssemblyStage]
    is_assembly: bool = False
    assembly_rationale: Optional[str] = None

    # Detected functional goals
    detected_goals: list = field(default_factory=list)  # list[DetectedGoal]

    # v2.0: Logic gates, hard constraints, optimization, capacity
    gate_evaluations: list = field(default_factory=list)  # list[GateEvaluation]
    has_validation_required: bool = False
    constraint_overrides: list = field(default_factory=list)  # list[ConstraintOverride]
    optimization_applied: Optional[dict] = None  # {sort_property, sort_order, ...}
    capacity_calculation: Optional[dict] = None  # {input_value, output_rating, modules_needed, ...}
    capacity_alternatives: list = field(default_factory=list)  # list[AlternativeProduct] v3.4

    # v2.1: Missing parameters (variance check), accessory validation
    missing_parameters: list = field(default_factory=list)  # list[MissingParameter]
    accessory_validations: list = field(default_factory=list)  # list[AccessoryValidation]
    has_blocked_accessory: bool = False

    # v2.5: Sizing arrangement (graph-driven module selection)
    sizing_arrangement: Optional[dict] = None

    # v3.0: Installation constraints (service clearance, environment, material limits)
    installation_violations: list = field(default_factory=list)  # list[InstallationViolation]
    has_installation_block: bool = False

    def to_prompt_injection(self) -> str:
        """Format verdict as text for LLM context injection."""
        parts = []
        has_critical_violation = bool(
            self.installation_violations
            and any(iv.severity == "CRITICAL" for iv in self.installation_violations)
        )

        # v3.13: Detect "all products vetoed" (material/trait block without IC violations).
        # When ALL products are vetoed, asking for config params is counterproductive —
        # the user needs to change material or product family first.
        all_products_vetoed = bool(
            self.ranked_products
            and all(tm.vetoed for tm in self.ranked_products)
        )
        is_blocked = has_critical_violation or all_products_vetoed

        # ASSEMBLY SECTION (highest priority — multi-stage system)
        # v3.8: Suppress assembly when critical IC violations exist to avoid
        # self-contradiction (recommending a product that's also blocked).
        if self.is_assembly and self.assembly and not has_critical_violation:
            parts.append("## MULTI-STAGE FILTRATION ASSEMBLY (ENGINEERING SOLUTION)")
            parts.append("")
            parts.append(f"**RATIONALE:** {self.assembly_rationale or 'Protective pre-stage required'}")
            parts.append("")
            parts.append("**ASSEMBLY SEQUENCE (in airflow order):**")
            for i, stage in enumerate(self.assembly, 1):
                parts.append(f"  Stage {i} ({stage.role}): **{stage.product_family_name}**")
                parts.append(f"    - Provides: {stage.provides_trait_name}")
                parts.append(f"    - Reason: {stage.reason}")
            parts.append("")
            parts.append("THE SYSTEM HAS DESIGNED A MULTI-STAGE ASSEMBLY. You MUST:")
            parts.append("1. Present this as a **two-stage system** (or multi-stage if more)")
            parts.append("2. EXPLAIN WHY the protector stage is needed (physics reasoning)")
            parts.append("3. Use the SAME DIMENSIONS for all stages (user's duct size applies to all units)")
            parts.append("4. DO NOT suggest removing the target product — it fulfills the user's primary goal")
            parts.append("5. Ask for missing parameters (airflow, etc.) for ALL stages together")
            parts.append("")

        # VETO+PIVOT SECTION (only when assembly was NOT possible)
        # v3.8: Also suppress when critical IC violations exist
        elif self.has_veto and self.auto_pivot_name and not has_critical_violation:
            parts.append("## AUTOMATIC PRODUCT SUBSTITUTION (ENGINEERING OVERRIDE)")
            parts.append(f"**VETOED:** {self.veto_reason}")
            parts.append(f"**PIVOTED TO:** {self.auto_pivot_name}")
            parts.append("")
            parts.append("THE SYSTEM HAS ALREADY SWITCHED THE PRODUCT. You MUST:")
            parts.append("1. ACKNOWLEDGE the pivot — do NOT offer the vetoed product")
            parts.append("2. EXPLAIN WHY using physics/engineering reasoning")
            parts.append(f"3. PROCEED with questions about {self.auto_pivot_name}")
            parts.append("")

        # LOGIC GATE EVALUATIONS (v2.0)
        # v3.13: Suppress "MUST ask" instructions when blocked — config params
        # are irrelevant until material/product is resolved
        if self.gate_evaluations:
            parts.append("## LOGIC GATE EVALUATIONS")
            for ge in self.gate_evaluations:
                parts.append(f"- **{ge.gate_name}** [{ge.state}]: Monitors {ge.stressor_name}")
                if ge.state == "VALIDATION_REQUIRED":
                    if is_blocked:
                        parts.append(f"  (Deferred — resolve material/product block first)")
                    else:
                        missing_keys = [p.get("property_key", p.get("name", "?")) for p in ge.missing_parameters]
                        parts.append(f"  Missing data: {', '.join(missing_keys)}")
                        parts.append(f"  → You MUST ask for this data BEFORE making any recommendation.")
                        for p in ge.missing_parameters:
                            parts.append(f"    - {p.get('name', '')}: {p.get('question', '')}")
                elif ge.state == "FIRED":
                    parts.append(f"  Physics: {ge.physics_explanation}")
                    parts.append(f"  → CONFIRMED from context. You MUST explicitly name '{ge.stressor_name}' "
                                 f"in your response. State as fact, do NOT ask 'if' present. "
                                 f"Explain WHY using physics, then move to next missing parameter.")
            parts.append("")

        # HARD CONSTRAINT AUTO-OVERRIDES (v2.0)
        if self.constraint_overrides:
            parts.append("## HARD CONSTRAINT AUTO-OVERRIDES")
            for co in self.constraint_overrides:
                parts.append(
                    f"- **{co.property_key}**: {co.original_value} → {co.corrected_value} "
                    f"({co.operator} {co.corrected_value})"
                )
                parts.append(f"  Reason: {co.error_msg}")
                parts.append(f"  → Inform user of the correction. Do NOT allow override.")
            parts.append("")

        # INSTALLATION CONSTRAINT VIOLATIONS (v3.0)
        if self.installation_violations:
            critical = [iv for iv in self.installation_violations if iv.severity == "CRITICAL"]
            if critical:
                parts.append("## ⛔ INSTALLATION CONSTRAINT VIOLATIONS — BLOCKED")
                parts.append("")
                parts.append("THE FOLLOWING INSTALLATION CONSTRAINTS ARE VIOLATED:")
                for iv in critical:
                    parts.append(f"- **[{iv.constraint_type}]** {iv.error_msg}")
                    for dk, dv in iv.details.items():
                        parts.append(f"  - {dk}: {dv}")
                parts.append("")
                parts.append("You MUST inform the user that this configuration is BLOCKED.")
                parts.append("Explain the engineering/physics reason for the block.")
                parts.append("")

                # v3.3: Inject graph-backed alternatives (Sales Recovery)
                all_alts = []
                for iv in critical:
                    all_alts.extend(getattr(iv, 'alternatives', []))

                # v3.7: Defense-in-depth — strip same-product material swaps
                # when any violation is a product-level block (SET_MEMBERSHIP)
                has_product_block = any(
                    iv.constraint_type == "SET_MEMBERSHIP" for iv in critical
                )
                if has_product_block:
                    all_alts = [
                        a for a in all_alts
                        if not a.details.get("is_material_change")
                    ]

                if all_alts:
                    # Deduplicate by (product_family_id, material_code)
                    seen = set()
                    unique_alts = []
                    for alt in all_alts:
                        key = (alt.product_family_id, alt.details.get("material_code", ""))
                        if key not in seen:
                            seen.add(key)
                            unique_alts.append(alt)

                    parts.append("## VERIFIED ALTERNATIVES (from engineering database)")
                    parts.append("")
                    for i, alt in enumerate(unique_alts[:5], 1):
                        parts.append(f"  {i}. **{alt.product_family_name}**")
                        parts.append(f"     Reason: {alt.why_it_works}")
                    parts.append("")
                    parts.append("Present these verified alternatives to the user.")
                    parts.append("Explain WHY each alternative resolves the constraint using physics reasoning.")
                    parts.append("Recommend the first option (highest engineering priority) unless the user has specific requirements.")
                else:
                    # v3.8: Inject violation-derived requirements profile
                    # so the LLM can explain WHAT the customer needs, not just
                    # "no product found."  Zero domain words — data from graph.
                    parts.append("## NO STANDARD ALTERNATIVES — REQUIREMENTS PROFILE")
                    parts.append("")
                    parts.append("No standard catalog product satisfies all constraints simultaneously.")
                    parts.append("Unmet requirements (derived from violated constraints):")
                    parts.append("")
                    for iv in critical:
                        parts.append(f"- **[{iv.constraint_id}]** {iv.error_msg}")
                        for dk, dv in iv.details.items():
                            parts.append(f"    {dk}: {dv}")
                    parts.append("")
                    parts.append("Based on these constraint gaps, you MUST:")
                    parts.append("1. Explain what technical specifications a solution WOULD need (infer from the violated constraints above).")
                    parts.append("2. Explain why no standard catalog product currently satisfies all requirements simultaneously.")
                    parts.append("3. Recommend contacting the manufacturer's Custom Engineering or Technical Support team with these specific technical requirements.")

                # v3.9: Inject capacity overload as additional risk INSIDE the
                # violation block so the LLM treats it as part of the same
                # engineering assessment (not as downstream "configuration").
                if self.capacity_calculation:
                    cap = self.capacity_calculation
                    if cap.get("input_value", 0) > cap.get("output_rating", 0):
                        parts.append(f"- **[CAPACITY_OVERLOAD]** Requested "
                                     f"{cap['input_value']} {cap.get('input_requirement', '')} "
                                     f"exceeds maximum capacity of {cap['output_rating']} "
                                     f"for the selected unit size. "
                                     f"Modules needed: {cap.get('modules_needed')}.")
                        parts.append("")

                parts.append("")
                parts.append("You MUST report ALL the above risks to the user.")
                parts.append("DO NOT proceed with product configuration until constraints are resolved.")
                parts.append("DO NOT ask for airflow, dimensions, or any other configuration parameters.")
                parts.append("")

        # CAPACITY CALCULATION (v2.0 → v3.3 component-aware)
        if self.capacity_calculation:
            cap = self.capacity_calculation
            parts.append("## CAPACITY CALCULATION")
            if has_critical_violation:
                parts.append(
                    "(Note: Product has CRITICAL installation violations above. "
                    "Capacity data shown for completeness — present ALL engineering "
                    "risks together.)"
                )
            parts.append(
                f"- Input: {cap.get('input_value')} {cap.get('input_requirement', '')}"
            )
            # Component-aware: show component count and per-component rating
            if cap.get("component_count") and cap.get("capacity_per_component"):
                parts.append(
                    f"- Component count: {int(cap['component_count'])} units"
                )
                parts.append(
                    f"- Per-component rating: {cap['capacity_per_component']} "
                    f"{cap.get('input_requirement', '')}"
                )
                parts.append(
                    f"- Effective max capacity: {cap.get('output_rating')} "
                    f"({int(cap['component_count'])} x {cap['capacity_per_component']})"
                )
                if cap.get("input_value", 0) > cap.get("output_rating", 0):
                    parts.append(
                        f"- **CAPACITY EXCEEDED**: requested {cap['input_value']} "
                        f"> effective max {cap['output_rating']}. "
                        f"Suggest upgrading to a larger size with more components."
                    )
            else:
                parts.append(
                    f"- Rating per module: {cap.get('output_rating')} "
                    f"({cap.get('module_descriptor', '')})"
                )
                if cap.get("input_value", 0) > cap.get("output_rating", 0):
                    parts.append(
                        f"- **CAPACITY EXCEEDED**: requested {cap['input_value']} "
                        f"> single module max {cap['output_rating']}. "
                        f"A single unit at this size CANNOT handle the required load."
                    )
            parts.append(f"- Modules needed: {cap.get('modules_needed')}")
            if cap.get("assumption"):
                parts.append(f"- Assumption: {cap['assumption']}")
            # v3.9: When capacity is exceeded AND product is blocked, force LLM to mention both
            if has_critical_violation and cap.get("input_value", 0) > cap.get("output_rating", 0):
                parts.append(
                    f"⚠️ You MUST also inform the user that the requested {cap.get('input_value')} "
                    f"{cap.get('input_requirement', '')} EXCEEDS the maximum capacity of "
                    f"{cap.get('output_rating')} for the selected unit size. "
                    f"This is an ADDITIONAL engineering risk on top of the installation constraints above."
                )
            parts.append("")

        # v3.4: Capacity alternatives when modules_needed > 1
        if self.capacity_alternatives:
            parts.append("### CAPACITY ALTERNATIVES (from engineering database)")
            parts.append("The following products handle this requirement in fewer modules:")
            for i, alt in enumerate(self.capacity_alternatives[:3], 1):
                parts.append(f"  {i}. **{alt.product_family_name}**: {alt.why_it_works}")
            parts.append("")
            parts.append("Present these alternatives to the user alongside the multi-module option.")
            parts.append("The user may prefer a single-module solution over multiple parallel units.")
            parts.append("")

        # SIZING ARRANGEMENT (v2.5 → v2.8 with arrangement geometry)
        if self.sizing_arrangement:
            sa = self.sizing_arrangement
            parts.append("## MODULE SIZING ARRANGEMENT")
            parts.append(
                f"- Base module: {sa.get('selected_module_id')} "
                f"({sa.get('selected_module_width')}×{sa.get('selected_module_height')}mm)"
            )
            parts.append(
                f"- Airflow per module: {sa.get('reference_airflow_per_module')} m³/h"
            )
            parts.append(f"- Modules needed: {sa.get('modules_needed')}")
            if sa.get('primary_constrained') or sa.get('width_constrained'):
                h_count = sa.get('horizontal_count', 1)
                v_count = sa.get('vertical_count', 1)
                parts.append(
                    f"- **Width constraint: max {sa.get('max_primary_mm') or sa.get('max_width_mm')}mm** "
                    f"→ arrangement: {h_count} wide × {v_count} high"
                )
            if sa.get('secondary_constrained'):
                parts.append(
                    f"- **Height constraint: max {sa.get('max_secondary_mm')}mm**"
                )
            if sa.get('modules_needed', 1) > 1:
                parts.append(
                    f"- **PARALLEL UNITS REQUIRED: {sa['modules_needed']} units** "
                    f"(present as {sa['modules_needed']}x product code)"
                )
                # v3.9: Show single-module alternatives
                for alt in sa.get('single_module_alternatives', [])[:2]:
                    parts.append(
                        f"- **ALTERNATIVE: Single {alt['label']} module** "
                        f"(capacity {alt['reference_airflow_m3h']:.0f} m³/h — "
                        f"no parallel units needed)"
                    )
            eff_w = sa.get('effective_width', sa.get('selected_module_width'))
            eff_h = sa.get('effective_height', sa.get('selected_module_height'))
            parts.append(
                f"- **Effective housing dimensions: {eff_w}×{eff_h}mm** "
                f"(USE THESE for the product configuration)"
            )
            parts.append(
                f"- Total capacity: {sa.get('reference_airflow_per_module', 0) * sa.get('modules_needed', 1)} m³/h "
                f"(required: {sa.get('total_airflow_required')} m³/h)"
            )
            # v3.10: Oversizing warning in prompt
            ow = sa.get('oversizing_warning')
            if ow:
                parts.append(
                    f"- **⚠️ OVERSIZING WARNING: Module capacity {ow['module_capacity']:.0f} m³/h "
                    f"but only {ow['required_airflow']:.0f} m³/h required "
                    f"({ow['utilization_pct']:.0f}% utilization)**"
                )
                parts.append(
                    "  - This extreme oversizing causes low face velocity, "
                    "uneven air distribution, and reduced efficiency"
                )
                for sm_alt in ow.get('smaller_alternatives', [])[:2]:
                    parts.append(
                        f"  - **RECOMMEND: {sm_alt['label']} module** "
                        f"({sm_alt['reference_airflow_m3h']:.0f} m³/h — better matched)"
                    )
                parts.append(
                    "  - ALWAYS warn the user about oversizing and recommend a smaller module"
                )
            # Size-determined properties (auto-resolved from graph)
            dp = sa.get('determined_properties', {})
            if dp:
                parts.append("- **Auto-determined by selected size (ALWAYS mention these in your response):**")
                for k, v in dp.items():
                    if isinstance(v, dict):
                        display = v.get("display_name", k)
                        val = v.get("value")
                    else:
                        display = k
                        val = v
                    parts.append(f"  - {display}: {val} (DO NOT ask the user for this)")
            parts.append("")

        # DIMENSION ORIENTATION (prevents LLM confusion about vertical/horizontal)
        if self.sizing_arrangement:
            sa = self.sizing_arrangement
            mod_w = sa.get('selected_module_width')
            mod_h = sa.get('selected_module_height')
            if mod_w and mod_h:
                parts.append("## DIMENSION ORIENTATION (VERIFIED)")
                parts.append(f"- Width (horizontal): {mod_w} mm")
                parts.append(f"- Height (vertical): {mod_h} mm")
                parts.append("The LARGER value is always HEIGHT (vertical). DO NOT confuse with filter dimensions.")
                parts.append("")

        # MISSING PARAMETERS (variance check — v2.1)
        # Suppressed when product is blocked — asking for config params is counterproductive
        if self.missing_parameters and not is_blocked:
            parts.append("## MISSING CONFIGURATION PARAMETERS")
            parts.append("The following parameters MUST be resolved before final configuration:")
            for mp in self.missing_parameters:
                parts.append(f"- **{mp.feature_name}** (key: {mp.parameter_name})")
                parts.append(f"  Question: {mp.question}")
                if mp.options:
                    opt_names = [o.get("name", o.get("value", "")) for o in mp.options[:5]]
                    parts.append(f"  Options: {', '.join(opt_names)}")
            parts.append("")
            parts.append("You MUST ask for ALL missing parameters listed above.")
            parts.append("DO NOT assume or guess values — the user MUST provide them.")
            parts.append("")

        # ACCESSORY VALIDATION (v2.1)
        # Suppressed when product is blocked — accessory compat irrelevant
        blocked = [av for av in self.accessory_validations if not av.is_compatible]
        if blocked and not has_critical_violation:
            parts.append("## ACCESSORY COMPATIBILITY — BLOCKED COMBINATIONS")
            for av in blocked:
                parts.append(
                    f"- **{av.accessory_code}** ({av.accessory_name}): "
                    f"BLOCKED with {av.product_family_id}"
                )
                if av.reason:
                    parts.append(f"  Reason: {av.reason}")
                if av.compatible_alternatives:
                    parts.append(f"  Alternatives: {', '.join(av.compatible_alternatives)}")
            parts.append("")
            parts.append("You MUST inform the user that this accessory is NOT compatible.")
            parts.append("Explain WHY and suggest the listed alternatives.")
            parts.append("")

        # DETECTED STRESSORS
        if self.detected_stressors:
            parts.append("## DETECTED ENVIRONMENTAL STRESSORS")
            for s in self.detected_stressors:
                parts.append(f"- **{s.name}** (via {s.detection_method}, confidence: {s.confidence:.2f})")
                if s.source_context:
                    parts.append(f"  Source: {s.source_context}")
            parts.append("")
            parts.append("You MUST mention each detected stressor BY NAME in your response.")
            parts.append("Explain the engineering/physics impact of each stressor on the selected product.")
            parts.append("")

        # ACTIVE CAUSAL RULES
        # Filter out NEUTRALIZED_BY rules for traits the recommended product
        # doesn't have — injecting them confuses the LLM (e.g. carbon warnings
        # shown for a mechanical filter product).
        # Include both traits_present AND traits_neutralized so WARNING-level
        # neutralizations (e.g. humidity degrades carbon) appear in the prompt.
        product_traits = set()
        if self.recommended_product:
            product_traits = set(self.recommended_product.traits_present) | set(self.recommended_product.traits_neutralized)
        relevant_rules = [
            r for r in self.active_causal_rules
            if r.rule_type != "NEUTRALIZED_BY"
            or r.trait_name in product_traits
        ]
        critical_rules = [r for r in relevant_rules if r.severity == "CRITICAL"]
        warning_rules = [r for r in relevant_rules if r.severity == "WARNING"]
        info_rules = [r for r in relevant_rules if r.severity == "INFO"]

        if critical_rules or warning_rules:
            parts.append("## PHYSICS-BASED ENGINEERING RULES")
            for rule in critical_rules:
                parts.append(f"- [CRITICAL] {rule.explanation}")
                parts.append(f"  Stressor: {rule.stressor_name} | Required trait: {rule.trait_name}")
            for rule in warning_rules:
                parts.append(f"- [WARNING] {rule.explanation}")
                parts.append(f"  Stressor: {rule.stressor_name} | Relevant trait: {rule.trait_name}")
            parts.append("")

        # PRODUCT RANKING
        if self.ranked_products:
            parts.append("## PRODUCT SUITABILITY RANKING")
            for tm in self.ranked_products[:5]:
                if tm.vetoed:
                    reasons = "; ".join(tm.veto_reasons[:2])
                    parts.append(f"- **{tm.product_family_name}**: VETOED — {reasons}")
                else:
                    parts.append(f"- **{tm.product_family_name}**: Score {tm.coverage_score:.0%}")
                    if tm.traits_missing:
                        parts.append(f"  Missing: {', '.join(tm.traits_missing)}")
                    if tm.traits_neutralized:
                        parts.append(f"  Neutralized: {', '.join(tm.traits_neutralized)}")
            parts.append("")

        # v3.13: MATERIAL/PRODUCT BLOCK when all products vetoed for material reasons
        # (no IC violations = pure material/trait veto). Instruct LLM to focus on
        # material alternatives rather than asking configuration questions.
        # Actual material list is injected by the retriever (has DB access).
        if all_products_vetoed and not has_critical_violation:
            parts.append("## ⚡ CONFIGURATION BLOCKED — MATERIAL/PRODUCT CHANGE REQUIRED")
            parts.append("")
            parts.append("All available products are blocked for the current material/environment combination.")
            parts.append("DO NOT ask for configuration parameters (airflow, depth, length, etc.).")
            parts.append("DO NOT ask clarification questions.")
            parts.append("Instead, suggest specific material upgrades or alternative product families.")
            parts.append("If material alternatives are listed below, present them to the user.")
            parts.append("")

        # TECHNOLOGY GUIDANCE
        if info_rules:
            parts.append("## TECHNOLOGY GUIDANCE")
            for rule in info_rules:
                parts.append(f"- {rule.explanation}")
            parts.append("")

        # CLARIFICATIONS
        # Suppressed when product is blocked — playbook questions irrelevant
        if self.clarification_questions and not is_blocked:
            parts.append("## REQUIRED CLARIFICATIONS (from Playbook layer)")
            for q in self.clarification_questions:
                parts.append(f"- **{q.get('param_name', '')}** [{q.get('intent', '')}] (Priority {q.get('priority', 99)})")
                parts.append(f"  Question: {q.get('question_text', '')}")
                if q.get('triggered_by'):
                    parts.append(f"  Triggered by: {q['triggered_by']}")
            parts.append("")

        # MANDATORY RESPONSE REQUIREMENTS (summary checklist)
        # Recency bias: LLMs follow instructions at the end more reliably.
        mandatory = []
        if self.detected_stressors:
            stressor_names = [s.name for s in self.detected_stressors]
            mandatory.append(
                f"Name each detected stressor ({', '.join(stressor_names)}) "
                f"explicitly and explain its engineering impact"
            )
        if self.installation_violations:
            mandatory.append("State that the configuration is BLOCKED and explain why")
        if self.is_assembly and self.assembly:
            mandatory.append("Present the multi-stage assembly with all stages")
        if self.has_veto and self.auto_pivot_name:
            mandatory.append(f"Acknowledge the pivot to {self.auto_pivot_name}")
        fired_gates = [g for g in self.gate_evaluations if g.state == "FIRED"]
        if fired_gates:
            for g in fired_gates:
                mandatory.append(
                    f"Reference '{g.stressor_name}' by name as a confirmed risk"
                )

        if mandatory:
            parts.append("## MANDATORY RESPONSE REQUIREMENTS")
            parts.append("Your response MUST explicitly address EACH of the following:")
            for i, req in enumerate(mandatory, 1):
                parts.append(f"  {i}. {req}")
            parts.append("")
            parts.append("If ANY of these items is missing from your response, it is INCOMPLETE.")
            parts.append("")

        return "\n".join(parts)


# =============================================================================
# TRAIT-BASED ENGINE
# =============================================================================

class TraitBasedEngine:
    """
    Domain-agnostic trait-based reasoning engine.

    Evaluates product suitability by:
    1. Detecting environmental stressors from user query
    2. Loading causal rules from the graph
    3. Matching product traits against stressor demands
    4. Computing coverage scores and applying vetoes
    """

    def __init__(self, db):
        """
        Args:
            db: Neo4jConnection instance with trait-query methods
        """
        self.db = db

    # =========================================================================
    # STEP 1: DETECT STRESSORS
    # =========================================================================

    def detect_stressors(self, query: str, context: Optional[dict] = None) -> list[DetectedStressor]:
        """Detect environmental stressors from user query and Scribe-extracted context.

        Methods:
        1. Keyword matching against EnvironmentalStressor.keywords (Cypher)
        2. Application detection → EXPOSES_TO → Stressor
        3. Environment stressor lookup using Scribe-detected installation_environment
        4. Vector search semantic fallback (when 1-3 find nothing)
        """
        context = context or {}
        query_lower = query.lower()
        query_words = re.findall(r'\b\w+\b', query_lower)
        stressors_by_id: dict[str, DetectedStressor] = {}

        # Method 1: Direct keyword match on stressor nodes (Cypher-side matching)
        kw_results = self.db.get_stressors_by_keywords(query_words)
        for row in kw_results:
            sid = row["id"]
            if sid not in stressors_by_id:
                stressors_by_id[sid] = DetectedStressor(
                    id=sid,
                    name=row["name"],
                    description=row.get("description", ""),
                    detection_method="keyword",
                    confidence=min(0.7 + 0.1 * row.get("match_count", 1), 1.0),
                    matched_keywords=row.get("matched_keywords", []),
                )

        # Method 2: Application detection → EXPOSES_TO → Stressor
        applications = self.db.get_all_applications()
        detected_app = None
        for app in applications:
            app_keywords = [app.get("name", "").lower()] + [k.lower() for k in app.get("keywords", [])]
            for kw in app_keywords:
                if kw and kw in query_lower:
                    detected_app = app
                    break
            if detected_app:
                break

        if detected_app:
            app_stressors = self.db.get_stressors_for_application(detected_app["id"])
            for row in app_stressors:
                sid = row["id"]
                if sid not in stressors_by_id:
                    stressors_by_id[sid] = DetectedStressor(
                        id=sid,
                        name=row["name"],
                        description=row.get("description", ""),
                        detection_method="application_link",
                        confidence=0.9,
                        source_context=detected_app.get("name"),
                    )
                else:
                    # Boost confidence if found by both methods
                    stressors_by_id[sid].confidence = min(stressors_by_id[sid].confidence + 0.1, 1.0)
                    stressors_by_id[sid].source_context = detected_app.get("name")

        # Method 3: Environment stressor lookup using Scribe-detected environment.
        # The Scribe (LLM) extracts installation_environment into context — no keyword
        # matching needed. This avoids false positives from substring matching.
        inst_env = context.get("installation_environment")
        if inst_env:
            env_stressors = self.db.get_stressors_for_application(inst_env)
            for row in env_stressors:
                sid = row["id"]
                if sid not in stressors_by_id:
                    stressors_by_id[sid] = DetectedStressor(
                        id=sid,
                        name=row["name"],
                        description=row.get("description", ""),
                        detection_method="environment_link",
                        confidence=0.95,
                        source_context=row.get("source_context"),
                    )

        # Method 4: Vector search semantic fallback (when keyword/context detection found nothing)
        if not stressors_by_id:
            try:
                from embeddings import generate_embedding
                query_embedding = generate_embedding(query)
                vector_results = self.db.vector_search_applications(
                    query_embedding=query_embedding,
                    top_k=1,
                    min_score=0.80,
                )
                if vector_results:
                    best = vector_results[0]
                    app_id = best.get("id", "")
                    app_stressors = self.db.get_stressors_for_application(app_id)
                    for row in app_stressors:
                        sid = row["id"]
                        if sid not in stressors_by_id:
                            stressors_by_id[sid] = DetectedStressor(
                                id=sid,
                                name=row["name"],
                                description=row.get("description", ""),
                                detection_method="vector_search",
                                confidence=best.get("similarity_score", 0.80),
                                source_context=best.get("name"),
                            )
                    logger.info(
                        f"[TraitEngine] Vector search fallback matched: "
                        f"{best.get('name')} (score={best.get('similarity_score', 0):.3f})"
                    )
            except Exception as e:
                logger.debug(f"[TraitEngine] Vector search fallback unavailable: {e}")

        result = sorted(stressors_by_id.values(), key=lambda s: -s.confidence)
        logger.info(f"[TraitEngine] Detected {len(result)} stressors from query")
        return result

    # =========================================================================
    # STEP 2: GET CAUSAL RULES
    # =========================================================================

    def get_causal_rules(self, stressors: list[DetectedStressor]) -> list[CausalRule]:
        """Retrieve all causal rules for detected stressors."""
        if not stressors:
            return []

        stressor_ids = [s.id for s in stressors]
        raw_rules = self.db.get_causal_rules_for_stressors(stressor_ids)

        rules = []
        for row in raw_rules:
            rules.append(CausalRule(
                rule_type=row["rule_type"],
                stressor_id=row["stressor_id"],
                stressor_name=row["stressor_name"],
                trait_id=row["trait_id"],
                trait_name=row["trait_name"],
                severity=row.get("severity", "INFO") or "INFO",
                explanation=row.get("explanation", ""),
            ))

        logger.info(f"[TraitEngine] Loaded {len(rules)} causal rules for {len(stressor_ids)} stressors")
        return rules

    # =========================================================================
    # STEP 3: GET CANDIDATE PRODUCTS
    # =========================================================================

    def get_candidate_products(
        self,
        query: str,
        product_hint: Optional[str] = None
    ) -> list[dict]:
        """Get product families with their trait sets.

        If product_hint is given, returns only that family.
        Otherwise, returns all families.

        Returns list of dicts with:
            product_id, product_name, product_type,
            direct_trait_ids, material_trait_ids, all_trait_ids
        """
        if product_hint:
            traits = self.db.get_product_traits(product_hint)
            if traits:
                pf_id = product_hint if product_hint.startswith("FAM_") else f"FAM_{product_hint.upper()}"
                direct = [t for t in traits if t["source"] == "direct"]
                material = [t for t in traits if t["source"] != "direct"]
                all_ids = list(set(t["id"] for t in traits))
                return [{
                    "product_id": pf_id,
                    "product_name": f"{product_hint.upper()} family",
                    "product_type": None,
                    "direct_trait_ids": [t["id"] for t in direct],
                    "direct_trait_names": [t["name"] for t in direct],
                    "material_trait_ids": [t["id"] for t in material],
                    "material_trait_names": [t["name"] for t in material],
                    "all_trait_ids": all_ids,
                }]

        # Get all families
        all_families = self.db.get_all_product_families_with_traits()
        logger.info(f"[TraitEngine] Loaded {len(all_families)} product families with traits")
        return all_families

    # =========================================================================
    # STEP 4: MATCH TRAITS TO PRODUCTS
    # =========================================================================

    def match_traits(
        self,
        rules: list[CausalRule],
        candidates: list[dict],
        stressors: list[DetectedStressor]
    ) -> list[TraitMatch]:
        """Compute trait coverage for each candidate product.

        For each product:
        - Check DEMANDS_TRAIT rules: does the product have the demanded trait?
        - Check NEUTRALIZED_BY rules: are any of the product's traits neutralized?
        - Compute coverage_score = (demanded met and not neutralized) / (total demanded)
        """
        # Collect demanded traits (from DEMANDS_TRAIT rules)
        demanded_traits: dict[str, CausalRule] = {}
        for rule in rules:
            if rule.rule_type == "DEMANDS_TRAIT":
                # Keep the most severe rule per trait
                if rule.trait_id not in demanded_traits or \
                   _severity_rank(rule.severity) > _severity_rank(demanded_traits[rule.trait_id].severity):
                    demanded_traits[rule.trait_id] = rule

        # Collect neutralized traits (from NEUTRALIZED_BY rules)
        stressor_ids = {s.id for s in stressors}
        neutralization_map: dict[str, CausalRule] = {}  # trait_id -> rule
        for rule in rules:
            if rule.rule_type == "NEUTRALIZED_BY" and rule.stressor_id in stressor_ids:
                if rule.trait_id not in neutralization_map or \
                   _severity_rank(rule.severity) > _severity_rank(neutralization_map[rule.trait_id].severity):
                    neutralization_map[rule.trait_id] = rule

        matches = []
        for candidate in candidates:
            product_trait_ids = set(candidate.get("all_trait_ids") or [])
            # Remove None values
            product_trait_ids.discard(None)

            traits_present = []
            traits_missing = []
            traits_neutralized = []

            # Check demanded traits
            for trait_id, rule in demanded_traits.items():
                if trait_id in product_trait_ids:
                    # Product has the trait — but is it neutralized?
                    if trait_id in neutralization_map:
                        traits_neutralized.append(rule.trait_name)
                    else:
                        traits_present.append(rule.trait_name)
                else:
                    traits_missing.append(rule.trait_name)

            # Also check if any of the product's PRIMARY traits are neutralized
            for trait_id, neut_rule in neutralization_map.items():
                if trait_id in product_trait_ids and neut_rule.trait_name not in traits_neutralized:
                    traits_neutralized.append(neut_rule.trait_name)

            # Compute coverage score
            total_demanded = len(demanded_traits)
            if total_demanded > 0:
                met_and_active = len(traits_present)
                coverage = met_and_active / total_demanded
            else:
                coverage = 1.0  # No demands = no constraints = everything fits

            matches.append(TraitMatch(
                product_family_id=candidate.get("product_id", ""),
                product_family_name=candidate.get("product_name", ""),
                product_type=candidate.get("product_type"),
                traits_present=traits_present,
                traits_missing=traits_missing,
                traits_neutralized=traits_neutralized,
                coverage_score=coverage,
                selection_priority=candidate.get("selection_priority") or 50,
            ))

        # Sort by coverage score DESC, then by graph-driven selection_priority ASC
        # This ensures GDC (priority 20) beats GDC-FLEX (priority 22) at equal coverage
        matches.sort(key=lambda m: (-m.coverage_score, m.selection_priority))
        return matches

    # =========================================================================
    # STEP 5: CHECK VETOES
    # =========================================================================

    def check_vetoes(
        self,
        matches: list[TraitMatch],
        rules: list[CausalRule]
    ) -> list[TraitMatch]:
        """Apply Engineering Veto for CRITICAL-severity rule violations.

        A product is vetoed if:
        - A CRITICAL DEMANDS_TRAIT is missing
        - A CRITICAL NEUTRALIZED_BY applies to its primary trait
        """
        critical_demands = {
            rule.trait_id: rule for rule in rules
            if rule.rule_type == "DEMANDS_TRAIT" and rule.severity == "CRITICAL"
        }
        critical_neutralizations = {
            rule.trait_id: rule for rule in rules
            if rule.rule_type == "NEUTRALIZED_BY" and rule.severity == "CRITICAL"
        }

        for match in matches:
            product_trait_ids = set()
            # Reconstruct trait IDs from names (reverse lookup via demanded traits)
            for trait_id, rule in critical_demands.items():
                if rule.trait_name in match.traits_missing:
                    match.vetoed = True
                    match.veto_reasons.append(
                        rule.explanation or f"{rule.stressor_name} requires {rule.trait_name}"
                    )

            for trait_id, rule in critical_neutralizations.items():
                if rule.trait_name in match.traits_neutralized:
                    match.vetoed = True
                    match.veto_reasons.append(
                        rule.explanation or f"{rule.trait_name} ineffective under {rule.stressor_name}"
                    )

        return matches

    # =========================================================================
    # STEP 5a: DETECT FUNCTIONAL GOALS
    # =========================================================================

    def detect_goals(self, query: str) -> list[DetectedGoal]:
        """Detect functional goals from user query via FunctionalGoal keywords."""
        query_lower = query.lower()
        query_words = re.findall(r'\b\w+\b', query_lower)

        goals = []
        try:
            raw = self.db.get_goals_by_keywords(query_words)
            for row in raw:
                goals.append(DetectedGoal(
                    id=row["id"],
                    name=row["name"],
                    description=row.get("description", ""),
                    required_trait_id=row["required_trait_id"],
                    required_trait_name=row["required_trait_name"],
                    confidence=min(0.7 + 0.1 * row.get("match_count", 1), 1.0),
                    matched_keywords=row.get("matched_keywords", []),
                ))
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to detect goals: {e}")

        logger.info(f"[TraitEngine] Detected {len(goals)} functional goals: {[g.name for g in goals]}")
        return goals

    # =========================================================================
    # STEP 5b: EVALUATE LOGIC GATES
    # =========================================================================

    def evaluate_logic_gates(
        self,
        stressors: list[DetectedStressor],
        context: dict,
    ) -> list[GateEvaluation]:
        """Evaluate LogicGate nodes for detected stressors.

        For each gate monitoring a detected stressor:
        - Check context.get(param["property_key"]) for each REQUIRES_DATA param
        - Missing data → VALIDATION_REQUIRED (ask user)
        - All data present → FIRED (conservative default)

        All property names come from graph — this method is domain-agnostic.
        """
        if not stressors:
            return []

        # Filter out vector_search stressors — too speculative for gate triggering.
        # Consistent with Step 1b boolean auto-resolution which already excludes vector_search.
        gate_stressors = [
            s for s in stressors
            if s.detection_method != "vector_search"
        ]
        if not gate_stressors:
            return []

        stressor_ids = [s.id for s in gate_stressors]
        try:
            raw_gates = self.db.get_logic_gates_for_stressors(stressor_ids)
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to query logic gates: {e}")
            return []

        evaluations = []
        for gate_data in raw_gates:
            params = gate_data.get("params") or []
            # Filter out null params (from OPTIONAL MATCH when gate has no parameters)
            params = [p for p in params if p.get("param_id") is not None]

            missing = []
            for param in params:
                key = param.get("property_key", "")
                if key and context.get(key) is None:
                    missing.append(param)

            if missing:
                state = "VALIDATION_REQUIRED"
            else:
                # All data present — conservative: gate fires (stressor confirmed)
                state = "FIRED"

            evaluations.append(GateEvaluation(
                gate_id=gate_data["gate_id"],
                gate_name=gate_data["gate_name"],
                stressor_id=gate_data["stressor_id"],
                stressor_name=gate_data["stressor_name"],
                physics_explanation=gate_data.get("physics_explanation", ""),
                state=state,
                missing_parameters=missing,
                condition_logic=gate_data.get("condition_logic", ""),
            ))

        logger.info(
            f"[TraitEngine] Evaluated {len(evaluations)} gates: "
            f"{sum(1 for e in evaluations if e.state == 'FIRED')} FIRED, "
            f"{sum(1 for e in evaluations if e.state == 'VALIDATION_REQUIRED')} VALIDATION_REQUIRED"
        )
        return evaluations

    # =========================================================================
    # STEP 5c: CHECK HARD CONSTRAINTS
    # =========================================================================

    def check_hard_constraints(
        self,
        item_id: str,
        context: dict,
    ) -> list[ConstraintOverride]:
        """Check HardConstraint nodes for a product family and auto-override violations.

        Reads constraint property_key, operator, and threshold from graph.
        Uses Python operator module for fully generic comparison.
        Type-safe: casts both sides to float before comparison.
        """
        if not item_id:
            return []

        try:
            constraints = self.db.get_hard_constraints(item_id)
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to query hard constraints: {e}")
            return []

        overrides = []
        for constraint in constraints:
            key = constraint.get("property_key", "")
            current_value = context.get(key)
            if current_value is None:
                continue  # No data to validate — skip (will be asked via clarifications)

            threshold = constraint.get("value")
            operator_str = constraint.get("operator", ">=")

            try:
                current_float = float(current_value)
                threshold_float = float(threshold)
            except (ValueError, TypeError):
                logger.warning(
                    f"[TraitEngine] Cannot cast constraint values to float: "
                    f"{key}={current_value}, threshold={threshold}"
                )
                continue

            comparator = _OPS.get(operator_str)
            if comparator is None:
                logger.warning(f"[TraitEngine] Unknown operator '{operator_str}' in constraint")
                continue

            if not comparator(current_float, threshold_float):
                # Violation detected — auto-override
                context[key] = threshold_float  # Mutate context in-place
                overrides.append(ConstraintOverride(
                    item_id=item_id,
                    property_key=key,
                    original_value=current_float,
                    corrected_value=threshold_float,
                    operator=operator_str,
                    error_msg=constraint.get("error_msg", ""),
                ))
                logger.info(
                    f"[TraitEngine] Hard constraint override: {key} "
                    f"{current_float} → {threshold_float} ({operator_str})"
                )

        return overrides

    # =========================================================================
    # STEP 5e2: CHECK INSTALLATION CONSTRAINTS
    # =========================================================================

    def check_installation_constraints(
        self,
        item_id: str,
        context: dict,
        required_trait_ids: list[str] | None = None,
    ) -> list[InstallationViolation]:
        """Check InstallationConstraint nodes for a product family.

        Dispatches by constraint_type:
        - COMPUTED_FORMULA: required = dim × (1 + factor), check vs available
        - SET_MEMBERSHIP: check input_value IN allowed_list
        - CROSS_NODE_THRESHOLD: query cross-node property, check threshold
        """
        if not item_id:
            return []

        try:
            constraints = self.db.get_installation_constraints(item_id)
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to query installation constraints: {e}")
            return []

        violations = []
        for ic in constraints:
            ctype = ic.get("constraint_type", "")
            severity = ic.get("severity", "CRITICAL")
            error_tpl = ic.get("error_msg", "Installation constraint violated")

            if ctype == "COMPUTED_FORMULA":
                violation = self._eval_computed_formula(ic, context, severity, error_tpl)
            elif ctype == "SET_MEMBERSHIP":
                violation = self._eval_set_membership(ic, context, severity, error_tpl)
            elif ctype == "CROSS_NODE_THRESHOLD":
                violation = self._eval_cross_node_threshold(ic, context, item_id, severity, error_tpl)
            else:
                logger.warning(f"[TraitEngine] Unknown installation constraint type: {ctype}")
                continue

            if violation:
                violations.append(violation)

        # v3.3: Populate alternatives for each violation (Sales Recovery)
        # v3.5: Pass required_trait_ids so alternatives are trait-qualified
        for v in violations:
            v.alternatives = self.find_alternatives_for_violation(
                v, context, item_id, required_trait_ids=required_trait_ids
            )

        # v3.7: Cross-violation dedup — if the product itself is blocked by an
        # environment constraint (SET_MEMBERSHIP), remove "same-product material swap"
        # alternatives from other violations. E.g., "GDB in SF" is invalid when
        # GDB fails ENV_HOSPITAL whitelist — a material change doesn't fix env block.
        if len(violations) > 1:
            product_blocked = any(
                v.constraint_type == "SET_MEMBERSHIP" for v in violations
            )
            if product_blocked:
                for v in violations:
                    if v.constraint_type != "SET_MEMBERSHIP":
                        before = len(v.alternatives)
                        v.alternatives = [
                            a for a in v.alternatives
                            if not a.details.get("is_material_change")
                        ]
                        if len(v.alternatives) < before:
                            logger.info(
                                f"[TraitEngine] Cross-violation dedup: removed "
                                f"{before - len(v.alternatives)} same-product "
                                f"material swap(s) (product is env-blocked)"
                            )

        if violations:
            alt_count = sum(len(v.alternatives) for v in violations)
            logger.info(
                f"[TraitEngine] Installation violations for {item_id}: "
                f"{len(violations)} ({', '.join(v.constraint_id for v in violations)})"
                f" — {alt_count} alternative(s) found"
            )
        return violations

    def _eval_computed_formula(
        self, ic: dict, context: dict, severity: str, error_tpl: str
    ) -> Optional[InstallationViolation]:
        """COMPUTED_FORMULA: required = dimension × (1 + factor), check required <= available."""
        dim_key = ic.get("dimension_key", "")  # e.g. "width"
        factor_prop = ic.get("factor_property", "")  # e.g. "service_access_factor"
        comparison_key = ic.get("comparison_key", "")  # e.g. "available_space_mm"
        operator_str = ic.get("operator", "<=")

        dim_value = context.get(dim_key)
        available = context.get(comparison_key)
        factor = ic.get(factor_prop)  # from ProductFamily properties returned by query

        if dim_value is None or available is None or factor is None:
            return None  # Insufficient data — skip

        try:
            dim_float = float(dim_value)
            available_float = float(available)
            factor_float = float(factor)
        except (ValueError, TypeError):
            return None

        required = dim_float * (1.0 + factor_float)

        comparator = _OPS.get(operator_str)
        if comparator is None:
            return None

        if not comparator(required, available_float):
            service_warning = ic.get("service_warning", "")
            msg = error_tpl.format(
                required=int(required),
                available=int(available_float),
                service_warning=service_warning,
            )
            return InstallationViolation(
                constraint_id=ic.get("id", ""),
                constraint_type="COMPUTED_FORMULA",
                severity=severity,
                error_msg=msg,
                details={
                    "dimension": dim_key,
                    "dimension_value": dim_float,
                    "factor": factor_float,
                    "required_space": required,
                    "available_space": available_float,
                },
            )
        return None

    def _eval_set_membership(
        self, ic: dict, context: dict, severity: str, error_tpl: str
    ) -> Optional[InstallationViolation]:
        """SET_MEMBERSHIP: check input_value IN allowed_list.

        v3.6: Supports IS_A hierarchy — checks input_value AND all parent
        values (from {input_key}_chain) against the allowed list.
        E.g., ENV_KITCHEN chain [ENV_KITCHEN, ENV_INDOOR] → if product allows
        ENV_INDOOR, kitchen also passes.
        """
        input_key = ic.get("input_key", "")  # e.g. "installation_environment"
        list_prop = ic.get("list_property", "")  # e.g. "allowed_environments"

        input_value = context.get(input_key)
        allowed_list = ic.get(list_prop) if list_prop else None  # from ProductFamily properties
        if allowed_list is None:
            allowed_list = ic.get("valid_set")  # self-contained list on IC node

        if input_value is None or allowed_list is None:
            if input_value is None:
                logger.warning(f"[IC] SET_MEMBERSHIP skipped: '{input_key}' not in context ({ic.get('id', '?')})")
            if allowed_list is None:
                logger.warning(f"[IC] SET_MEMBERSHIP skipped: '{list_prop}' not on product ({ic.get('id', '?')})")
            return None  # No data — skip

        if isinstance(allowed_list, str):
            allowed_list = [s.strip() for s in allowed_list.split(",")]

        # Numeric coercion: if valid_set contains numbers, compare as numbers
        if allowed_list and isinstance(allowed_list[0], (int, float)):
            try:
                input_value = type(allowed_list[0])(input_value)
            except (ValueError, TypeError):
                pass

        # v3.6: Check IS_A hierarchy chain if available
        chain_key = f"{input_key}_chain"
        value_chain = context.get(chain_key, [input_value])

        if any(v in allowed_list for v in value_chain):
            return None  # Constraint satisfied (self or parent matches)

        msg = error_tpl.format(
            input_value=input_value,
            allowed_list=", ".join(str(v) for v in allowed_list),
            construction_type=ic.get("construction_type", "standard"),
        )
        return InstallationViolation(
            constraint_id=ic.get("id", ""),
            constraint_type="SET_MEMBERSHIP",
            severity=severity,
            error_msg=msg,
            details={
                "input_key": input_key,
                "input_value": input_value,
                "allowed_values": allowed_list,
                "construction_type": ic.get("construction_type"),
            },
        )

    def _eval_cross_node_threshold(
        self, ic: dict, context: dict, item_id: str, severity: str, error_tpl: str
    ) -> Optional[InstallationViolation]:
        """CROSS_NODE_THRESHOLD: query related-node property, check threshold >= input.

        Two lookup paths (dispatched by IC properties):
        1. Legacy material path: material_context_key → get_material_property()
        2. Generic related-node path: context_match_key → get_related_node_property()
        """
        input_key = ic.get("input_key", "")
        cross_prop = ic.get("cross_property", "")
        operator_str = ic.get("operator", ">=")

        input_value = context.get(input_key)
        if input_value is None:
            return None

        try:
            input_float = float(input_value)
        except (ValueError, TypeError):
            return None

        # ── Branch: generic related-node lookup vs legacy material lookup ──
        context_match_key = ic.get("context_match_key")
        context_match_value = None

        if context_match_key:
            # Generic path: look up property on a related node (e.g. VariantLength)
            context_match_value = context.get(context_match_key)
            if context_match_value is None:
                return None
            rel_type = ic.get("cross_rel_type", "")
            match_prop = ic.get("cross_node_match_property", "")
            if not rel_type or not match_prop:
                return None
            try:
                threshold = self.db.get_related_node_property(
                    item_id, rel_type, match_prop, int(context_match_value), cross_prop
                )
            except Exception as e:
                logger.warning(f"[TraitEngine] Related node property lookup failed: {e}")
                return None
        else:
            # Legacy path: material threshold (e.g. IC_MATERIAL_CHLORINE)
            material_key = ic.get("material_context_key", "")
            material_code = context.get(material_key)
            if material_code is None:
                return None
            try:
                threshold = self.db.get_material_property(item_id, material_code, cross_prop)
            except Exception as e:
                logger.warning(f"[TraitEngine] Failed to query material property: {e}")
                return None

        if threshold is None:
            return None

        try:
            threshold_float = float(threshold)
        except (ValueError, TypeError):
            return None

        comparator = _OPS.get(operator_str)
        if comparator is None:
            return None

        if not comparator(threshold_float, input_float):
            # Build details based on which branch we took
            if context_match_key:
                # Include compatible variants for the LLM to suggest
                compatible = []
                try:
                    compatible = self.db.find_compatible_variants(
                        item_id,
                        ic.get("cross_rel_type", ""),
                        ic.get("cross_node_match_property", ""),
                        cross_prop,
                        input_float,
                    )
                except Exception:
                    pass

                msg = error_tpl.format(
                    threshold=int(threshold_float),
                    input_value=int(input_float),
                    context_match_value=int(context_match_value),
                )
                details = {
                    "input_key": input_key,
                    "input_value": input_float,
                    "context_match_key": context_match_key,
                    "context_match_value": context_match_value,
                    "threshold": threshold_float,
                    "cross_property": cross_prop,
                    "compatible_variants": compatible,
                    "is_variant_constraint": True,
                }
            else:
                msg = error_tpl.format(
                    threshold=int(threshold_float),
                    input_value=int(input_float),
                )
                details = {
                    "material": context.get(ic.get("material_context_key", "")),
                    "material_threshold": threshold_float,
                    "environment_load": input_float,
                    "cross_property": cross_prop,
                }

            return InstallationViolation(
                constraint_id=ic.get("id", ""),
                constraint_type="CROSS_NODE_THRESHOLD",
                severity=severity,
                error_msg=msg,
                details=details,
            )
        return None

    # =========================================================================
    # STEP 5e3: FIND ALTERNATIVES FOR INSTALLATION VIOLATIONS (v3.3)
    # =========================================================================

    def find_alternatives_for_violation(
        self,
        violation: InstallationViolation,
        context: dict,
        blocked_pf_id: str,
        required_trait_ids: list[str] | None = None,
    ) -> list:
        """Find graph-backed alternatives for a single installation violation.

        Dispatches by constraint_type. Returns up to 3 alternatives ordered by
        selection_priority (lower = preferred). Graceful degradation on failure.

        v3.5: required_trait_ids filters alternatives to only those with the
        stressor-demanded traits (APPLICATION-CRITICAL).
        """
        alternatives = []

        try:
            if violation.constraint_type == "COMPUTED_FORMULA":
                alternatives = self._find_space_alternatives(
                    violation, context, blocked_pf_id, required_trait_ids
                )
            elif violation.constraint_type == "SET_MEMBERSHIP":
                # v3.5b: Environment alternatives are NOT trait-filtered.
                # Environment constraint = "where can this product be installed?"
                # Functional traits are a separate concern (handled by assembly).
                alternatives = self._find_environment_alternatives(
                    violation, context, blocked_pf_id, required_trait_ids=None
                )
            elif violation.constraint_type == "CROSS_NODE_THRESHOLD":
                alternatives = self._find_threshold_alternatives(
                    violation, context, blocked_pf_id, required_trait_ids
                )
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to find alternatives for {violation.constraint_id}: {e}")

        # v3.5c: Spatial validation of alternatives (Tetris Logic)
        # Before returning, batch-check if alternatives physically fit
        # within the user's spatial + airflow constraints.
        # Done via single Cypher query — no Python spatial math.
        airflow = context.get("airflow_m3h") or context.get("airflow")
        has_spatial = context.get("max_width_mm") or context.get("max_height_mm")

        if airflow and has_spatial and alternatives:
            candidate_ids = [
                a.product_family_id for a in alternatives
                if not a.details.get("is_material_change")
            ]

            if candidate_ids:
                try:
                    feasible = self.db.validate_spatial_feasibility(
                        pf_ids=candidate_ids,
                        airflow=float(airflow),
                        max_width=int(context.get("max_width_mm", 0)),
                        max_height=int(context.get("max_height_mm", 0)),
                        explicit_width=int(context.get("width", 0)),
                        explicit_height=int(context.get("height", 0)),
                    )
                    feasible_ids = {r["product_family_id"] for r in feasible}
                    sizing_map = {r["product_family_id"]: r for r in feasible}

                    validated = []
                    for a in alternatives:
                        if a.details.get("is_material_change"):
                            validated.append(a)
                        elif a.product_family_id in feasible_ids:
                            s = sizing_map[a.product_family_id]
                            a.details["sizing"] = {
                                "modules_needed": s["modules_needed"],
                                "module_width": s["module_width"],
                                "module_height": s["module_height"],
                                "airflow_per_module": s["airflow_per_module"],
                            }
                            validated.append(a)
                        else:
                            logger.info(
                                f"[TraitEngine] Alternative {a.product_family_id} "
                                f"fails spatial feasibility. Removed."
                            )
                    alternatives = validated
                except Exception as e:
                    logger.warning(f"[TraitEngine] Spatial validation failed: {e}")

        return alternatives[:3]

    def _find_space_alternatives(
        self,
        violation: InstallationViolation,
        context: dict,
        blocked_pf_id: str,
        required_trait_ids: list[str] | None = None,
    ) -> list:
        """COMPUTED_FORMULA: find products with smaller service clearance requirement."""
        dim_value = violation.details.get("dimension_value")
        available = violation.details.get("available_space")
        dim_key = violation.details.get("dimension", "width")

        if dim_value is None or available is None:
            return []

        rows = self.db.find_alternatives_for_space_constraint(
            blocked_pf_id=blocked_pf_id,
            dimension_key=dim_key,
            available_space=available,
            dim_value=dim_value,
            required_trait_ids=required_trait_ids,
        )

        results = []
        for row in rows:
            results.append(AlternativeProduct(
                product_family_id=row["product_id"],
                product_family_name=row["product_name"],
                selection_priority=row.get("selection_priority", 50),
                why_it_works=(
                    f"Requires {int(row['required_space_mm'])}mm "
                    f"({row.get('service_access_type', 'service access')}), "
                    f"fits within {int(available)}mm available"
                ),
                details={
                    "required_space_mm": row["required_space_mm"],
                    "service_access_factor": row.get("service_access_factor"),
                    "service_access_type": row.get("service_access_type"),
                },
            ))
        return results

    def _find_environment_alternatives(
        self,
        violation: InstallationViolation,
        context: dict,
        blocked_pf_id: str,
        required_trait_ids: list[str] | None = None,
    ) -> list:
        """SET_MEMBERSHIP: find products that allow the required environment.

        v3.6: Uses IS_A env chain — if user needs ENV_KITCHEN and kitchen IS_A indoor,
        products rated for ENV_INDOOR also qualify as alternatives.
        """
        required_env = violation.details.get("input_value")
        if not required_env:
            return []

        # v3.6: Pass full IS_A chain for hierarchy-aware matching
        env_chain = context.get("installation_environment_chain", [required_env])

        rows = self.db.find_alternatives_for_environment_constraint(
            blocked_pf_id=blocked_pf_id,
            required_environments=env_chain,
            required_trait_ids=required_trait_ids,
        )

        results = []
        for row in rows:
            results.append(AlternativeProduct(
                product_family_id=row["product_id"],
                product_family_name=row["product_name"],
                selection_priority=row.get("selection_priority", 50),
                why_it_works=f"Approved for {required_env} environment",
                details={
                    "allowed_environments": row.get("allowed_environments", ""),
                },
            ))
        return results

    def _find_threshold_alternatives(
        self,
        violation: InstallationViolation,
        context: dict,
        blocked_pf_id: str,
        required_trait_ids: list[str] | None = None,
    ) -> list:
        """CROSS_NODE_THRESHOLD: two-pronged search for material alternatives.

        Prong 1: Same product, different material (cheapest fix).
        Prong 2: Other product families with qualifying materials.

        For variant constraints (is_variant_constraint=True), compatible
        variants are already in violation.details — no product alternatives needed.
        """
        if violation.details.get("is_variant_constraint"):
            # v3.8: Convert compatible variants into AlternativeProduct objects
            # so the LLM receives concrete suggestions (e.g. "use GDB-750 instead")
            compatible = violation.details.get("compatible_variants", [])
            if not compatible:
                return []
            results = []
            pf_name = blocked_pf_id.replace("FAM_", "")
            for cv in compatible:
                variant_value = cv.get("variant_value")
                threshold = cv.get("threshold")
                if variant_value is None or threshold is None:
                    continue
                results.append(AlternativeProduct(
                    product_family_id=blocked_pf_id,
                    product_family_name=f"{pf_name}-{int(variant_value)}",
                    selection_priority=0,
                    why_it_works=(
                        f"The {int(variant_value)}mm variant accommodates "
                        f"up to {int(threshold)}mm "
                        f"(requested: {int(violation.details.get('input_value', 0))}mm)"
                    ),
                    details={
                        "is_variant_change": True,
                        "variant_value": int(variant_value),
                    },
                ))
            return results

        cross_prop = violation.details.get("cross_property", "")
        env_load = violation.details.get("environment_load")

        if not cross_prop or env_load is None:
            return []

        results = []

        # Prong 1: Same product, different material (no trait filter — same product)
        same_rows = self.db.find_material_alternatives_for_threshold(
            pf_id=blocked_pf_id,
            cross_property=cross_prop,
            required_value=env_load,
        )
        for row in same_rows[:2]:
            pf_name = blocked_pf_id.replace("FAM_", "")
            results.append(AlternativeProduct(
                product_family_id=blocked_pf_id,
                product_family_name=f"{pf_name} in {row['material_code']}",
                selection_priority=0,  # Same product = highest priority
                why_it_works=(
                    f"Material {row['material_name']} has "
                    f"{cross_prop} = {row['threshold_value']} "
                    f"(>= {int(env_load)} required)"
                ),
                details={
                    "material_code": row["material_code"],
                    "material_name": row["material_name"],
                    "threshold_value": row["threshold_value"],
                    "is_material_change": True,
                },
            ))

        # Prong 2: Other product families with qualifying materials
        # v3.5: Trait-qualified — only return products with demanded traits
        other_rows = self.db.find_other_products_for_material_threshold(
            blocked_pf_id=blocked_pf_id,
            cross_property=cross_prop,
            required_value=env_load,
            required_trait_ids=required_trait_ids,
        )
        for row in other_rows[:2]:
            mat_list = row.get("qualifying_materials", [])
            mat_summary = ", ".join(m["code"] for m in mat_list[:3])
            results.append(AlternativeProduct(
                product_family_id=row["product_id"],
                product_family_name=row["product_name"],
                selection_priority=row.get("selection_priority", 50),
                why_it_works=(
                    f"Available in materials meeting {cross_prop} >= {int(env_load)}: {mat_summary}"
                ),
                details={
                    "qualifying_materials": [m["code"] for m in mat_list],
                },
            ))

        # Sort combined results by priority
        results.sort(key=lambda a: a.selection_priority)
        return results

    # =========================================================================
    # STEP 5d: CALCULATE CAPACITY
    # =========================================================================

    def calculate_capacity(
        self,
        item_id: str,
        context: dict,
    ) -> Optional[dict]:
        """Calculate module count from CapacityRule nodes.

        Generic linear scaling: modules_needed = ceil(input_value / output_rating).
        input_requirement is a graph-supplied string key (e.g., "airflow_m3h", "cups_per_day").
        """
        if not item_id:
            return None

        try:
            rules = self.db.get_capacity_rules(item_id)
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to query capacity rules: {e}")
            return None

        if not rules:
            return None

        # Use first matching rule where input data is available
        for rule in rules:
            input_key = rule.get("input_requirement", "")
            input_value = context.get(input_key)
            if input_value is None:
                continue

            try:
                input_float = float(input_value)
                output_rating = float(rule.get("output_rating", 0))
            except (ValueError, TypeError):
                continue

            # Component-aware capacity: if rule specifies per-component rating,
            # compute effective output_rating from component count in context.
            # Domain-agnostic: cpc and cck are opaque graph properties.
            cpc = rule.get("capacity_per_component")
            cck = rule.get("component_count_key")
            component_count = None
            if cpc and cck and context.get(cck) is not None:
                try:
                    component_count = float(context[cck])
                    output_rating = component_count * float(cpc)
                    logger.info(
                        f"[TraitEngine] Component-aware capacity: "
                        f"{component_count} x {cpc} = {output_rating}"
                    )
                except (ValueError, TypeError):
                    pass  # Fall through to flat output_rating

            if output_rating <= 0:
                continue

            modules_needed = math.ceil(input_float / output_rating)
            result = {
                "input_requirement": input_key,
                "input_value": input_float,
                "output_rating": output_rating,
                "modules_needed": max(1, modules_needed),
                "module_descriptor": rule.get("module_descriptor", ""),
                "assumption": rule.get("assumption", ""),
                "description": rule.get("description", ""),
                "capacity_per_component": float(cpc) if cpc else None,
                "component_count": component_count,
            }
            logger.info(
                f"[TraitEngine] Capacity: {input_float} / {output_rating} = {modules_needed} modules"
            )
            return result

        return None

    def find_capacity_alternatives(
        self,
        blocked_pf_id: str,
        capacity_result: dict,
        input_value: float,
        required_trait_ids: list[str] | None = None,
    ) -> list:
        """Find products that handle the same requirement in fewer modules (v3.4).

        When modules_needed > 1, queries the graph for product families whose
        CapacityRule output_rating for the same module dimensions exceeds the
        blocked product's rating. Only returns alternatives needing fewer modules.

        v3.5: required_trait_ids filters alternatives to only those with the
        stressor-demanded traits (APPLICATION-CRITICAL).

        Returns list[AlternativeProduct], max 3, priority-ordered.
        """
        if not blocked_pf_id or not capacity_result:
            return []

        module_descriptor = capacity_result.get("module_descriptor", "")
        blocked_rating = capacity_result.get("output_rating", 0)
        blocked_modules = capacity_result.get("modules_needed", 1)
        input_req = capacity_result.get("input_requirement", "")

        if not module_descriptor or blocked_rating <= 0:
            return []

        try:
            rows = self.db.find_products_with_higher_capacity(
                blocked_pf_id, module_descriptor, blocked_rating,
                required_trait_ids=required_trait_ids,
            )
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to find capacity alternatives: {e}")
            return []

        alternatives = []
        for row in rows:
            alt_rating = float(row.get("output_rating", 0))
            if alt_rating <= 0:
                continue

            alt_modules = math.ceil(input_value / alt_rating)
            if alt_modules >= blocked_modules:
                continue  # Not an improvement

            if alt_modules == 1:
                reason = (
                    f"Handles {input_value:.0f} {input_req} in a single "
                    f"{module_descriptor} module ({alt_rating:.0f} capacity)"
                )
            else:
                reason = (
                    f"Needs only {alt_modules} module(s) vs {blocked_modules} "
                    f"({alt_rating:.0f} per module)"
                )

            alternatives.append(AlternativeProduct(
                product_family_id=row["product_id"],
                product_family_name=row.get("product_name", row["product_id"]),
                why_it_works=reason,
                selection_priority=row.get("selection_priority", 50) or 50,
                details={
                    "output_rating": alt_rating,
                    "modules_needed": alt_modules,
                    "module_descriptor": module_descriptor,
                    "description": row.get("description", ""),
                },
            ))

        alternatives.sort(key=lambda a: a.selection_priority)
        return alternatives[:3]

    # =========================================================================
    # STEP 5d1b: COMPUTE SIZING ARRANGEMENT (Graph-Driven)
    # =========================================================================

    def compute_sizing_arrangement(
        self,
        item_id: str,
        context: dict,
    ) -> Optional[dict]:
        """Compute optimal module arrangement using graph-driven Strategy metadata.

        Reads spatial expansion rules from the graph Strategy node:
        - primary_axis: which dimension has the user constraint (e.g., "width_mm")
        - secondary_axis: which dimension expands vertically (e.g., "height_mm")
        - expansion_unit: module increment size (e.g., 600)

        Python performs pure math (floor/ceil) on graph-supplied axes.
        No hardcoded axis names — a different domain could use
        primary_axis="depth_mm", secondary_axis="height_mm" and it works.

        Args:
            item_id: ProductFamily ID (e.g., 'FAM_GDP')
            context: Dict with airflow_m3h, max_width_mm, etc.

        Returns:
            Dict with selected_module, arrangement geometry, determined_properties.
        """
        airflow = context.get("airflow_m3h") or context.get("airflow")
        if airflow is None:
            return None

        try:
            airflow_float = float(airflow)
        except (ValueError, TypeError):
            return None

        # --- Graph-driven spatial strategy ---
        strategy = None
        try:
            strategy = self.db.get_optimization_strategy(item_id)
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to query strategy: {e}")

        # Read axis names from graph Strategy node (domain-agnostic)
        primary_axis = (strategy or {}).get("primary_axis") or "width_mm"
        secondary_axis = (strategy or {}).get("secondary_axis") or "height_mm"
        expansion_unit = (strategy or {}).get("expansion_unit")

        # User constraints on BOTH axes: context key = "max_{axis_name}"
        primary_constraint_key = f"max_{primary_axis}"
        secondary_constraint_key = f"max_{secondary_axis}"
        user_primary_constraint = context.get(primary_constraint_key)
        user_secondary_constraint = context.get(secondary_constraint_key)

        try:
            modules = self.db.get_available_dimension_modules(item_id)
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to query dimension modules: {e}")
            return None

        if not modules:
            return None

        # v3.9: Keep unfiltered list for single-module alternative search
        all_modules = list(modules)

        # Filter modules by primary axis constraint
        max_primary = None
        if user_primary_constraint is not None:
            try:
                max_primary = int(user_primary_constraint)
            except (ValueError, TypeError):
                max_primary = None

            if max_primary:
                fitting = [
                    m for m in modules
                    if m.get(primary_axis, 0) <= max_primary
                ]
                if fitting:
                    total_before = len(modules)
                    modules = fitting
                    logger.info(
                        f"[TraitEngine] {primary_axis} constraint {max_primary}mm: "
                        f"{len(fitting)}/{total_before} modules fit"
                    )
                else:
                    logger.warning(
                        f"[TraitEngine] No modules fit within "
                        f"{primary_axis}≤{max_primary}mm constraint"
                    )

        # Filter modules by secondary axis constraint
        max_secondary = None
        if user_secondary_constraint is not None:
            try:
                max_secondary = int(user_secondary_constraint)
            except (ValueError, TypeError):
                max_secondary = None

            if max_secondary:
                fitting = [
                    m for m in modules
                    if m.get(secondary_axis, 0) <= max_secondary
                ]
                if fitting:
                    total_before = len(modules)
                    modules = fitting
                    logger.info(
                        f"[TraitEngine] {secondary_axis} constraint {max_secondary}mm: "
                        f"{len(fitting)}/{total_before} modules fit"
                    )
                else:
                    logger.warning(
                        f"[TraitEngine] No modules fit within "
                        f"{secondary_axis}≤{max_secondary}mm constraint"
                    )

        # v3.5b: Explicit dimension lock
        # When user specifies dimensions (e.g., "600x600"), honor them for module
        # selection. Space constraints (max_width, max_height) determine arrangement
        # geometry only. Fall back to "biggest fitting" when no explicit dims given.
        explicit_primary = context.get(primary_axis.replace("_mm", ""))
        explicit_secondary = context.get(secondary_axis.replace("_mm", ""))

        best = None
        if explicit_primary or explicit_secondary:
            for m in modules:
                match = True
                if explicit_primary and int(m.get(primary_axis, 0)) != int(explicit_primary):
                    match = False
                if explicit_secondary and int(m.get(secondary_axis, 0)) != int(explicit_secondary):
                    match = False
                if match:
                    best = m
                    logger.info(
                        f"[TraitEngine] Dimension lock: exact match {m.get('id')} "
                        f"({m.get(primary_axis)}x{m.get(secondary_axis)}mm)"
                    )
                    break

        if best is None and modules:
            # No exact match or no explicit dims — pick optimal module:
            # 1. Prefer smallest single-unit module that covers required airflow
            # 2. If none can do it alone, pick highest airflow to minimize unit count
            single_unit = [
                m for m in modules
                if float(m.get("reference_airflow_m3h", 0)) >= airflow_float
            ]
            if single_unit:
                best = min(
                    single_unit,
                    key=lambda m: float(m.get("reference_airflow_m3h", 0))
                )
                logger.info(
                    f"[TraitEngine] Optimal single-unit: {best.get('id')} "
                    f"({best.get('reference_airflow_m3h')} m³/h >= {airflow_float})"
                )
            else:
                best = max(
                    modules,
                    key=lambda m: float(m.get("reference_airflow_m3h", 0))
                )
                logger.info(
                    f"[TraitEngine] No single-unit option — highest airflow: "
                    f"{best.get('id')} ({best.get('reference_airflow_m3h')} m³/h)"
                )
        if not best or not best.get("reference_airflow_m3h"):
            return None

        ref_airflow = float(best["reference_airflow_m3h"])
        modules_needed = max(1, math.ceil(airflow_float / ref_airflow))

        # v3.9: When explicit dimensions cause multi-module, find single-module alternatives
        # Search ALL modules (not filtered by spatial constraints) since the point
        # is to suggest a larger module that avoids needing multiple units.
        single_module_alternatives = []
        if modules_needed > 1 and (explicit_primary or explicit_secondary):
            for m in all_modules:
                m_airflow = float(m.get("reference_airflow_m3h", 0))
                if m_airflow >= airflow_float and m.get("id") != best.get("id"):
                    single_module_alternatives.append({
                        "module_id": m.get("id", ""),
                        "label": m.get("label", ""),
                        "width_mm": m.get("width_mm"),
                        "height_mm": m.get("height_mm"),
                        "reference_airflow_m3h": m_airflow,
                    })
            # Sort by airflow (smallest sufficient first)
            single_module_alternatives.sort(key=lambda x: x["reference_airflow_m3h"])
            # Keep top 3
            single_module_alternatives = single_module_alternatives[:3]
            if single_module_alternatives:
                alt_desc = ", ".join(
                    f"{a['label']} ({a['reference_airflow_m3h']:.0f} m³/h)"
                    for a in single_module_alternatives
                )
                logger.info(
                    f"[TraitEngine] Single-module alternatives: {alt_desc}"
                )

        # v3.10: Oversizing detection — warn when airflow is far below module capacity
        total_capacity = ref_airflow * modules_needed
        utilization_pct = (airflow_float / total_capacity * 100) if total_capacity > 0 else 100
        oversizing_warning = None
        smaller_module_alternatives = []
        if utilization_pct < 30 and modules_needed == 1:
            # Find the smallest module that still covers required airflow
            candidates = sorted(
                all_modules,
                key=lambda m: float(m.get("reference_airflow_m3h", 0))
            )
            for m in candidates:
                m_airflow = float(m.get("reference_airflow_m3h", 0))
                if m_airflow >= airflow_float and m.get("id") != best.get("id"):
                    smaller_module_alternatives.append({
                        "module_id": m.get("id", ""),
                        "label": m.get("label", ""),
                        "width_mm": m.get("width_mm"),
                        "height_mm": m.get("height_mm"),
                        "reference_airflow_m3h": m_airflow,
                    })
            # Keep top 3 smallest
            smaller_module_alternatives = smaller_module_alternatives[:3]
            oversizing_warning = {
                "utilization_pct": round(utilization_pct, 1),
                "module_capacity": ref_airflow,
                "required_airflow": airflow_float,
                "smaller_alternatives": smaller_module_alternatives,
            }
            logger.warning(
                f"[TraitEngine] OVERSIZING: {best.get('id')} capacity "
                f"{ref_airflow} m³/h but only {airflow_float} m³/h required "
                f"({utilization_pct:.0f}% utilization)"
            )

        module_primary = int(best.get(primary_axis, 0))
        module_secondary = int(best.get(secondary_axis, 0))

        # --- Spatial arrangement (pure math on graph-supplied axes) ---
        # Use actual module width for arrangement geometry.
        # expansion_unit (Strategy property) is an abstract grid step (e.g. 600 for GDB),
        # but the selected module may be wider (e.g. 1800mm). Physical arrangement
        # dimensions must reflect the real module width, not the grid step.
        exp_unit = module_primary
        if max_primary and exp_unit > 0 and modules_needed > 1:
            max_on_primary = max(1, max_primary // exp_unit)
            needed_on_secondary = math.ceil(modules_needed / max_on_primary)
        else:
            max_on_primary = modules_needed
            needed_on_secondary = 1

        effective_primary = exp_unit * max_on_primary
        effective_secondary = module_secondary * needed_on_secondary

        # Validate secondary axis doesn't exceed constraint
        if max_secondary and effective_secondary > max_secondary:
            logger.warning(
                f"[TraitEngine] {secondary_axis} overflow: effective "
                f"{effective_secondary}mm > max {max_secondary}mm. "
                f"Increasing parallel units on primary axis."
            )
            # Re-calculate: fit within secondary constraint by using more primary-axis units
            max_stacked = max(1, max_secondary // module_secondary)
            max_per_row = math.ceil(modules_needed / max_stacked) if max_stacked else modules_needed
            max_on_primary = max_per_row
            needed_on_secondary = max_stacked
            effective_primary = exp_unit * max_on_primary
            effective_secondary = module_secondary * needed_on_secondary

        # --- v3.5: Spatial feasibility check ---
        # After arrangement geometry is finalized, verify the required modules
        # physically fit within BOTH axis constraints simultaneously.
        # Two conditions for spatial impossibility:
        # 1. Not enough slots (modules_needed > max_fitting)
        # 2. Effective dimensions exceed constraints (after overflow recalc)
        max_modules_fitting = max_on_primary * needed_on_secondary
        spatial_feasible = modules_needed <= max_modules_fitting

        # Also check if effective dimensions exceed constraints
        if spatial_feasible and max_primary and effective_primary > max_primary:
            spatial_feasible = False
            # Recalculate true fitting capacity within both constraints
            true_max_on_primary = max(1, max_primary // exp_unit) if exp_unit > 0 else 1
            true_max_on_secondary = (
                max(1, max_secondary // module_secondary)
                if max_secondary and module_secondary > 0
                else modules_needed
            )
            max_modules_fitting = true_max_on_primary * true_max_on_secondary

        if spatial_feasible and max_secondary and effective_secondary > max_secondary:
            spatial_feasible = False
            true_max_on_primary = max(1, max_primary // exp_unit) if max_primary and exp_unit > 0 else modules_needed
            true_max_on_secondary = (
                max(1, max_secondary // module_secondary)
                if module_secondary > 0
                else 1
            )
            max_modules_fitting = true_max_on_primary * true_max_on_secondary

        if not spatial_feasible and (max_primary or max_secondary):
            logger.warning(
                f"[TraitEngine] SPATIAL IMPOSSIBILITY: need {modules_needed} modules "
                f"but only {max_modules_fitting} fit "
                f"({max_on_primary}×{needed_on_secondary}) "
                f"within constraints "
                f"{primary_axis}≤{max_primary}mm, "
                f"{secondary_axis}≤{max_secondary}mm"
            )

        # --- Auto-resolve size-determined properties (v2.8 Task 3) ---
        determined_properties = {}
        try:
            module_id = best.get("id", "")
            if module_id:
                dp_list = self.db.get_size_determined_properties(module_id, item_id)
                for dp in dp_list:
                    if dp.get("key"):
                        determined_properties[dp["key"]] = {
                            "value": dp.get("value"),
                            "display_name": dp.get("display_name", dp["key"]),
                        }
                        logger.info(
                            f"[TraitEngine] Size-determined: "
                            f"{dp['key']} = {dp.get('value')} "
                            f"({dp.get('display_name', '')}) "
                            f"(from {module_id})"
                        )
        except Exception as e:
            logger.warning(f"[TraitEngine] Size-determined properties query failed: {e}")

        result = {
            "selected_module_id": best.get("id", ""),
            "selected_module_width": best.get("width_mm"),
            "selected_module_height": best.get("height_mm"),
            "selected_module_label": best.get("label", ""),
            "reference_airflow_per_module": ref_airflow,
            "total_airflow_required": airflow_float,
            "modules_needed": modules_needed,
            "primary_constrained": max_primary is not None,
            "secondary_constrained": max_secondary is not None,
            "max_primary_mm": max_primary,
            "max_secondary_mm": max_secondary,
            # Legacy aliases for backward compat
            "width_constrained": max_primary is not None,
            "max_width_mm": max_primary,
            # Arrangement geometry — axis-agnostic results
            "horizontal_count": max_on_primary,
            "vertical_count": needed_on_secondary,
            "effective_width": effective_primary,
            "effective_height": effective_secondary,
            # Size-determined properties (e.g., cartridge_count)
            "determined_properties": determined_properties,
            # v3.5: Spatial feasibility
            "spatial_feasible": spatial_feasible,
            "max_modules_fitting": max_modules_fitting,
            # v3.9: Single-module alternatives when explicit dims cause multi-module
            "single_module_alternatives": single_module_alternatives,
            # v3.10: Oversizing detection
            "oversizing_warning": oversizing_warning,
        }

        arrangement_desc = (
            f"{max_on_primary} × {needed_on_secondary}"
            if modules_needed > 1 else "single module"
        )
        logger.info(
            f"[TraitEngine] Sizing: {best.get('id')} "
            f"({module_primary}×{module_secondary}mm) × {modules_needed} "
            f"[{arrangement_desc}] "
            f"→ effective {effective_primary}×{effective_secondary}mm "
            f"= {ref_airflow * modules_needed} m³/h "
            f"(required: {airflow_float})"
        )

        return result

    # =========================================================================
    # STEP 5d2: CHECK MISSING PARAMETERS (Variance Check Loop)
    # =========================================================================

    def check_missing_parameters(
        self,
        item_id: str,
        context: dict,
    ) -> list[MissingParameter]:
        """Check for unresolved variable features / required parameters.

        Queries graph for VariableFeature and Parameter nodes linked to the
        product family. Cross-references with context dict to find gaps.
        All property names come from graph — no hardcoded parameter awareness.

        Args:
            item_id: ProductFamily ID or short code (e.g., 'GDB' or 'FAM_GDB')
            context: Current project state dict with resolved values

        Returns:
            List of MissingParameter for unresolved features
        """
        if not item_id:
            return []

        pf_code = item_id.replace("FAM_", "") if item_id.startswith("FAM_") else item_id

        # Collect all resolved context keys (case-insensitive)
        resolved_keys = {k.lower() for k, v in context.items() if v is not None}

        missing = []

        # Source 1: VariableFeature nodes from graph
        try:
            variable_features = self.db.get_variable_features(pf_code)
            for feat in variable_features:
                param_name = feat.get("parameter_name", "")
                feature_name = feat.get("feature_name", "")
                param_key = param_name.lower() if param_name else feature_name.lower().replace(" ", "_")

                if param_key in resolved_keys or param_name.lower() in resolved_keys:
                    continue

                missing.append(MissingParameter(
                    feature_id=feat.get("feature_id", ""),
                    feature_name=feature_name,
                    parameter_name=param_key,
                    question=feat.get("question", f"Please provide {feature_name}"),
                    why_needed=feat.get("why_needed", ""),
                    options=feat.get("options", []),
                ))
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to query variable features for {pf_code}: {e}")

        logger.info(
            f"[TraitEngine] Variance check for {pf_code}: "
            f"{len(missing)} unresolved parameter(s)"
        )
        return missing

    # =========================================================================
    # STEP 5d3: VALIDATE ACCESSORIES
    # =========================================================================

    def validate_accessories(
        self,
        item_id: str,
        query: str,
    ) -> list[AccessoryValidation]:
        """Validate accessory compatibility with a product family.

        Detects accessory mentions in the query and checks graph for
        HAS_COMPATIBLE_ACCESSORY relationships. If no explicit relationship
        exists, the combination is BLOCKED (strict allow-list).

        All compatibility data comes from graph — no hardcoded product logic.

        Args:
            item_id: ProductFamily ID or short code
            query: User's query text (to detect accessory mentions)

        Returns:
            List of AccessoryValidation results for each detected accessory
        """
        if not item_id:
            return []

        pf_code = item_id.replace("FAM_", "") if item_id.startswith("FAM_") else item_id

        # Detect accessory codes mentioned in query
        # Get all known accessory codes from graph
        try:
            all_accessories = self.db.get_all_accessory_codes()
        except Exception as e:
            logger.debug(f"[TraitEngine] Failed to query accessory codes: {e}")
            return []

        if not all_accessories:
            return []

        query_upper = query.upper()
        detected_accessories = []
        seen_codes = set()
        for acc in all_accessories:
            acc_code = acc.get("code", "")
            acc_name = acc.get("name", "")
            matched = False
            # Match accessory code in query (word boundary aware)
            if acc_code and acc_code not in seen_codes and (
                f" {acc_code} " in f" {query_upper} "
                or f" {acc_code}," in f" {query_upper},"
                or query_upper.endswith(f" {acc_code}")
            ):
                matched = True
            elif acc_name and acc_name.lower() in query.lower():
                matched = True

            if matched:
                code = acc_code or acc_name
                if code not in seen_codes:
                    seen_codes.add(code)
                    detected_accessories.append(code)

        if not detected_accessories:
            return []

        validations = []
        for acc_code in detected_accessories:
            try:
                compat = self.db.get_accessory_compatibility(acc_code, pf_code)

                is_compatible = compat.get("is_compatible")
                if is_compatible is None:
                    is_compatible = False
                    status = compat.get("status", "UNKNOWN")
                else:
                    status = compat.get("status", "ALLOWED" if is_compatible else "BLOCKED")

                validations.append(AccessoryValidation(
                    accessory_code=acc_code,
                    accessory_name=compat.get("accessory", acc_code),
                    product_family_id=f"FAM_{pf_code.upper()}",
                    is_compatible=is_compatible,
                    status=status,
                    reason=compat.get("reason"),
                    compatible_alternatives=compat.get("compatible_alternatives", []),
                ))
            except Exception as e:
                logger.warning(f"[TraitEngine] Accessory check failed for {acc_code}: {e}")
                validations.append(AccessoryValidation(
                    accessory_code=acc_code,
                    accessory_name=acc_code,
                    product_family_id=f"FAM_{pf_code.upper()}",
                    is_compatible=False,
                    status="UNKNOWN",
                    reason=f"Compatibility check failed: {e}",
                ))

        blocked = [v for v in validations if not v.is_compatible]
        logger.info(
            f"[TraitEngine] Accessory validation for {pf_code}: "
            f"{len(validations)} checked, {len(blocked)} BLOCKED"
        )
        return validations

    # =========================================================================
    # STEP 5e: BUILD ASSEMBLY (Multi-Stage Sequence)
    # =========================================================================

    def build_assembly(
        self,
        query: str,
        product_hint: str,
        stressors: list[DetectedStressor],
        rules: list[CausalRule],
        matches: list[TraitMatch],
    ) -> Optional[list[AssemblyStage]]:
        """Try to build a multi-stage assembly instead of pivoting.

        Strategy:
        1. First, try graph-driven DependencyRule nodes (v2.0)
        2. If no graph rules match, fall back to Python inference (v1.0)
        """
        pf_id = product_hint if product_hint.startswith("FAM_") else f"FAM_{product_hint.upper()}"
        user_match = next((m for m in matches if m.product_family_id == pf_id), None)
        if not user_match or not user_match.vetoed:
            return None

        # Only build assembly when veto is due to NEUTRALIZATION (not missing trait)
        neutralization_rules = [
            r for r in rules
            if r.rule_type == "NEUTRALIZED_BY" and r.severity == "CRITICAL"
            and r.trait_name in user_match.traits_neutralized
        ]

        if not neutralization_rules:
            logger.info("[TraitEngine] Veto not from neutralization — assembly N/A")
            return None

        # Graph-driven DependencyRule is the ONLY authority on when assemblies
        # are needed. If no DependencyRule exists for the detected stressors,
        # it means the veto cannot be solved by upstream filtration (e.g.
        # corrosion/material issues need material upgrade, not a pre-filter).
        assembly = self._build_assembly_from_rules(pf_id, user_match, stressors, rules, matches)
        if assembly:
            return assembly

        logger.info(
            "[TraitEngine] No DependencyRule for detected stressors — "
            "assembly N/A (material change or family pivot needed instead)"
        )
        return None

    def _build_assembly_from_rules(
        self,
        pf_id: str,
        user_match: TraitMatch,
        stressors: list[DetectedStressor],
        rules: list[CausalRule],
        matches: list[TraitMatch],
    ) -> Optional[list[AssemblyStage]]:
        """Build assembly from graph DependencyRule nodes."""
        stressor_ids = [s.id for s in stressors]
        try:
            dep_rules = self.db.get_dependency_rules_for_stressors(stressor_ids)
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to query dependency rules: {e}")
            return None

        if not dep_rules:
            logger.info("[TraitEngine] No DependencyRule nodes for detected stressors")
            return None

        all_families = self.db.get_all_product_families_with_traits()
        # Graph-driven priority: families with lower selection_priority are preferred
        # for protector role. Cypher already sorts, but defense-in-depth.
        all_families.sort(key=lambda f: f.get("selection_priority") or 50)
        stages = []

        # Track (family_id, trait_id) to deduplicate protector stages
        seen_protectors = set()

        for dep in dep_rules:
            dep_type = dep.get("dependency_type", "")
            upstream_trait_id = dep.get("upstream_trait_id", "")
            downstream_trait_id = dep.get("downstream_trait_id", "")

            # Check if this rule applies to the target product
            # The target must provide the downstream trait
            target_traits = set(
                next((c.get("all_trait_ids") or [] for c in all_families if c["product_id"] == pf_id), [])
            )
            target_traits.discard(None)

            if downstream_trait_id not in target_traits:
                continue

            if dep_type == "MANDATES_PROTECTION":
                # Find a product with the upstream trait (protector)
                protector_found = False
                for cand in all_families:
                    if cand["product_id"] == pf_id:
                        continue

                    cand_traits = set(cand.get("all_trait_ids") or [])
                    cand_traits.discard(None)

                    if upstream_trait_id in cand_traits:
                        # Deduplicate: same family + same trait = same protector stage
                        dedup_key = (cand["product_id"], upstream_trait_id)
                        if dedup_key in seen_protectors:
                            protector_found = True
                            break

                        # Verify the protector's required trait is not neutralized.
                        # Don't full-evaluate with all rules — protector only needs
                        # to cover its specific role, not the TARGET's traits. (v2.8)
                        trait_neutralized = any(
                            r.trait_id == upstream_trait_id and r.rule_type == "NEUTRALIZED_BY"
                            for r in rules if r.severity == "CRITICAL"
                        )
                        if not trait_neutralized:
                            stages.append(AssemblyStage(
                                role="PROTECTOR",
                                product_family_id=cand["product_id"],
                                product_family_name=cand["product_name"],
                                provides_trait_id=upstream_trait_id,
                                provides_trait_name=dep.get("upstream_trait_name", ""),
                                reason=dep.get("description", ""),
                            ))
                            seen_protectors.add(dedup_key)
                            protector_found = True
                            break

                if not protector_found:
                    logger.info(
                        f"[TraitEngine] DependencyRule {dep.get('id')}: "
                        f"no valid protector with trait {upstream_trait_id}"
                    )
                    return None

        if not stages:
            return None

        # Add the target stage
        stages.append(AssemblyStage(
            role="TARGET",
            product_family_id=pf_id,
            product_family_name=user_match.product_family_name,
            provides_trait_id=dep_rules[0].get("downstream_trait_id", ""),
            provides_trait_name=dep_rules[0].get("downstream_trait_name", ""),
            reason=f"Primary function, protected by upstream stage",
        ))

        logger.info(
            f"[TraitEngine] Assembly from graph rules: "
            f"{' → '.join(f'{s.product_family_name}({s.role})' for s in stages)}"
        )
        return stages

    def _build_assembly_from_inference(
        self,
        pf_id: str,
        user_match: TraitMatch,
        stressors: list[DetectedStressor],
        rules: list[CausalRule],
        matches: list[TraitMatch],
        neutralization_rules: list[CausalRule],
    ) -> Optional[list[AssemblyStage]]:
        """Build assembly via Python inference (v1.0 fallback)."""
        stages = []
        seen_protectors = set()  # (family_id, trait_id) dedup
        all_families = self.db.get_all_product_families_with_traits()

        for neut_rule in neutralization_rules:
            neutralizing_stressor_id = neut_rule.stressor_id

            protector_demands = [
                r for r in rules
                if r.rule_type == "DEMANDS_TRAIT"
                and r.stressor_id == neutralizing_stressor_id
            ]

            if not protector_demands:
                logger.info(f"[TraitEngine] No DEMANDS_TRAIT for {neut_rule.stressor_name}")
                return None

            protector_found = False
            for prot_rule in protector_demands:
                for cand in all_families:
                    if cand["product_id"] == pf_id:
                        continue

                    trait_ids = set(cand.get("all_trait_ids") or [])
                    trait_ids.discard(None)

                    if prot_rule.trait_id in trait_ids:
                        # Deduplicate: same family + same trait = same protector stage
                        dedup_key = (cand["product_id"], prot_rule.trait_id)
                        if dedup_key in seen_protectors:
                            protector_found = True
                            break

                        # Check that the protector's required trait is not neutralized
                        # by ANY detected stressor (not full re-evaluation with all rules,
                        # since the protector doesn't need to cover the TARGET's traits). (v2.8)
                        trait_neutralized = any(
                            r.trait_id == prot_rule.trait_id and r.rule_type == "NEUTRALIZED_BY"
                            for r in rules if r.severity == "CRITICAL"
                        )
                        if not trait_neutralized:
                            stages.append(AssemblyStage(
                                role="PROTECTOR",
                                product_family_id=cand["product_id"],
                                product_family_name=cand["product_name"],
                                provides_trait_id=prot_rule.trait_id,
                                provides_trait_name=prot_rule.trait_name,
                                reason=(
                                    f"Captures {neut_rule.stressor_name} upstream, "
                                    f"preventing it from reaching the {neut_rule.trait_name} stage"
                                ),
                            ))
                            seen_protectors.add(dedup_key)
                            protector_found = True
                            break
                if protector_found:
                    break

            if not protector_found:
                logger.info(f"[TraitEngine] No valid protector for {neut_rule.stressor_name}")
                return None

        target_neut = neutralization_rules[0]
        stages.append(AssemblyStage(
            role="TARGET",
            product_family_id=pf_id,
            product_family_name=user_match.product_family_name,
            provides_trait_id=target_neut.trait_id,
            provides_trait_name=target_neut.trait_name,
            reason=f"Primary {target_neut.trait_name} function, protected by upstream stage",
        ))

        logger.info(
            f"[TraitEngine] Assembly from inference: "
            f"{' → '.join(f'{s.product_family_name}({s.role})' for s in stages)}"
        )
        return stages

    # =========================================================================
    # STEP 6: GET CLARIFICATIONS
    # =========================================================================

    def get_clarifications(
        self,
        recommended: Optional[TraitMatch],
        application_id: Optional[str],
        context: Optional[dict],
        gate_evaluations: Optional[list] = None,
    ) -> list[dict]:
        """Get clarification questions for the recommended product.

        Merges:
        1. Gate VALIDATION_REQUIRED parameters (priority 0 — highest)
        2. Required parameters from Playbook layer
        3. Contextual clarifications from ClarificationRule

        Gate parameters come first so the LLM asks for gate data before anything else.
        """
        context = context or {}
        questions = []
        seen_params = set()

        # v2.0: Merge gate VALIDATION_REQUIRED params at priority 0
        for ge in (gate_evaluations or []):
            if ge.state == "VALIDATION_REQUIRED":
                for param in ge.missing_parameters:
                    p_key = param.get("property_key", "")
                    if p_key in seen_params:
                        continue
                    seen_params.add(p_key)
                    questions.append({
                        "param_id": param.get("param_id", ""),
                        "param_name": param.get("name", p_key),
                        "question_id": f"gate_{ge.gate_id}_{p_key}",
                        "question_text": param.get("question", f"Please provide {p_key}"),
                        "intent": "gate_validation",
                        "priority": 0,  # Highest priority — ask before anything else
                        "triggered_by": ge.gate_name,
                    })

        if not recommended:
            questions.sort(key=lambda q: q.get("priority", 99))
            return questions

        # Extract product family code from ID (FAM_GDB -> GDB)
        pf_code = recommended.product_family_id.replace("FAM_", "")

        # Get required parameters
        try:
            required_params = self.db.get_required_parameters(pf_code)
            for param in required_params:
                param_name = param.get("param_name", "")
                if param_name in context and context[param_name]:
                    continue
                param_id = param.get("param_id", "")
                if param_id in seen_params:
                    continue
                seen_params.add(param_id)
                questions.append({
                    "param_id": param_id,
                    "param_name": param_name,
                    "question_id": param.get("question_id", ""),
                    "question_text": param.get("question_text", ""),
                    "intent": param.get("intent", "sizing"),
                    "priority": param.get("priority", 1),
                    "triggered_by": None,
                })
        except Exception as e:
            logger.warning(f"[TraitEngine] Failed to get required params for {pf_code}: {e}")

        # Get contextual clarifications
        if application_id:
            try:
                contextual = self.db.get_contextual_clarifications(application_id, pf_code)
                for param in contextual:
                    param_name = param.get("param_name", "")
                    if param_name in context and context[param_name]:
                        continue
                    param_id = param.get("param_id", "")
                    if param_id in seen_params:
                        continue
                    seen_params.add(param_id)
                    questions.append({
                        "param_id": param_id,
                        "param_name": param_name,
                        "question_id": param.get("question_id", ""),
                        "question_text": param.get("question_text", ""),
                        "intent": param.get("intent", "engineering"),
                        "priority": param.get("priority", 5),
                        "triggered_by": param.get("rule_name"),
                    })
            except Exception as e:
                logger.warning(f"[TraitEngine] Failed to get contextual clarifications: {e}")

        questions.sort(key=lambda q: q.get("priority", 99))
        return questions

    # =========================================================================
    # STEP 7: ASSEMBLE VERDICT
    # =========================================================================

    def assemble_verdict(
        self,
        stressors: list[DetectedStressor],
        rules: list[CausalRule],
        matches: list[TraitMatch],
        clarifications: list[dict],
        application_match: Optional[dict],
        product_hint: Optional[str],
        assembly: Optional[list] = None,
        goals: Optional[list] = None,
        gate_evaluations: Optional[list] = None,
        constraint_overrides: Optional[list] = None,
        optimization_applied: Optional[dict] = None,
        capacity_calculation: Optional[dict] = None,
        sizing_arrangement: Optional[dict] = None,
        missing_parameters: Optional[list] = None,
        accessory_validations: Optional[list] = None,
        installation_violations: Optional[list] = None,
        capacity_alternatives: Optional[list] = None,
    ) -> EngineVerdict:
        """Assemble the final EngineVerdict from all pipeline results."""
        vetoed = [m for m in matches if m.vetoed]
        non_vetoed = [m for m in matches if not m.vetoed]
        goals = goals or []

        # Determine recommendation and pivot
        has_veto = False
        veto_reason = None
        auto_pivot_to = None
        auto_pivot_name = None
        is_assembly = bool(assembly)

        if is_assembly:
            # Assembly mode: the target is the user's product (even though it's "vetoed" standalone)
            target_stage = next((s for s in assembly if s.role == "TARGET"), None)
            if target_stage:
                pf_id = target_stage.product_family_id
            elif product_hint:
                pf_id = product_hint if product_hint.startswith("FAM_") else f"FAM_{product_hint.upper()}"
            else:
                pf_id = None
            recommended = next((m for m in matches if m.product_family_id == pf_id), None) if pf_id else None
            # In assembly mode, the veto is "resolved" by the protector stage
            # So we report the veto reason but don't set has_veto (it's handled)
            if recommended:
                veto_reason = "; ".join(recommended.veto_reasons[:2]) if recommended.veto_reasons else None
        else:
            recommended = non_vetoed[0] if non_vetoed else None
            # Check if the user's requested product was vetoed (simple pivot case)
            if product_hint:
                pf_id = product_hint if product_hint.startswith("FAM_") else f"FAM_{product_hint.upper()}"
                user_product = next((m for m in matches if m.product_family_id == pf_id), None)
                if user_product and user_product.vetoed:
                    has_veto = True
                    veto_reason = "; ".join(user_product.veto_reasons[:2])
                    if recommended:
                        auto_pivot_to = recommended.product_family_id
                        auto_pivot_name = recommended.product_family_name

        # Build assembly rationale
        assembly_rationale = None
        if is_assembly:
            protectors = [s for s in assembly if s.role == "PROTECTOR"]
            target = next((s for s in assembly if s.role == "TARGET"), None)
            if protectors and target:
                prot_names = ", ".join(s.product_family_name for s in protectors)
                assembly_rationale = (
                    f"{target.product_family_name} provides {target.provides_trait_name} "
                    f"but requires protection from environmental stressors. "
                    f"{prot_names} provides upstream filtration to protect the target stage."
                )

        # Build reasoning trace
        trace = []
        trace.append({
            "step": "Stressor Detection",
            "result": f"Detected {len(stressors)} stressors: {', '.join(s.name for s in stressors)}" if stressors else "No environmental stressors detected",
        })
        if goals:
            trace.append({
                "step": "Goal Detection",
                "result": f"Detected {len(goals)} goal(s): {', '.join(g.name for g in goals)}",
            })
        trace.append({
            "step": "Causal Rules",
            "result": f"Loaded {len(rules)} rules ({sum(1 for r in rules if r.severity == 'CRITICAL')} CRITICAL)",
        })
        trace.append({
            "step": "Trait Matching",
            "result": f"Evaluated {len(matches)} products. Best: {recommended.product_family_name} ({recommended.coverage_score:.0%})" if recommended else "No suitable products found",
        })
        if vetoed:
            trace.append({
                "step": "Engineering Veto",
                "result": f"Vetoed {len(vetoed)} products: {', '.join(m.product_family_name for m in vetoed)}",
            })
        if is_assembly:
            stage_desc = " → ".join(f"{s.product_family_name} ({s.role})" for s in assembly)
            trace.append({
                "step": "Assembly Builder",
                "result": f"Built multi-stage sequence: {stage_desc}",
            })
        elif has_veto:
            trace.append({
                "step": "Auto-Pivot",
                "result": f"Pivoted from {product_hint} to {auto_pivot_name}",
            })

        # v2.0 trace steps
        gate_evaluations = gate_evaluations or []
        constraint_overrides = constraint_overrides or []

        if gate_evaluations:
            fired = [g for g in gate_evaluations if g.state == "FIRED"]
            pending = [g for g in gate_evaluations if g.state == "VALIDATION_REQUIRED"]
            trace.append({
                "step": "Logic Gates",
                "result": (
                    f"Evaluated {len(gate_evaluations)} gates: "
                    f"{len(fired)} FIRED, {len(pending)} VALIDATION_REQUIRED"
                ),
            })

        if constraint_overrides:
            trace.append({
                "step": "Hard Constraints",
                "result": (
                    f"Auto-corrected {len(constraint_overrides)} constraint(s): "
                    + ", ".join(f"{co.property_key} {co.original_value}→{co.corrected_value}" for co in constraint_overrides)
                ),
            })

        if capacity_calculation:
            trace.append({
                "step": "Capacity Calculation",
                "result": (
                    f"{capacity_calculation.get('input_value')} / "
                    f"{capacity_calculation.get('output_rating')} = "
                    f"{capacity_calculation.get('modules_needed')} module(s)"
                ),
            })

        # v3.4: Capacity alternatives trace
        capacity_alternatives = capacity_alternatives or []
        if capacity_alternatives:
            trace.append({
                "step": "Capacity Alternatives",
                "result": (
                    f"Found {len(capacity_alternatives)} product(s) with higher capacity: "
                    + ", ".join(a.product_family_name for a in capacity_alternatives)
                ),
            })

        if sizing_arrangement:
            trace.append({
                "step": "Sizing Arrangement",
                "result": (
                    f"Module: {sizing_arrangement.get('selected_module_id')} "
                    f"({sizing_arrangement.get('selected_module_width')}×"
                    f"{sizing_arrangement.get('selected_module_height')}mm) × "
                    f"{sizing_arrangement.get('modules_needed')}"
                    + (f" [width≤{sizing_arrangement.get('max_width_mm')}mm]"
                       if sizing_arrangement.get('width_constrained') else "")
                ),
            })

        # v2.1 trace steps
        missing_parameters = missing_parameters or []
        accessory_validations = accessory_validations or []

        if missing_parameters:
            trace.append({
                "step": "Variance Check",
                "result": (
                    f"{len(missing_parameters)} unresolved parameter(s): "
                    + ", ".join(mp.parameter_name for mp in missing_parameters)
                ),
            })

        blocked_accessories = [av for av in accessory_validations if not av.is_compatible]
        if blocked_accessories:
            trace.append({
                "step": "Accessory Validation",
                "result": (
                    f"BLOCKED {len(blocked_accessories)} accessory(ies): "
                    + ", ".join(f"{av.accessory_code}" for av in blocked_accessories)
                ),
            })

        # Installation constraint violations (v3.0)
        installation_violations = installation_violations or []
        has_installation_block = any(iv.severity == "CRITICAL" for iv in installation_violations)
        if installation_violations:
            trace.append({
                "step": "Installation Constraints",
                "result": (
                    f"BLOCKED — {len(installation_violations)} violation(s): "
                    + ", ".join(iv.constraint_id for iv in installation_violations)
                ),
            })

        has_validation_required = any(g.state == "VALIDATION_REQUIRED" for g in gate_evaluations)
        has_blocked_accessory = len(blocked_accessories) > 0

        return EngineVerdict(
            detected_stressors=stressors,
            active_causal_rules=rules,
            ranked_products=matches,
            vetoed_products=vetoed,
            recommended_product=recommended,
            has_veto=has_veto,
            veto_reason=veto_reason,
            auto_pivot_to=auto_pivot_to,
            auto_pivot_name=auto_pivot_name,
            needs_clarification=len(clarifications) > 0 or has_validation_required or len(missing_parameters) > 0,
            clarification_questions=clarifications,
            reasoning_trace=trace,
            application_match=application_match,
            assembly=assembly,
            is_assembly=is_assembly,
            assembly_rationale=assembly_rationale,
            detected_goals=goals,
            gate_evaluations=gate_evaluations,
            has_validation_required=has_validation_required,
            constraint_overrides=constraint_overrides,
            optimization_applied=optimization_applied,
            capacity_calculation=capacity_calculation,
            capacity_alternatives=capacity_alternatives,
            sizing_arrangement=sizing_arrangement,
            missing_parameters=missing_parameters,
            accessory_validations=accessory_validations,
            has_blocked_accessory=has_blocked_accessory,
            installation_violations=installation_violations,
            has_installation_block=has_installation_block,
        )

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    def process_query(
        self,
        query: str,
        product_hint: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> EngineVerdict:
        """Main entry point for the trait-based reasoning engine.

        Args:
            query: User's natural language query
            product_hint: Optional pre-detected product family (e.g., "GDB")
            context: Dict of already-known parameter values

        Returns:
            EngineVerdict with complete reasoning results
        """
        context = context or {}

        # Step 1: Detect stressors (pass context for Scribe-detected environment)
        stressors = self.detect_stressors(query, context=context)

        # Step 1b: Auto-resolve boolean gate params for context-inferred stressors.
        # When a stressor was detected from application/keyword/environment context,
        # its boolean existence-confirmation parameters are redundant.
        if stressors:
            inferred_ids = [
                s.id for s in stressors
                if s.detection_method in ("application_link", "keyword", "environment_link")
                and s.confidence >= 0.7
            ]
            if inferred_ids:
                try:
                    pre_gates = self.db.get_logic_gates_for_stressors(inferred_ids)
                    for gate_data in pre_gates:
                        for param in (gate_data.get("params") or []):
                            if param.get("param_id") is None:
                                continue
                            p_key = param.get("property_key", "")
                            p_unit = (param.get("unit") or "").lower()
                            # Only auto-resolve boolean confirmations, not data-bearing params
                            if p_key and p_unit == "boolean" and context.get(p_key) is None:
                                context[p_key] = True
                                logger.info(
                                    f"[TraitEngine] Auto-resolved '{p_key}' = True "
                                    f"(inferred from detected stressor)"
                                )
                except Exception as e:
                    logger.debug(f"[TraitEngine] Gate pre-resolution failed: {e}")

        # Step 2: Get causal rules
        rules = self.get_causal_rules(stressors)

        # v3.5: Collect stressor-demanded trait IDs (APPLICATION-CRITICAL only)
        # Used to trait-qualify alternatives — ensures alternatives can actually
        # perform the required function (e.g., carbon adsorption for solvent vapors).
        stressor_demanded_trait_ids = list({
            rule.trait_id for rule in rules
            if rule.rule_type == "DEMANDS_TRAIT" and rule.severity == "CRITICAL"
        })
        if stressor_demanded_trait_ids:
            logger.info(
                f"[TraitEngine] Stressor-demanded traits (CRITICAL): "
                f"{stressor_demanded_trait_ids}"
            )

        # Step 3: Get candidate products
        candidates = self.get_candidate_products(query, product_hint)

        # Step 4: Match traits to products
        matches = self.match_traits(rules, candidates, stressors)

        # Step 5: Check vetoes
        matches = self.check_vetoes(matches, rules)

        # Step 5a: Detect functional goals from query
        goals = self.detect_goals(query)

        # Step 5b: Evaluate logic gates (v2.0)
        gate_evaluations = self.evaluate_logic_gates(stressors, context)

        # Step 5c: Try ASSEMBLY first — when products are vetoed due to
        # neutralization, build a multi-stage sequence instead of pivoting.
        # When no product_hint is given, infer TARGET from best-scoring match. (v2.8)
        assembly = None
        non_vetoed = [m for m in matches if not m.vetoed]
        if not non_vetoed and rules:
            target_hint = product_hint
            if not target_hint and matches:
                # Infer target: prefer a product vetoed by NEUTRALIZATION (assemblable)
                # over one vetoed by missing traits (can't help with assembly).
                neutralization_vetoed = [
                    m for m in matches
                    if m.vetoed and m.traits_neutralized
                ]
                if neutralization_vetoed:
                    # Sort by selection_priority to get the preferred product
                    neutralization_vetoed.sort(key=lambda m: m.selection_priority)
                    target_hint = neutralization_vetoed[0].product_family_id.replace("FAM_", "")
                else:
                    target_hint = matches[0].product_family_id.replace("FAM_", "")
                logger.info(f"[TraitEngine] No product_hint — inferred TARGET: {target_hint}")
            if target_hint:
                assembly = self.build_assembly(query, target_hint, stressors, rules, matches)

        # Step 5d: If assembly failed, fall back to simple pivot
        if not assembly and not non_vetoed and rules and product_hint:
            logger.info("[TraitEngine] Assembly not possible, expanding to all families for pivot")
            all_candidates = self.get_candidate_products(query, product_hint=None)
            pf_id = product_hint if product_hint.startswith("FAM_") else f"FAM_{product_hint.upper()}"
            extra_candidates = [c for c in all_candidates if c.get("product_id") != pf_id]
            if extra_candidates:
                extra_matches = self.match_traits(rules, extra_candidates, stressors)
                extra_matches = self.check_vetoes(extra_matches, rules)
                matches.extend(extra_matches)
                matches.sort(key=lambda m: (-int(not m.vetoed), -m.coverage_score))

        # Step 5e: Check hard constraints (v2.0 → v3.0b per-stage)
        constraint_overrides = []
        pf_id_for_constraints = None
        if product_hint:
            pf_id_for_constraints = product_hint if product_hint.startswith("FAM_") else f"FAM_{product_hint.upper()}"
            constraint_overrides = self.check_hard_constraints(pf_id_for_constraints, context)
        elif assembly:
            # Check constraints for ALL assembly stages (v3.0b)
            for stage in assembly:
                stage_overrides = self.check_hard_constraints(stage.product_family_id, context)
                constraint_overrides.extend(stage_overrides)
            # Use TARGET stage for sizing/capacity
            target_stage = next((s for s in assembly if s.role == "TARGET"), None)
            if target_stage:
                pf_id_for_constraints = target_stage.product_family_id
        elif non_vetoed:
            pf_id_for_constraints = non_vetoed[0].product_family_id
            constraint_overrides = self.check_hard_constraints(pf_id_for_constraints, context)

        # Step 5e2: Check installation constraints (v3.0)
        # v3.5: Pass product-relevant demanded trait IDs for trait-qualified alternatives.
        # Intersect stressor demands with the blocked product's own trait IDs —
        # alternatives only need the function THIS product was responsible for,
        # not traits handled by other assembly stages.
        product_relevant_trait_ids = stressor_demanded_trait_ids
        if pf_id_for_constraints and stressor_demanded_trait_ids:
            try:
                product_traits = self.db.get_product_traits(pf_id_for_constraints)
                product_trait_ids = {t["id"] for t in product_traits if t.get("id")}
                narrowed = [
                    t for t in stressor_demanded_trait_ids
                    if t in product_trait_ids
                ]
                if narrowed != stressor_demanded_trait_ids:
                    logger.info(
                        f"[TraitEngine] Narrowed trait filter for alternatives: "
                        f"{stressor_demanded_trait_ids} → {narrowed} "
                        f"(intersected with {pf_id_for_constraints} traits: "
                        f"{sorted(product_trait_ids)})"
                    )
                # Use the intersection as the trait filter.
                # When empty (product provides NONE of the demanded traits),
                # don't trait-filter alternatives at all — any alternative with
                # ANY demanded trait would be an improvement.
                product_relevant_trait_ids = narrowed
            except Exception as e:
                logger.debug(f"[TraitEngine] Could not narrow trait filter: {e}")

        # v3.6: Resolve environment IS_A hierarchy before constraint check
        inst_env = context.get("installation_environment")
        if inst_env:
            try:
                env_chain = self.db.resolve_environment_hierarchy(inst_env)
                context["installation_environment_chain"] = env_chain
                logger.info(f"[TraitEngine] Environment hierarchy: {inst_env} → {env_chain}")
            except Exception as e:
                logger.debug(f"[TraitEngine] Could not resolve env hierarchy: {e}")
                context["installation_environment_chain"] = [inst_env]

        installation_violations = []
        if pf_id_for_constraints:
            installation_violations = self.check_installation_constraints(
                pf_id_for_constraints, context,
                required_trait_ids=product_relevant_trait_ids,
            )

        # Step 5e3: Assembly target pivot on installation block (v3.9)
        # When the assembly TARGET is blocked by a CRITICAL installation
        # constraint, pivot the TARGET stage to the best alternative product.
        # Domain-agnostic: uses violation alternatives sorted by selection_priority.
        if assembly and installation_violations:
            critical_violations = [
                iv for iv in installation_violations if iv.severity == "CRITICAL"
            ]
            if critical_violations:
                target_stage = next(
                    (s for s in assembly if s.role == "TARGET"), None
                )
                if target_stage and target_stage.product_family_id == pf_id_for_constraints:
                    # Collect non-material-change alternatives (product TYPE is blocked)
                    pivot_candidates = []
                    for iv in critical_violations:
                        for alt in getattr(iv, 'alternatives', []):
                            if not alt.details.get("is_material_change"):
                                pivot_candidates.append(alt)

                    if pivot_candidates:
                        pivot_candidates.sort(key=lambda a: a.selection_priority)
                        best = pivot_candidates[0]
                        logger.info(
                            f"[TraitEngine] Assembly target pivot: "
                            f"{target_stage.product_family_id} → {best.product_family_id} "
                            f"(installation constraint block)"
                        )
                        new_target = AssemblyStage(
                            role="TARGET",
                            product_family_id=best.product_family_id,
                            product_family_name=best.product_family_name,
                            provides_trait_id=target_stage.provides_trait_id,
                            provides_trait_name=target_stage.provides_trait_name,
                            reason=(
                                f"Replaces {target_stage.product_family_name} "
                                f"(blocked by installation constraint). "
                                f"{best.why_it_works}"
                            ),
                        )
                        for i, stage in enumerate(assembly):
                            if stage.role == "TARGET":
                                assembly[i] = new_target
                                break
                        # Keep pf_id_for_constraints on the ORIGINAL product so
                        # downstream sizing/capacity diagnose why the user's
                        # requested product fails (full engineering scan).
                        # The pivoted assembly provides the corrected solution.

        # Step 5f-pre: When explicit dimensions are specified (width/height)
        # but no max constraints exist, use explicit dims as sizing constraints.
        # This prevents sizing from selecting a larger module than the user requested.
        # Domain-agnostic: reads generic "width"/"height" keys from context.
        # v3.5: Track whether constraints are user-explicit (for spatial check)
        # vs auto-derived from dimensions (only for module selection, not spatial).
        has_explicit_spatial_constraint = bool(
            context.get("max_width_mm") or context.get("max_height_mm")
        )
        if context.get("width") and not context.get("max_width_mm"):
            context["max_width_mm"] = context["width"]
        if context.get("height") and not context.get("max_height_mm"):
            context["max_height_mm"] = context["height"]

        # Step 5f: Compute sizing arrangement FIRST (v2.5 → v3.3 reorder)
        # Sizing must run before capacity so size-determined properties
        # (e.g., capacity_units/cartridge count) are in context for
        # component-aware capacity calculation.
        sizing_arrangement = None
        if pf_id_for_constraints:
            sizing_arrangement = self.compute_sizing_arrangement(pf_id_for_constraints, context)

        # Step 5f2: Inject size-determined properties into context
        # When a DimensionModule is selected, some properties become fixed
        # (e.g., capacity_units for a given housing size). Auto-inject these
        # so capacity calculation and check_missing_parameters() can use them.
        if sizing_arrangement and sizing_arrangement.get("determined_properties"):
            for dp_key, dp_entry in sizing_arrangement["determined_properties"].items():
                dp_val = dp_entry.get("value") if isinstance(dp_entry, dict) else dp_entry
                if dp_key and dp_val is not None and dp_key not in context:
                    context[dp_key] = dp_val
                    logger.info(
                        f"[TraitEngine] Size→context: {dp_key} = {dp_val} "
                        f"(determined by {sizing_arrangement.get('selected_module_id')})"
                    )

        # Step 5f3: Calculate capacity (v2.0 → v3.3 component-aware)
        # Now runs AFTER sizing so capacity_units is available in context.
        # When sizing arrangement already selected a specific module (e.g.
        # DIM_1800x900 with 15300 m³/h), use its result instead of the
        # base CapacityRule (which is for the 600x600 reference module).
        capacity_calculation = None
        if sizing_arrangement and sizing_arrangement.get("modules_needed") is not None:
            ref_af = sizing_arrangement.get("reference_airflow_per_module", 0)
            total_af = sizing_arrangement.get("total_airflow_required", 0)
            if ref_af and total_af:
                capacity_calculation = {
                    "input_requirement": "airflow_m3h",
                    "input_value": total_af,
                    "output_rating": ref_af,
                    "modules_needed": sizing_arrangement["modules_needed"],
                    "module_descriptor": (sizing_arrangement.get("selected_module_label", "")
                                         .replace(" mm", "")),
                    "assumption": "From sizing arrangement (actual selected module)",
                    "description": f"Sized module: {sizing_arrangement.get('selected_module_id', '')}",
                }
                logger.info(
                    f"[TraitEngine] Capacity from sizing: "
                    f"{total_af}/{ref_af} = {sizing_arrangement['modules_needed']} module(s)"
                )
        if capacity_calculation is None and pf_id_for_constraints:
            capacity_calculation = self.calculate_capacity(pf_id_for_constraints, context)

        # Step 5f4: Find capacity alternatives (v3.4)
        # v3.5: Pass product-relevant trait IDs for trait-qualified alternatives
        capacity_alternatives = []
        if capacity_calculation and capacity_calculation.get("modules_needed", 1) > 1:
            capacity_alternatives = self.find_capacity_alternatives(
                pf_id_for_constraints, capacity_calculation,
                capacity_calculation["input_value"],
                required_trait_ids=product_relevant_trait_ids,
            )

        # Step 5f5: Spatial feasibility check (v3.5)
        # When sizing says modules don't physically fit in the constrained space,
        # create a synthetic installation violation (CRITICAL block).
        # ONLY applies when user explicitly specified space constraints (e.g.,
        # "max width 1250mm"), NOT when constraints are auto-derived from
        # requested module dimensions (Step 5f-pre).
        if (sizing_arrangement
                and has_explicit_spatial_constraint
                and not sizing_arrangement.get("spatial_feasible", True)):
            spatial_violation = InstallationViolation(
                constraint_id="SPATIAL_IMPOSSIBILITY",
                constraint_type="SPATIAL_IMPOSSIBILITY",
                severity="CRITICAL",
                error_msg=(
                    f"Requires {sizing_arrangement['modules_needed']} modules "
                    f"but only {sizing_arrangement['max_modules_fitting']} fit "
                    f"within the available space "
                    f"({sizing_arrangement.get('max_primary_mm')}mm × "
                    f"{sizing_arrangement.get('max_secondary_mm')}mm)"
                ),
                details={
                    "modules_needed": sizing_arrangement["modules_needed"],
                    "max_modules_fitting": sizing_arrangement["max_modules_fitting"],
                    "horizontal_count": sizing_arrangement.get("horizontal_count"),
                    "vertical_count": sizing_arrangement.get("vertical_count"),
                    "max_primary_mm": sizing_arrangement.get("max_primary_mm"),
                    "max_secondary_mm": sizing_arrangement.get("max_secondary_mm"),
                    "reference_airflow_per_module": sizing_arrangement.get(
                        "reference_airflow_per_module"
                    ),
                },
                alternatives=capacity_alternatives,  # reuse v3.4 capacity alternatives
            )
            installation_violations.append(spatial_violation)
            logger.info(
                f"[TraitEngine] Spatial impossibility added as installation violation: "
                f"need {sizing_arrangement['modules_needed']} modules, "
                f"max {sizing_arrangement['max_modules_fitting']} fit"
            )

        # Step 5g: Get optimization strategy (v2.0)
        optimization_applied = None
        if pf_id_for_constraints:
            try:
                optimization_applied = self.db.get_optimization_strategy(pf_id_for_constraints)
            except Exception as e:
                logger.warning(f"[TraitEngine] Failed to get optimization strategy: {e}")

        # Step 5h: Auto-resolve parameters with graph-stored defaults (v2.4)
        # MUST run BEFORE missing-parameter check so auto-resolved values
        # are already in context when the variance check runs.
        # If a VariableFeature has auto_resolve=true and default_value, FORCE it
        # into context. 100% domain-agnostic — the graph defines which params
        # auto-resolve and to what value.
        if pf_id_for_constraints:
            vf_list = self.db.get_variable_features(
                pf_id_for_constraints.replace("FAM_", "")
            )
            for vf in vf_list:
                if vf.get("auto_resolve") and vf.get("default_value") is not None:
                    p_name = vf.get("parameter_name") or vf.get("property_key", "")
                    if p_name:
                        old_val = context.get(p_name)
                        default_val = vf["default_value"]
                        context[p_name] = default_val
                        logger.info(
                            f"[TraitEngine] Auto-resolved '{p_name}' = {default_val} "
                            f"(graph default for {vf.get('feature_name', vf.get('name', '?'))})"
                            + (f" [overrode {old_val}]" if old_val is not None and old_val != default_val else "")
                        )

        # Step 5h2: Check missing parameters — variance check loop (v2.1)
        # Runs AFTER auto-resolve so graph-defaulted params won't appear as missing
        missing_parameters = []
        if pf_id_for_constraints:
            missing_parameters = self.check_missing_parameters(pf_id_for_constraints, context)

        # Step 5i: Validate accessories mentioned in query (v2.1)
        accessory_validations = []
        if pf_id_for_constraints:
            accessory_validations = self.validate_accessories(pf_id_for_constraints, query)

        # Step 6: Get clarifications for recommended product
        non_vetoed = [m for m in matches if not m.vetoed]
        if assembly:
            # Use assembly TARGET's family (product_hint may be None when inferred)
            target_stage = next((s for s in assembly if s.role == "TARGET"), None)
            if target_stage:
                pf_id = target_stage.product_family_id
            elif product_hint:
                pf_id = product_hint if product_hint.startswith("FAM_") else f"FAM_{product_hint.upper()}"
            else:
                pf_id = None
            recommended = next((m for m in matches if m.product_family_id == pf_id), None) if pf_id else None
        else:
            recommended = non_vetoed[0] if non_vetoed else None

        # Determine application for contextual clarifications
        application_id = None
        application_match = None
        apps = None

        # 1. Direct application_link stressor (highest confidence)
        for s in stressors:
            if s.source_context and s.detection_method == "application_link":
                if apps is None:
                    apps = self.db.get_all_applications()
                for app in apps:
                    if app.get("name") == s.source_context:
                        application_id = app["id"]
                        application_match = app
                        break
                if application_match:
                    break

        # 2. Fallback: match from context dict (Scribe-detected environment/application)
        if not application_match:
            env_key = context.get("installation_environment", "")
            app_key = context.get("detected_application", "")
            hints = context.get("context_hints", [])
            raw_terms = [env_key, app_key] + (hints if isinstance(hints, list) else [])

            # 2a. Direct ID match (APP_POWDER_COATING → match app.id)
            if apps is None:
                apps = self.db.get_all_applications()
            for t in raw_terms:
                if not t:
                    continue
                for app in apps:
                    if app.get("id", "").upper() == t.upper():
                        application_id = app.get("id")
                        application_match = app
                        break
                if application_match:
                    break

            # 2b. Keyword match (strip ENV_/APP_ prefix → plain words)
            if not application_match:
                search_terms = []
                for t in raw_terms:
                    if not t:
                        continue
                    search_terms.append(t)
                    upper = t.upper()
                    if upper.startswith("ENV_") or upper.startswith("APP_"):
                        search_terms.append(t[4:].replace("_", " "))
            if not application_match and search_terms:
                if apps is None:
                    apps = self.db.get_all_applications()
                for app in apps:
                    app_keywords = [k.lower() for k in app.get("keywords", [])]
                    app_name_lower = app.get("name", "").lower()
                    for term in search_terms:
                        term_lower = term.lower()
                        if term_lower in app_name_lower or any(term_lower in kw for kw in app_keywords):
                            application_id = app.get("id")
                            application_match = app
                            break
                    if application_match:
                        break

        clarifications = self.get_clarifications(
            recommended, application_id, context,
            gate_evaluations=gate_evaluations,
        )

        # Step 7: Assemble verdict
        return self.assemble_verdict(
            stressors=stressors,
            rules=rules,
            matches=matches,
            clarifications=clarifications,
            application_match=application_match,
            product_hint=product_hint,
            assembly=assembly,
            goals=goals,
            gate_evaluations=gate_evaluations,
            constraint_overrides=constraint_overrides,
            optimization_applied=optimization_applied,
            capacity_calculation=capacity_calculation,
            sizing_arrangement=sizing_arrangement,
            missing_parameters=missing_parameters,
            accessory_validations=accessory_validations,
            installation_violations=installation_violations,
            capacity_alternatives=capacity_alternatives,
        )


# =============================================================================
# HELPERS
# =============================================================================

def _severity_rank(severity: str) -> int:
    """Convert severity to numeric rank for comparison."""
    return {"CRITICAL": 3, "WARNING": 2, "INFO": 1}.get(severity, 0)
