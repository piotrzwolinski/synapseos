"""
Verdict-to-Report Adapter

Transforms EngineVerdict (from trait-based engine) into GraphReasoningReport
so that retriever.py works transparently with either engine.

The adapter:
1. Maps DetectedStressors → ApplicationMatch
2. Maps TraitMatch vetoes → SuitabilityResult + RiskWarnings
3. Maps auto_pivot → ProductPivot
4. Maps clarification_questions → ClarificationQuestion list
5. Overrides to_reasoning_summary_steps() for trait-based UI rendering
"""

from dataclasses import dataclass, field
from typing import Optional

from logic.graph_reasoning import (
    ApplicationMatch,
    MaterialRequirement,
    RiskWarning,
    ClarificationQuestion,
    SuitabilityResult,
    ProductPivot,
    UnmitigatedPhysicsRisk,
    GraphReasoningReport,
    GraphTraversalStep,
    VariableFeature,
    AccessoryCompatibilityResult,
)
from logic.universal_engine import (
    EngineVerdict, TraitMatch, CausalRule, AssemblyStage,
    GateEvaluation, ConstraintOverride,
    MissingParameter, AccessoryValidation,
)


class TraitBasedReport(GraphReasoningReport):
    """GraphReasoningReport subclass with trait-based reasoning steps and prompt injection.

    Overrides to_reasoning_summary_steps() to render stressor/trait/veto logic
    instead of domain-specific material/vulnerability chains.

    Overrides to_prompt_injection() to use the EngineVerdict's own method which
    is more tailored to trait-based output.
    """

    def __init__(self, verdict: EngineVerdict, **kwargs):
        self._verdict = verdict
        super().__init__(**kwargs)

    def to_prompt_injection(self) -> str:
        """Use the EngineVerdict's prompt injection which is designed for trait-based output."""
        return self._verdict.to_prompt_injection()

    def to_reasoning_summary_steps(self) -> list[dict]:
        """Convert trait-based reasoning to UI summary steps."""
        steps = []
        verdict = self._verdict

        # =================================================================
        # Step 1: STRESSOR DETECTION
        # =================================================================
        stressor_traversals = []

        for s in verdict.detected_stressors:
            if s.detection_method == "keyword":
                cypher = (
                    f"MATCH (s:EnvironmentalStressor) "
                    f"WHERE ANY(kw IN s.keywords WHERE kw IN $query_words)"
                )
                path_desc = (
                    f"Query['{', '.join(s.matched_keywords[:3])}'] "
                    f"──KEYWORD_MATCH──▶ Stressor:{s.name}"
                )
            elif s.detection_method == "application_link":
                cypher = (
                    f"MATCH (app:Application)-[:EXPOSES_TO]->(s:EnvironmentalStressor)"
                )
                path_desc = (
                    f"Query ──CONTEXT──▶ Application:{s.source_context or '?'} "
                    f"──EXPOSES_TO──▶ Stressor:{s.name}"
                )
            else:
                cypher = (
                    f"MATCH (env:Environment)-[:EXPOSES_TO]->(s:EnvironmentalStressor)"
                )
                path_desc = (
                    f"Query ──CONTEXT──▶ Environment:{s.source_context or '?'} "
                    f"──EXPOSES_TO──▶ Stressor:{s.name}"
                )

            stressor_traversals.append({
                "layer": 2,
                "layer_name": "Physics & Traits",
                "operation": f"Stressor Detection ({s.detection_method})",
                "cypher_pattern": cypher,
                "nodes_visited": [f"EnvironmentalStressor:{s.name}"],
                "relationships": ["EXPOSES_TO", "KEYWORD_MATCH"],
                "path_description": path_desc,
                "result_summary": (
                    f"Detected {s.name} via {s.detection_method} "
                    f"(confidence: {s.confidence:.2f})"
                ),
            })

        stressor_names = [s.name for s in verdict.detected_stressors]
        if stressor_names:
            desc = f"Detected {len(stressor_names)} stressor(s): {', '.join(stressor_names)}"
        else:
            desc = "No environmental stressors detected"

        steps.append({
            "step": "STRESSOR DETECTION",
            "icon": "🔍",
            "description": desc,
            "graph_traversals": stressor_traversals,
        })

        # =================================================================
        # Step 2: CAUSAL RULES
        # =================================================================
        rule_traversals = []

        critical_rules = [r for r in verdict.active_causal_rules if r.severity == "CRITICAL"]
        warning_rules = [r for r in verdict.active_causal_rules if r.severity == "WARNING"]

        for rule in critical_rules + warning_rules:
            if rule.rule_type == "DEMANDS_TRAIT":
                path_desc = (
                    f"Stressor:{rule.stressor_name} "
                    f"──DEMANDS_TRAIT [{rule.severity}]──▶ "
                    f"PhysicalTrait:{rule.trait_name}"
                )
                cypher = (
                    f"MATCH (s:EnvironmentalStressor {{id: '{rule.stressor_id}'}})"
                    f"-[:DEMANDS_TRAIT]->(t:PhysicalTrait {{id: '{rule.trait_id}'}})"
                )
            else:
                path_desc = (
                    f"PhysicalTrait:{rule.trait_name} "
                    f"──NEUTRALIZED_BY [{rule.severity}]──▶ "
                    f"Stressor:{rule.stressor_name}"
                )
                cypher = (
                    f"MATCH (t:PhysicalTrait {{id: '{rule.trait_id}'}})"
                    f"-[:NEUTRALIZED_BY]->(s:EnvironmentalStressor {{id: '{rule.stressor_id}'}})"
                )

            rule_traversals.append({
                "layer": 2,
                "layer_name": "Physics & Traits",
                "operation": f"Causal Rule: {rule.rule_type}",
                "cypher_pattern": cypher,
                "nodes_visited": [
                    f"EnvironmentalStressor:{rule.stressor_name}",
                    f"PhysicalTrait:{rule.trait_name}",
                ],
                "relationships": [rule.rule_type],
                "path_description": path_desc,
                "result_summary": rule.explanation,
            })

        n_crit = len(critical_rules)
        n_warn = len(warning_rules)
        steps.append({
            "step": "CAUSAL RULES",
            "icon": "⚡",
            "description": (
                f"Loaded {len(verdict.active_causal_rules)} rules "
                f"({n_crit} CRITICAL, {n_warn} WARNING)"
            ),
            "graph_traversals": rule_traversals,
        })

        # =================================================================
        # Step 3: TRAIT MATCHING
        # =================================================================
        trait_traversals = []

        for tm in (verdict.ranked_products or [])[:5]:
            nodes = [f"ProductFamily:{tm.product_family_name}"]
            for t in tm.traits_present:
                nodes.append(f"Trait:{t} ✓")
            for t in tm.traits_missing:
                nodes.append(f"Trait:{t} ✗")
            for t in tm.traits_neutralized:
                nodes.append(f"Trait:{t} ⚠")

            pf_id = tm.product_family_id
            trait_traversals.append({
                "layer": 1,
                "layer_name": "Inventory & Traits",
                "operation": f"Trait Coverage: {tm.product_family_name}",
                "cypher_pattern": (
                    f"MATCH (pf:ProductFamily {{id: '{pf_id}'}})"
                    f"-[:HAS_TRAIT]->(t:PhysicalTrait)"
                ),
                "nodes_visited": nodes,
                "relationships": ["HAS_TRAIT", "PROVIDES_TRAIT"],
                "path_description": (
                    f"ProductFamily:{tm.product_family_name} "
                    f"──HAS_TRAIT──▶ [{len(tm.traits_present)} met, "
                    f"{len(tm.traits_missing)} missing, "
                    f"{len(tm.traits_neutralized)} neutralized]"
                ),
                "result_summary": (
                    f"Coverage: {tm.coverage_score:.0%}"
                    + (f" — VETOED: {'; '.join(tm.veto_reasons[:2])}" if tm.vetoed else "")
                ),
            })

        rec = verdict.recommended_product
        if rec:
            desc = f"Best match: {rec.product_family_name} ({rec.coverage_score:.0%} coverage)"
        else:
            desc = "No suitable product found"

        steps.append({
            "step": "TRAIT MATCHING",
            "icon": "🧬",
            "description": desc,
            "graph_traversals": trait_traversals,
        })

        # =================================================================
        # Step 4: ENGINEERING VETO (if applicable)
        # =================================================================
        if verdict.vetoed_products:
            veto_traversals = []
            for tm in verdict.vetoed_products:
                veto_traversals.append({
                    "layer": 2,
                    "layer_name": "Physics & Traits",
                    "operation": f"Veto: {tm.product_family_name}",
                    "cypher_pattern": "Engineering Veto applied via CRITICAL rule violation",
                    "nodes_visited": [f"ProductFamily:{tm.product_family_name}"],
                    "relationships": ["DEMANDS_TRAIT", "NEUTRALIZED_BY"],
                    "path_description": (
                        f"ProductFamily:{tm.product_family_name} "
                        f"──VETOED──▶ {'; '.join(tm.veto_reasons[:2])}"
                    ),
                    "result_summary": f"VETOED: {'; '.join(tm.veto_reasons[:2])}",
                })

            pivot_desc = ""
            if verdict.has_veto and verdict.auto_pivot_name:
                pivot_desc = f" → Pivoted to {verdict.auto_pivot_name}"

            steps.append({
                "step": "ENGINEERING VETO",
                "icon": "🛑",
                "description": (
                    f"Vetoed {len(verdict.vetoed_products)} product(s)"
                    + pivot_desc
                ),
                "graph_traversals": veto_traversals,
            })

        # =================================================================
        # Step 4b: ASSEMBLY (if applicable — replaces pivot)
        # =================================================================
        if verdict.is_assembly and verdict.assembly:
            assembly_traversals = []
            for stage in verdict.assembly:
                if stage.role == "PROTECTOR":
                    path_desc = (
                        f"ProductFamily:{stage.product_family_name} "
                        f"──HAS_TRAIT──▶ PhysicalTrait:{stage.provides_trait_name} "
                        f"──PROTECTS──▶ TARGET"
                    )
                else:
                    path_desc = (
                        f"ProductFamily:{stage.product_family_name} "
                        f"──HAS_TRAIT──▶ PhysicalTrait:{stage.provides_trait_name} "
                        f"──FULFILLS──▶ User Goal"
                    )
                assembly_traversals.append({
                    "layer": 2,
                    "layer_name": "Physics & Traits",
                    "operation": f"Assembly Stage: {stage.role}",
                    "cypher_pattern": (
                        f"MATCH (pf:ProductFamily {{id: '{stage.product_family_id}'}})"
                        f"-[:HAS_TRAIT]->(t:PhysicalTrait {{id: '{stage.provides_trait_id}'}})"
                    ),
                    "nodes_visited": [
                        f"ProductFamily:{stage.product_family_name}",
                        f"PhysicalTrait:{stage.provides_trait_name}",
                    ],
                    "relationships": ["HAS_TRAIT"],
                    "path_description": path_desc,
                    "result_summary": (
                        f"{stage.role}: {stage.product_family_name} — {stage.reason}"
                    ),
                })

            stage_desc = " → ".join(
                f"{s.product_family_name} ({s.role})" for s in verdict.assembly
            )
            steps.append({
                "step": "ASSEMBLY BUILDER",
                "icon": "🔧",
                "description": f"Multi-stage system: {stage_desc}",
                "graph_traversals": assembly_traversals,
            })

        # =================================================================
        # Step 5: LOGIC GATES (v2.0)
        # =================================================================
        if verdict.gate_evaluations:
            gate_traversals = []
            for ge in verdict.gate_evaluations:
                if ge.state == "VALIDATION_REQUIRED":
                    missing_keys = [p.get("property_key", "?") for p in ge.missing_parameters]
                    result_summary = f"VALIDATION_REQUIRED — needs: {', '.join(missing_keys)}"
                elif ge.state == "FIRED":
                    result_summary = f"FIRED — {ge.physics_explanation[:100]}..."
                else:
                    result_summary = f"{ge.state}"

                gate_traversals.append({
                    "layer": 3,
                    "layer_name": "Playbook & Gates",
                    "operation": f"Gate: {ge.gate_name}",
                    "cypher_pattern": (
                        f"MATCH (g:LogicGate {{id: '{ge.gate_id}'}})"
                        f"-[:MONITORS]->(s:EnvironmentalStressor {{id: '{ge.stressor_id}'}})"
                    ),
                    "nodes_visited": [
                        f"LogicGate:{ge.gate_name}",
                        f"EnvironmentalStressor:{ge.stressor_name}",
                    ] + [f"Parameter:{p.get('name', '')}" for p in ge.missing_parameters],
                    "relationships": ["MONITORS", "REQUIRES_DATA"],
                    "path_description": (
                        f"LogicGate:{ge.gate_name} "
                        f"──MONITORS──▶ Stressor:{ge.stressor_name} "
                        f"──REQUIRES_DATA──▶ [{', '.join(p.get('property_key', '') for p in ge.missing_parameters)}]"
                    ),
                    "result_summary": result_summary,
                })

            fired_count = sum(1 for g in verdict.gate_evaluations if g.state == "FIRED")
            pending_count = sum(1 for g in verdict.gate_evaluations if g.state == "VALIDATION_REQUIRED")
            steps.append({
                "step": "LOGIC GATES",
                "icon": "🚦",
                "description": (
                    f"Evaluated {len(verdict.gate_evaluations)} gate(s): "
                    f"{fired_count} FIRED, {pending_count} VALIDATION_REQUIRED"
                ),
                "graph_traversals": gate_traversals,
            })

        # =================================================================
        # Step 6: HARD CONSTRAINTS (v2.0)
        # =================================================================
        if verdict.constraint_overrides:
            constraint_traversals = []
            for co in verdict.constraint_overrides:
                constraint_traversals.append({
                    "layer": 1,
                    "layer_name": "Inventory & Constraints",
                    "operation": f"Constraint: {co.property_key}",
                    "cypher_pattern": (
                        f"MATCH (pf:ProductFamily {{id: '{co.item_id}'}})"
                        f"-[:HAS_HARD_CONSTRAINT]->(hc:HardConstraint {{property_key: '{co.property_key}'}})"
                    ),
                    "nodes_visited": [
                        f"ProductFamily:{co.item_id}",
                        f"HardConstraint:{co.property_key}",
                    ],
                    "relationships": ["HAS_HARD_CONSTRAINT"],
                    "path_description": (
                        f"ProductFamily:{co.item_id} "
                        f"──HAS_HARD_CONSTRAINT──▶ "
                        f"{co.property_key} {co.operator} {co.corrected_value}"
                    ),
                    "result_summary": (
                        f"Auto-override: {co.property_key} {co.original_value} → {co.corrected_value}. "
                        f"{co.error_msg}"
                    ),
                })

            steps.append({
                "step": "HARD CONSTRAINTS",
                "icon": "🔒",
                "description": (
                    f"Auto-corrected {len(verdict.constraint_overrides)} constraint(s)"
                ),
                "graph_traversals": constraint_traversals,
            })

        # =================================================================
        # Step 7: CAPACITY (v2.0)
        # =================================================================
        if verdict.capacity_calculation:
            cap = verdict.capacity_calculation
            cap_traversals = [{
                "layer": 1,
                "layer_name": "Inventory & Capacity",
                "operation": "Capacity Calculation",
                "cypher_pattern": (
                    f"MATCH (pf:ProductFamily)-[:HAS_CAPACITY]->"
                    f"(cr:CapacityRule {{input_requirement: '{cap.get('input_requirement', '')}'}})"
                ),
                "nodes_visited": [f"CapacityRule:{cap.get('description', '')}"],
                "relationships": ["HAS_CAPACITY"],
                "path_description": (
                    f"Input: {cap.get('input_value')} {cap.get('input_requirement', '')} / "
                    f"{cap.get('output_rating')} per module = {cap.get('modules_needed')} module(s)"
                ),
                "result_summary": (
                    f"{cap.get('modules_needed')} x {cap.get('module_descriptor', '')} modules needed. "
                    f"Assumption: {cap.get('assumption', '')}"
                ),
            }]

            # v3.4: Capacity alternative traversals
            for alt in getattr(verdict, 'capacity_alternatives', []):
                cap_traversals.append({
                    "layer": 1,
                    "layer_name": "Inventory & Capacity",
                    "operation": f"Capacity Alternative: {alt.product_family_name}",
                    "cypher_pattern": (
                        f"MATCH (pf:ProductFamily {{id: '{alt.product_family_id}'}})"
                        f"-[:HAS_CAPACITY]->(cr:CapacityRule)"
                    ),
                    "nodes_visited": [f"ProductFamily:{alt.product_family_name}"],
                    "relationships": ["HAS_CAPACITY"],
                    "path_description": alt.why_it_works,
                    "result_summary": f"ALTERNATIVE — {alt.product_family_name}: {alt.why_it_works}",
                })

            alt_count = len(getattr(verdict, 'capacity_alternatives', []))
            cap_desc = (
                f"{cap.get('modules_needed')} module(s) needed "
                f"for {cap.get('input_value')} {cap.get('input_requirement', '')}"
            )
            if alt_count:
                cap_desc += f" — {alt_count} alternative(s) found"

            steps.append({
                "step": "CAPACITY CALCULATION",
                "icon": "📐",
                "description": cap_desc,
                "graph_traversals": cap_traversals,
            })

        # =================================================================
        # Step 7b: SIZING ARRANGEMENT (v2.5)
        # =================================================================
        if verdict.sizing_arrangement:
            sa = verdict.sizing_arrangement
            eff_w = sa.get('effective_width', sa.get('selected_module_width'))
            eff_h = sa.get('effective_height', sa.get('selected_module_height'))
            h_count = sa.get('horizontal_count', 1)
            v_count = sa.get('vertical_count', 1)
            arrangement_desc = (
                f" → {h_count}W×{v_count}H = {eff_w}×{eff_h}mm"
                if sa.get('modules_needed', 1) > 1 else f" → {eff_w}×{eff_h}mm"
            )
            sizing_traversals = [{
                "layer": 1,
                "layer_name": "Inventory & Sizing",
                "operation": "Module Sizing",
                "cypher_pattern": (
                    f"MATCH (pf:ProductFamily)-[:AVAILABLE_IN_SIZE]->"
                    f"(dm:DimensionModule {{id: '{sa.get('selected_module_id', '')}'}})"
                ),
                "nodes_visited": [f"DimensionModule:{sa.get('selected_module_id', '')}"],
                "relationships": ["AVAILABLE_IN_SIZE"],
                "path_description": (
                    f"Module {sa.get('selected_module_width')}×{sa.get('selected_module_height')}mm "
                    f"({sa.get('reference_airflow_per_module')} m³/h each) × {sa.get('modules_needed')}"
                    + arrangement_desc
                ),
                "result_summary": (
                    f"{sa.get('modules_needed')} × {sa.get('selected_module_label', '')}"
                    + (f" [width ≤ {sa.get('max_width_mm')}mm]" if sa.get('width_constrained') else "")
                    + f" = {eff_w}×{eff_h}mm effective"
                ),
            }]
            steps.append({
                "step": "SIZING ARRANGEMENT",
                "icon": "📏",
                "description": (
                    f"{sa.get('modules_needed')} × "
                    f"{sa.get('selected_module_width')}×{sa.get('selected_module_height')}mm module(s)"
                    + (f" (width ≤ {sa.get('max_width_mm')}mm)" if sa.get('width_constrained') else "")
                    + f" = {eff_w}×{eff_h}mm"
                ),
                "graph_traversals": sizing_traversals,
            })

        # =================================================================
        # Step 8: MISSING PARAMETERS — Variance Check (v2.1)
        # =================================================================
        if verdict.missing_parameters:
            param_traversals = []
            for mp in verdict.missing_parameters:
                param_traversals.append({
                    "layer": 3,
                    "layer_name": "Playbook & Configuration",
                    "operation": f"Variance Check: {mp.feature_name}",
                    "cypher_pattern": (
                        f"MATCH (pf:ProductFamily)-[:HAS_VARIABLE_FEATURE]->"
                        f"(f:VariableFeature {{id: '{mp.feature_id}'}})"
                    ),
                    "nodes_visited": [f"VariableFeature:{mp.feature_name}"],
                    "relationships": ["HAS_VARIABLE_FEATURE"],
                    "path_description": (
                        f"ProductFamily ──HAS_VARIABLE_FEATURE──▶ "
                        f"{mp.feature_name} (key: {mp.parameter_name})"
                    ),
                    "result_summary": f"UNRESOLVED: {mp.question}",
                })

            steps.append({
                "step": "VARIANCE CHECK",
                "icon": "📋",
                "description": (
                    f"{len(verdict.missing_parameters)} unresolved parameter(s) "
                    f"must be provided before final configuration"
                ),
                "graph_traversals": param_traversals,
            })

        # =================================================================
        # Step 8b: ACCESSORY VALIDATION (v2.1)
        # =================================================================
        blocked_accessories = [av for av in verdict.accessory_validations if not av.is_compatible]
        if blocked_accessories:
            acc_traversals = []
            for av in blocked_accessories:
                acc_traversals.append({
                    "layer": 1,
                    "layer_name": "Inventory & Compatibility",
                    "operation": f"Accessory Check: {av.accessory_code}",
                    "cypher_pattern": (
                        f"MATCH (pf:ProductFamily {{id: '{av.product_family_id}'}})"
                        f"-[:HAS_COMPATIBLE_ACCESSORY]->(acc:Accessory)"
                    ),
                    "nodes_visited": [
                        f"ProductFamily:{av.product_family_id}",
                        f"Accessory:{av.accessory_name}",
                    ],
                    "relationships": ["HAS_COMPATIBLE_ACCESSORY"],
                    "path_description": (
                        f"ProductFamily:{av.product_family_id} "
                        f"──✗ NO COMPATIBLE──▶ Accessory:{av.accessory_code}"
                    ),
                    "result_summary": (
                        f"BLOCKED: {av.reason or 'No explicit compatibility relationship'}"
                        + (f". Try: {', '.join(av.compatible_alternatives)}" if av.compatible_alternatives else "")
                    ),
                })

            steps.append({
                "step": "ACCESSORY VALIDATION",
                "icon": "🔌",
                "description": (
                    f"BLOCKED {len(blocked_accessories)} accessory(ies): "
                    + ", ".join(av.accessory_code for av in blocked_accessories)
                ),
                "graph_traversals": acc_traversals,
            })

        # =================================================================
        # Step 9: CLARIFICATIONS (if any)
        # =================================================================
        if verdict.clarification_questions:
            clar_traversals = []
            for q in verdict.clarification_questions[:3]:
                clar_traversals.append({
                    "layer": 3,
                    "layer_name": "Playbook",
                    "operation": f"Clarification: {q.get('param_name', '')}",
                    "cypher_pattern": (
                        f"MATCH (pf:ProductFamily)-[:NEEDS_PARAMETER]->"
                        f"(p:Parameter {{id: '{q.get('param_id', '')}'}})"
                        f"-[:HAS_QUESTION]->(q:Question)"
                    ),
                    "nodes_visited": [
                        f"Parameter:{q.get('param_name', '')}",
                        f"Question:{q.get('question_id', '')}",
                    ],
                    "relationships": ["NEEDS_PARAMETER", "HAS_QUESTION"],
                    "path_description": (
                        f"Product ──NEEDS_PARAMETER──▶ "
                        f"{q.get('param_name', '')} ──HAS_QUESTION──▶ "
                        f"'{q.get('question_text', '')[:60]}...'"
                    ),
                    "result_summary": q.get("question_text", ""),
                })

            steps.append({
                "step": "CLARIFICATIONS",
                "icon": "❓",
                "description": (
                    f"{len(verdict.clarification_questions)} clarification(s) needed"
                ),
                "graph_traversals": clar_traversals,
            })

        # =================================================================
        # Step N: INSTALLATION CONSTRAINTS (v3.0)
        # =================================================================
        if verdict.installation_violations:
            ic_traversals = []
            for iv in verdict.installation_violations:
                ic_traversals.append({
                    "layer": 1,
                    "layer_name": "Inventory & Constraints",
                    "operation": f"Installation Constraint: {iv.constraint_type}",
                    "cypher_pattern": (
                        f"MATCH (pf:ProductFamily)-[:HAS_INSTALLATION_CONSTRAINT]->"
                        f"(ic:InstallationConstraint {{id: '{iv.constraint_id}'}})"
                    ),
                    "nodes_visited": [f"InstallationConstraint:{iv.constraint_id}"],
                    "relationships": ["HAS_INSTALLATION_CONSTRAINT"],
                    "path_description": iv.error_msg,
                    "result_summary": f"BLOCKED — {iv.error_msg}",
                })

                # v3.3: Add alternative traversals
                for alt in getattr(iv, 'alternatives', []):
                    ic_traversals.append({
                        "layer": 1,
                        "layer_name": "Inventory & Alternatives",
                        "operation": f"Alternative: {alt.product_family_name}",
                        "cypher_pattern": (
                            f"MATCH (pf:ProductFamily {{id: '{alt.product_family_id}'}})"
                        ),
                        "nodes_visited": [f"ProductFamily:{alt.product_family_id}"],
                        "relationships": ["ALTERNATIVE_FOR"],
                        "path_description": alt.why_it_works,
                        "result_summary": f"ALTERNATIVE — {alt.product_family_name}: {alt.why_it_works}",
                    })

            alt_total = sum(len(getattr(iv, 'alternatives', [])) for iv in verdict.installation_violations)
            desc = f"BLOCKED — {len(verdict.installation_violations)} installation constraint(s) violated"
            if alt_total:
                desc += f" — {alt_total} alternative(s) found"

            steps.append({
                "step": "INSTALLATION CONSTRAINTS",
                "icon": "⛔",
                "description": desc,
                "graph_traversals": ic_traversals,
            })

        return steps


class VerdictToReportAdapter:
    """Transforms EngineVerdict → GraphReasoningReport (TraitBasedReport subclass).

    Mapping summary:
    - DetectedStressor (source_context) → ApplicationMatch
    - Vetoed TraitMatch → RiskWarning (severity=CRITICAL)
    - Missing traits → RiskWarning (severity=WARNING)
    - DEMANDS_TRAIT on corrosion → MaterialRequirement
    - has_veto + auto_pivot → ProductPivot
    - clarification_questions → ClarificationQuestion list
    - reasoning_trace → reasoning_steps + graph_evidence
    """

    def adapt(self, verdict: EngineVerdict) -> GraphReasoningReport:
        """Convert an EngineVerdict to a GraphReasoningReport."""
        application = self._map_application(verdict)
        suitability = self._map_suitability(verdict)
        clarifications = self._map_clarifications(verdict)
        product_pivot = self._map_pivot(verdict)
        reasoning_steps = self._map_reasoning_steps(verdict)
        graph_evidence = self._map_evidence(verdict)
        physics_risks = self._map_physics_risks(verdict)
        variable_features = self._map_variable_features(verdict)
        accessory_compat = self._map_accessory_compatibility(verdict)

        return TraitBasedReport(
            verdict=verdict,
            application=application,
            suitability=suitability,
            clarifications=clarifications,
            reasoning_steps=reasoning_steps,
            graph_evidence=graph_evidence,
            product_pivot=product_pivot,
            variable_features=variable_features,
            accessory_compatibility=accessory_compat,
            physics_risks=physics_risks,
        )

    # -----------------------------------------------------------------
    # Application mapping
    # -----------------------------------------------------------------

    def _map_application(self, verdict: EngineVerdict) -> Optional[ApplicationMatch]:
        """Map detected stressor context to ApplicationMatch."""
        app_data = verdict.application_match
        if not app_data:
            # Try to infer from stressor with application_link detection
            for s in verdict.detected_stressors:
                if s.source_context and s.detection_method == "application_link":
                    return ApplicationMatch(
                        id=s.source_context.upper().replace(" ", "_"),
                        name=s.source_context,
                        keywords=s.matched_keywords or [],
                        matched_keyword=s.matched_keywords[0] if s.matched_keywords else s.source_context,
                        risks=[],
                        requirements=self._stressors_as_requirements(verdict),
                        match_method="Keyword Match",
                        confidence=s.confidence,
                    )
            return None

        return ApplicationMatch(
            id=app_data.get("id", ""),
            name=app_data.get("name", ""),
            keywords=app_data.get("keywords", []),
            matched_keyword=app_data.get("keywords", [""])[0] if app_data.get("keywords") else "",
            risks=self._stressors_as_risks(verdict),
            requirements=self._stressors_as_requirements(verdict),
            match_method="Keyword Match",
            confidence=1.0,
        )

    def _stressors_as_risks(self, verdict: EngineVerdict) -> list[dict]:
        """Map detected stressors to risk dicts for ApplicationMatch."""
        risks = []
        for s in verdict.detected_stressors:
            risks.append({
                "name": s.name,
                "description": s.description,
                "id": s.id,
            })
        return risks

    def _stressors_as_requirements(self, verdict: EngineVerdict) -> list[dict]:
        """Map DEMANDS_TRAIT rules to requirement dicts for ApplicationMatch."""
        reqs = []
        seen = set()
        for rule in verdict.active_causal_rules:
            if rule.rule_type == "DEMANDS_TRAIT" and rule.trait_id not in seen:
                seen.add(rule.trait_id)
                reqs.append({
                    "name": rule.trait_name,
                    "reason": rule.explanation or f"{rule.stressor_name} requires {rule.trait_name}",
                    "id": rule.trait_id,
                })
        return reqs

    # -----------------------------------------------------------------
    # Suitability mapping
    # -----------------------------------------------------------------

    def _map_suitability(self, verdict: EngineVerdict) -> SuitabilityResult:
        """Map trait matches and vetoes to SuitabilityResult."""
        warnings = []
        required_materials = []

        # Map vetoed products to CRITICAL warnings (physics-based narrative from graph)
        for tm in verdict.vetoed_products:
            for reason in tm.veto_reasons:
                warnings.append(RiskWarning(
                    risk_name=f"Engineering Veto: {tm.product_family_name}",
                    risk_type="TRAIT_VETO",
                    severity="CRITICAL",
                    description=reason,
                    consequence=(
                        f"{tm.product_family_name} cannot safely operate in this environment"
                    ),
                    mitigation=(
                        f"Use {verdict.auto_pivot_name}" if verdict.auto_pivot_name
                        else "Select a product with the required traits"
                    ),
                    graph_path=(
                        f"(Stressor)-[:DEMANDS_TRAIT]->(Trait) "
                        f"NOT IN ({tm.product_family_name})-[:HAS_TRAIT]->()"
                    ),
                ))

        # Map non-critical missing traits to WARNING (physics from graph)
        rec = verdict.recommended_product
        if rec and rec.traits_missing:
            for trait_name in rec.traits_missing:
                # Find the rule severity
                rule = next(
                    (r for r in verdict.active_causal_rules
                     if r.trait_name == trait_name and r.rule_type == "DEMANDS_TRAIT"),
                    None
                )
                if rule and rule.severity != "CRITICAL":
                    warnings.append(RiskWarning(
                        risk_name=f"Gap: {trait_name}",
                        risk_type="TRAIT_GAP",
                        severity=rule.severity,
                        description=(
                            rule.explanation
                            or f"{rec.product_family_name} lacks {trait_name}"
                        ),
                        consequence=(
                            f"{rec.product_family_name} does not provide {trait_name} "
                            f"(needed for {rule.stressor_name})"
                        ),
                        mitigation="Consider products with this trait",
                        graph_path=f"({rule.stressor_id})-[:DEMANDS_TRAIT]->({rule.trait_id})",
                    ))

        # Map neutralized traits to WARNING (physics from graph)
        if rec and rec.traits_neutralized:
            for trait_name in rec.traits_neutralized:
                rule = next(
                    (r for r in verdict.active_causal_rules
                     if r.trait_name == trait_name and r.rule_type == "NEUTRALIZED_BY"),
                    None
                )
                if rule:
                    warnings.append(RiskWarning(
                        risk_name=f"Neutralized: {trait_name}",
                        risk_type="TRAIT_NEUTRALIZATION",
                        severity=rule.severity,
                        description=(
                            rule.explanation
                            or f"{trait_name} on {rec.product_family_name} is "
                            f"neutralized by {rule.stressor_name}"
                        ),
                        consequence=(
                            f"{rec.product_family_name}'s {trait_name} is rendered "
                            f"ineffective by {rule.stressor_name}"
                        ),
                        mitigation="Consider alternative technology",
                        graph_path=(
                            f"({rule.trait_id})-[:NEUTRALIZED_BY]->({rule.stressor_id})"
                        ),
                    ))

        # Map corrosion-related DEMANDS_TRAIT to MaterialRequirement
        # Maps trait → minimum corrosion class (NOT a specific material)
        # Multiple materials can satisfy each class — the retriever resolves
        # to available materials for the specific product family.
        corrosion_trait_classes = {
            "TRAIT_CORROSION_RESISTANCE_C5": "C5",
            "TRAIT_CORROSION_RESISTANCE_C5M": "C5.1",
            "TRAIT_CORROSION_RESISTANCE_C3": "C3",
        }
        for rule in verdict.active_causal_rules:
            if rule.rule_type == "DEMANDS_TRAIT" and rule.trait_id in corrosion_trait_classes:
                corr_class = corrosion_trait_classes[rule.trait_id]
                required_materials.append(MaterialRequirement(
                    material_code=corr_class,  # class, not specific material
                    material_name=f"Any material rated {corr_class} or higher",
                    corrosion_class=corr_class,
                    reason=f"{rule.stressor_name}: {rule.explanation}",
                ))

        # v2.0: Map gate evaluations to warnings
        for ge in verdict.gate_evaluations:
            if ge.state == "VALIDATION_REQUIRED":
                missing_keys = [p.get("property_key", "?") for p in ge.missing_parameters]
                warnings.append(RiskWarning(
                    risk_name=f"Gate: {ge.gate_name}",
                    risk_type="GATE_VALIDATION_REQUIRED",
                    severity="INFO",
                    description=(
                        f"Gate {ge.gate_name} requires data before evaluation: "
                        f"{', '.join(missing_keys)}"
                    ),
                    consequence="Cannot confirm or deny physics constraint without this data",
                    mitigation="Provide the requested parameters",
                    graph_path=(
                        f"(LogicGate:{ge.gate_id})-[:MONITORS]->"
                        f"(Stressor:{ge.stressor_id})"
                    ),
                ))
            elif ge.state == "FIRED":
                warnings.append(RiskWarning(
                    risk_name=f"Gate: {ge.gate_name}",
                    risk_type="GATE_FIRED",
                    severity="CRITICAL",
                    description=ge.physics_explanation,
                    consequence=f"Physics constraint confirmed by {ge.stressor_name}",
                    mitigation="Non-negotiable — follow engineering recommendation",
                    graph_path=(
                        f"(LogicGate:{ge.gate_id})-[:MONITORS]->"
                        f"(Stressor:{ge.stressor_id})"
                    ),
                ))

        # v2.0: Map constraint overrides to warnings
        for co in verdict.constraint_overrides:
            warnings.append(RiskWarning(
                risk_name=f"Constraint: {co.property_key}",
                risk_type="HARD_CONSTRAINT_OVERRIDE",
                severity="WARNING",
                description=co.error_msg,
                consequence=(
                    f"{co.property_key} auto-corrected from "
                    f"{co.original_value} to {co.corrected_value}"
                ),
                mitigation="Value has been auto-corrected to meet physical requirements",
                graph_path=(
                    f"(ProductFamily:{co.item_id})-[:HAS_HARD_CONSTRAINT]->"
                    f"(HardConstraint:{co.property_key})"
                ),
            ))

        # v2.1: Map blocked accessories to CRITICAL warnings
        for av in verdict.accessory_validations:
            if not av.is_compatible:
                alts = ", ".join(av.compatible_alternatives) if av.compatible_alternatives else "None listed"
                warnings.append(RiskWarning(
                    risk_name=f"Accessory: {av.accessory_code}",
                    risk_type="ACCESSORY_BLOCKED",
                    severity="CRITICAL",
                    description=(
                        f"{av.accessory_code} ({av.accessory_name}) is NOT compatible "
                        f"with {av.product_family_id}"
                    ),
                    consequence=av.reason or "No explicit compatibility in engineering data",
                    mitigation=f"Compatible alternatives: {alts}",
                    graph_path=(
                        f"({av.product_family_id})-[:HAS_COMPATIBLE_ACCESSORY]-/->({av.accessory_code})"
                    ),
                ))

        # v3.0: Map installation constraint violations to CRITICAL warnings
        for iv in verdict.installation_violations:
            # v3.3: Include verified alternatives in mitigation text
            alt_names = [a.product_family_name for a in getattr(iv, 'alternatives', [])[:3]]
            mitigation = (
                f"Verified alternatives: {', '.join(alt_names)}"
                if alt_names
                else "Reconfigure installation space, product, or material to satisfy constraint"
            )
            warnings.append(RiskWarning(
                risk_name=f"Installation: {iv.constraint_id}",
                risk_type="INSTALLATION_BLOCKED",
                severity=iv.severity,
                description=iv.error_msg,
                consequence=(
                    f"Constraint type: {iv.constraint_type}. "
                    + "; ".join(f"{k}={v}" for k, v in iv.details.items())
                ),
                mitigation=mitigation,
                graph_path=f"(ProductFamily)-[:HAS_INSTALLATION_CONSTRAINT]->({iv.constraint_id})",
            ))

        # Assembly resolves the veto: product IS suitable when used with protector
        # Installation blocks override everything — product is NOT suitable
        is_suitable = (verdict.is_assembly or not verdict.has_veto) and not verdict.has_installation_block
        return SuitabilityResult(
            is_suitable=is_suitable,
            warnings=warnings,
            required_materials=required_materials,
            product_vulnerabilities=[],
        )

    # -----------------------------------------------------------------
    # Clarification mapping
    # -----------------------------------------------------------------

    def _map_clarifications(self, verdict: EngineVerdict) -> list[ClarificationQuestion]:
        """Map verdict clarification dicts to ClarificationQuestion objects."""
        if verdict.has_installation_block:
            return []  # Suppress clarifications when installation is BLOCKED
        questions = []
        for q in verdict.clarification_questions:
            questions.append(ClarificationQuestion(
                param_id=q.get("param_id", ""),
                param_name=q.get("param_name", ""),
                question_id=q.get("question_id", ""),
                question_text=q.get("question_text", ""),
                intent=q.get("intent", "sizing"),
                priority=q.get("priority", 1),
                triggered_by=q.get("triggered_by"),
            ))
        return questions

    # -----------------------------------------------------------------
    # Product Pivot mapping
    # -----------------------------------------------------------------

    def _map_pivot(self, verdict: EngineVerdict) -> Optional[ProductPivot]:
        """Map veto + auto_pivot to ProductPivot.

        When an assembly is built, no pivot is needed — the user's product
        is kept as the TARGET stage, protected by PROTECTOR stage(s).
        """
        if verdict.is_assembly:
            return None  # Assembly resolves the veto; no pivot needed
        if not verdict.has_veto or not verdict.auto_pivot_name:
            return None

        # Find the vetoed product for details
        vetoed = verdict.vetoed_products[0] if verdict.vetoed_products else None
        veto_reason = verdict.veto_reason or "Engineering veto"

        # Build physics explanation from graph-stored rule explanations
        critical_rules = [
            r for r in verdict.active_causal_rules
            if r.severity == "CRITICAL"
        ]
        physics_parts = [
            rule.explanation for rule in critical_rules[:3]
            if rule.explanation
        ]

        physics_explanation = "; ".join(physics_parts) if physics_parts else veto_reason

        # Get the recommended product's key trait
        rec = verdict.recommended_product
        required_feature = ""
        if rec and rec.traits_present:
            required_feature = ", ".join(rec.traits_present[:2])

        original = vetoed.product_family_name if vetoed else "Unknown"

        return ProductPivot(
            original_product=original,
            pivoted_to=verdict.auto_pivot_name,
            reason=veto_reason,
            physics_explanation=physics_explanation,
            user_misconception=None,
            required_feature=required_feature,
        )

    # -----------------------------------------------------------------
    # Physics risks mapping
    # -----------------------------------------------------------------

    def _map_physics_risks(self, verdict: EngineVerdict) -> list[UnmitigatedPhysicsRisk]:
        """Map vetoed products to UnmitigatedPhysicsRisk objects."""
        risks = []

        for tm in verdict.vetoed_products:
            # Find the CRITICAL rule that caused this veto
            for reason in tm.veto_reasons:
                # Find stressor and trait from the rules
                rule = next(
                    (r for r in verdict.active_causal_rules
                     if r.severity == "CRITICAL"
                     and (r.trait_name in reason or r.stressor_name in reason)),
                    None
                )
                if not rule:
                    continue

                # Find source stressor for environment info
                stressor = next(
                    (s for s in verdict.detected_stressors
                     if s.id == rule.stressor_id),
                    None
                )

                safe_alts = []
                for m in (verdict.ranked_products or []):
                    if not m.vetoed and m.product_family_id != tm.product_family_id:
                        safe_alts.append(m.product_family_name)
                        if len(safe_alts) >= 3:
                            break

                risks.append(UnmitigatedPhysicsRisk(
                    environment_id=rule.stressor_id,
                    environment_name=stressor.name if stressor else rule.stressor_name,
                    risk_id=rule.trait_id,
                    risk_name=rule.explanation or f"Missing {rule.trait_name}",
                    risk_severity=rule.severity,
                    physics_explanation=rule.explanation,
                    consequence=(
                        f"{tm.product_family_name} cannot safely operate "
                        f"under {rule.stressor_name}"
                    ),
                    user_misconception=None,
                    required_feature=rule.trait_name,
                    mitigation_mechanism=rule.trait_name,
                    safe_alternatives=safe_alts,
                    blocked_product=tm.product_family_name,
                ))

        return risks

    # -----------------------------------------------------------------
    # Variable features mapping (v2.1)
    # -----------------------------------------------------------------

    def _map_variable_features(self, verdict: EngineVerdict) -> list[VariableFeature]:
        """Map MissingParameter list to VariableFeature objects."""
        features = []
        for mp in verdict.missing_parameters:
            features.append(VariableFeature(
                feature_id=mp.feature_id,
                feature_name=mp.feature_name,
                parameter_name=mp.parameter_name,
                question=mp.question,
                why_needed=mp.why_needed,
                options=mp.options,
                is_resolved=False,
            ))
        return features

    # -----------------------------------------------------------------
    # Accessory compatibility mapping (v2.1)
    # -----------------------------------------------------------------

    def _map_accessory_compatibility(self, verdict: EngineVerdict) -> list[AccessoryCompatibilityResult]:
        """Map AccessoryValidation list to AccessoryCompatibilityResult objects."""
        results = []
        for av in verdict.accessory_validations:
            results.append(AccessoryCompatibilityResult(
                accessory_code=av.accessory_code,
                accessory_name=av.accessory_name,
                product_family=av.product_family_id.replace("FAM_", ""),
                is_compatible=av.is_compatible,
                status=av.status,
                reason=av.reason,
                compatible_alternatives=av.compatible_alternatives,
            ))
        return results

    # -----------------------------------------------------------------
    # Reasoning steps and evidence
    # -----------------------------------------------------------------

    def _map_reasoning_steps(self, verdict: EngineVerdict) -> list[dict]:
        """Map reasoning trace to reasoning_steps dicts."""
        return verdict.reasoning_trace

    def _map_evidence(self, verdict: EngineVerdict) -> list[dict]:
        """Build graph evidence trail from stressors and rules."""
        evidence = []

        for s in verdict.detected_stressors:
            evidence.append({
                "type": "STRESSOR_DETECTED",
                "description": (
                    f"Detected stressor: {s.name} "
                    f"via {s.detection_method} (confidence: {s.confidence:.2f})"
                ),
                "path": f"(Query)-[:{s.detection_method.upper()}]->(Stressor:{s.id})",
            })

        for rule in verdict.active_causal_rules:
            if rule.severity in ("CRITICAL", "WARNING"):
                evidence.append({
                    "type": "CAUSAL_RULE",
                    "description": (
                        f"[{rule.severity}] {rule.rule_type}: "
                        f"{rule.stressor_name} → {rule.trait_name}: {rule.explanation}"
                    ),
                    "path": (
                        f"({rule.stressor_id})-[:{rule.rule_type}]->"
                        f"({rule.trait_id})"
                    ),
                })

        if verdict.is_assembly and verdict.assembly:
            stage_desc = " → ".join(f"{s.product_family_name}" for s in verdict.assembly)
            evidence.append({
                "type": "ASSEMBLY_BUILT",
                "description": (
                    f"Multi-stage assembly: {stage_desc}. "
                    f"{verdict.assembly_rationale or ''}"
                ),
                "path": " → ".join(
                    f"(ProductFamily:{s.product_family_id})" for s in verdict.assembly
                ),
            })
        elif verdict.has_veto and verdict.auto_pivot_name:
            evidence.append({
                "type": "PRODUCT_PIVOT",
                "description": (
                    f"Engineering veto applied. "
                    f"Pivoted to {verdict.auto_pivot_name}: {verdict.veto_reason}"
                ),
                "path": f"(Veto)-[:PIVOT_TO]->(ProductFamily:{verdict.auto_pivot_to})",
            })

        # v2.0: Gate evaluations
        for ge in verdict.gate_evaluations:
            evidence.append({
                "type": f"GATE_{ge.state}",
                "description": (
                    f"LogicGate {ge.gate_name} [{ge.state}]: monitors {ge.stressor_name}"
                    + (f" — missing: {', '.join(p.get('property_key', '') for p in ge.missing_parameters)}"
                       if ge.state == "VALIDATION_REQUIRED" else "")
                ),
                "path": (
                    f"(LogicGate:{ge.gate_id})-[:MONITORS]->"
                    f"(Stressor:{ge.stressor_id})"
                ),
            })

        # v2.0: Constraint overrides
        for co in verdict.constraint_overrides:
            evidence.append({
                "type": "HARD_CONSTRAINT_OVERRIDE",
                "description": (
                    f"Constraint override: {co.property_key} "
                    f"{co.original_value} → {co.corrected_value}. {co.error_msg}"
                ),
                "path": (
                    f"(ProductFamily:{co.item_id})-[:HAS_HARD_CONSTRAINT]->"
                    f"(HardConstraint:{co.property_key})"
                ),
            })

        # v2.1: Blocked accessories
        for av in verdict.accessory_validations:
            if not av.is_compatible:
                evidence.append({
                    "type": "ACCESSORY_BLOCKED",
                    "description": (
                        f"Accessory {av.accessory_code} ({av.accessory_name}) BLOCKED "
                        f"with {av.product_family_id}. "
                        f"{av.reason or 'No compatibility relationship in graph.'}"
                    ),
                    "path": (
                        f"({av.product_family_id})-[:HAS_COMPATIBLE_ACCESSORY]-/->({av.accessory_code})"
                    ),
                })

        # v2.1: Missing parameters
        if verdict.missing_parameters:
            evidence.append({
                "type": "VARIANCE_CHECK",
                "description": (
                    f"{len(verdict.missing_parameters)} unresolved parameter(s): "
                    + ", ".join(mp.parameter_name for mp in verdict.missing_parameters)
                ),
                "path": "(:ProductFamily)-[:HAS_VARIABLE_FEATURE]->(:VariableFeature)",
            })

        return evidence
