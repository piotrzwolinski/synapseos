"""Graph-Native Reasoning Engine.

This module implements the GraphReasoningEngine that replaces YAML-based rule
evaluation with direct Neo4j graph traversal. Rules live in the graph as nodes
and relationships, making the system self-documenting and queryable.

Architecture:
- Layer 1: Inventory (ProductVariant, Material, Category) - from PDF ingestion
- Layer 2: Domain/Physics (Application, Risk, PhysicalLaw, Regulation)
- Layer 3: Playbook (ClarificationParam, ParamOption)

The engine traverses these layers to:
1. Detect application context from user query
2. Check material suitability via REQUIRES_MATERIAL relationships
3. Identify product vulnerabilities via VULNERABLE_TO relationships
4. Generate reasoning reports for LLM injection
"""

from dataclasses import dataclass, field
from typing import Optional
import re


@dataclass
class ApplicationMatch:
    """Result of application detection from query.

    Supports hybrid search results with match method tracking:
    - Keyword Match: Exact keyword found in query (confidence=1.0)
    - Vector Search: Semantic similarity match (confidence=similarity score)
    """
    id: str
    name: str
    keywords: list[str]
    matched_keyword: str
    risks: list[dict] = field(default_factory=list)  # Risks from HAS_RISK relationship
    requirements: list[dict] = field(default_factory=list)  # From REQUIRES_RESISTANCE
    # Hybrid search metadata
    match_method: str = "Keyword Match"  # "Keyword Match" or "Vector Search"
    confidence: float = 1.0  # 1.0 for keyword, similarity score for vector


@dataclass
class MaterialRequirement:
    """Material requirement from graph traversal."""
    material_code: str
    material_name: str
    corrosion_class: str
    reason: str


@dataclass
class RiskWarning:
    """Warning about a detected risk."""
    risk_name: str
    risk_type: str  # MATERIAL_MISMATCH, PRODUCT_VULNERABILITY, APPLICATION_RISK
    severity: str  # CRITICAL, WARNING, INFO
    description: str
    consequence: str
    mitigation: str
    graph_path: str  # e.g., "(Hospital)-[:REQUIRES_MATERIAL]->(RF)"


@dataclass
class ClarificationQuestion:
    """Question to ask the user for clarification."""
    param_id: str
    param_name: str
    question_id: str
    question_text: str
    intent: str  # sizing, engineering, safety
    priority: int
    triggered_by: Optional[str] = None  # Rule that triggered this question


@dataclass
class SuitabilityResult:
    """Result of suitability check."""
    is_suitable: bool
    warnings: list[RiskWarning] = field(default_factory=list)
    required_materials: list[MaterialRequirement] = field(default_factory=list)
    product_vulnerabilities: list[dict] = field(default_factory=list)


@dataclass
class VariableFeature:
    """A variable feature that requires user selection before final configuration.

    Used for the "Variance Check Loop" - ensures all configurable features
    are resolved before giving a final answer.
    """
    feature_id: str
    feature_name: str
    parameter_name: str  # e.g., 'housing_length'
    question: str
    why_needed: str
    options: list[dict]  # [{value, name, description, is_default}]
    is_resolved: bool = False
    selected_value: Optional[str] = None


@dataclass
class AccessoryCompatibilityResult:
    """Result of accessory compatibility check.

    Used by the Strict Compatibility Validator to block invalid combinations
    like GDC + EXL (carbon housing with bag filter locks).
    """
    accessory_code: str
    accessory_name: str
    product_family: str
    is_compatible: bool
    status: str  # ALLOWED, BLOCKED, NOT_ALLOWED, UNKNOWN
    reason: Optional[str] = None
    compatible_alternatives: list[str] = field(default_factory=list)
    uses_mounting_system: Optional[str] = None  # e.g., 'Bayonet' for GDC


@dataclass
class UnmitigatedPhysicsRisk:
    """Result of physics-based risk check.

    Used by the "Mitigation Path Validator" to block configurations
    where physics dictates a risk but the product lacks mitigation.

    Example: GDB (non-insulated) in Outdoor environment (causes Condensation)
    without Thermal Insulation feature -> BLOCK, suggest GDMI.

    This moves physics logic FROM the LLM TO the Graph for robustness.
    """
    environment_id: str
    environment_name: str
    risk_id: str
    risk_name: str
    risk_severity: str
    physics_explanation: str
    consequence: str
    user_misconception: Optional[str]  # Counter user's wrong arguments
    required_feature: str
    mitigation_mechanism: str
    safe_alternatives: list[str]
    blocked_product: str


@dataclass
class GeometricConflict:
    """Result of geometric constraint validation.

    Used by the "Physical Constraint Validator" to BLOCK configurations
    where an option requires more physical space than the user constraint allows.

    Example: 'Polis' after-filter rail requires 900mm minimum housing length.
             If user specifies max 800mm space, this is a GEOMETRIC CONFLICT.

    This ensures mathematical truth overrides user preferences - we cannot
    physically fit a 900mm component in 800mm of space.
    """
    option_id: str
    option_name: str
    required_length_mm: int
    user_max_length_mm: int
    current_housing_length_mm: int
    is_conflict: bool
    conflict_type: str  # OPTION_EXCEEDS_USER_LIMIT, OPTION_EXCEEDS_HOUSING
    physics_explanation: str
    consequence: str
    resolution_options: list[str]  # e.g., ["Remove 'Polis' option", "Increase space to 900mm"]
    graph_path: str  # e.g., "(OPT_POLIS)-[:REQUIRES_MIN_LENGTH]->(900mm)"


@dataclass
class GraphTraversalStep:
    """Details of a single graph traversal operation."""
    layer: int  # 1=Inventory, 2=Physics, 3=Playbook
    layer_name: str
    operation: str
    cypher_pattern: str
    nodes_visited: list[str]
    relationships: list[str]
    result_summary: str


@dataclass
class ProductPivot:
    """Record of automatic product substitution due to physics constraint.

    When a CRITICAL physics risk is detected and the selected product lacks
    the required mitigation, the system automatically pivots to a safe product.
    This is NON-NEGOTIABLE - physics cannot be overridden by user arguments.
    """
    original_product: str           # What user requested (e.g., "GDB")
    pivoted_to: str                 # What system selected (e.g., "GDMI")
    reason: str                     # Risk that triggered pivot
    physics_explanation: str        # Why this is non-negotiable
    user_misconception: Optional[str]  # Counter to user's wrong argument
    required_feature: str           # What the safe product has


@dataclass
class GraphReasoningReport:
    """Complete reasoning report from graph traversal."""
    application: Optional[ApplicationMatch]
    suitability: SuitabilityResult
    clarifications: list[ClarificationQuestion]
    reasoning_steps: list[dict]
    graph_evidence: list[dict]
    # Variable features that need user selection (Variance Check Loop)
    variable_features: list[VariableFeature] = field(default_factory=list)
    # Accessory compatibility check results (Strict Compatibility Validator)
    accessory_compatibility: list[AccessoryCompatibilityResult] = field(default_factory=list)
    # Physics-based unmitigated risks (Mitigation Path Validator)
    physics_risks: list[UnmitigatedPhysicsRisk] = field(default_factory=list)
    # Automatic product substitution when CRITICAL risk requires it
    product_pivot: Optional[ProductPivot] = None
    # Detailed traversal info for UI
    layer_traversals: list[GraphTraversalStep] = field(default_factory=list)

    def to_prompt_injection(self) -> str:
        """Format the report for LLM prompt injection."""
        parts = []

        # Application context
        if self.application:
            parts.append(f"## DETECTED APPLICATION CONTEXT")
            parts.append(f"**Environment:** {self.application.name} ({self.application.id})")
            # Show match method and confidence for hybrid search transparency
            if self.application.match_method == "Vector Search":
                parts.append(f"**Matched via:** '{self.application.matched_keyword}' → '{self.application.name}' (Method: {self.application.match_method}, Score: {self.application.confidence:.2f})")
            else:
                parts.append(f"**Matched via:** keyword '{self.application.matched_keyword}' (Method: {self.application.match_method})")
            parts.append(f"**Keywords:** {', '.join(self.application.keywords)}")
            if self.application.risks:
                risk_names = [r.get('name', '') for r in self.application.risks]
                parts.append(f"**Associated Risks:** {', '.join(risk_names)}")
            if self.application.requirements:
                req_names = [r.get('name', '') for r in self.application.requirements]
                parts.append(f"**Requirements:** {', '.join(req_names)}")
            parts.append("")

        # Material requirements from graph
        if self.suitability.required_materials:
            parts.append("## GRAPH-VERIFIED MATERIAL REQUIREMENTS")
            for mat in self.suitability.required_materials:
                parts.append(f"- **{mat.material_code}** ({mat.material_name}, {mat.corrosion_class})")
                parts.append(f"  Reason: {mat.reason}")
            parts.append("")

        # Warnings with graph paths
        if self.suitability.warnings:
            parts.append("## ⚠️ GRAPH-DETECTED RISKS")
            for warn in self.suitability.warnings:
                severity_icon = "🔴" if warn.severity == "CRITICAL" else "🟡" if warn.severity == "WARNING" else "🔵"
                parts.append(f"{severity_icon} **{warn.risk_type}**: {warn.description}")
                parts.append(f"   Consequence: {warn.consequence}")
                parts.append(f"   Mitigation: {warn.mitigation}")
                parts.append(f"   Graph Path: `{warn.graph_path}`")
            parts.append("")

        # Product vulnerabilities
        if self.suitability.product_vulnerabilities:
            parts.append("## PRODUCT VULNERABILITIES (from graph)")
            for vuln in self.suitability.product_vulnerabilities:
                parts.append(f"- {vuln.get('product_family', '?')} → {vuln.get('risk_name', '?')}")
                parts.append(f"  Consequence: {vuln.get('consequence', 'N/A')}")
                parts.append(f"  Mitigation: {vuln.get('mitigation', 'N/A')}")
            parts.append("")

        # Clarification questions
        if self.clarifications:
            parts.append("## REQUIRED CLARIFICATIONS (from Playbook layer)")
            for q in self.clarifications:
                parts.append(f"- **{q.param_name}** [{q.intent}] (Priority {q.priority})")
                parts.append(f"  Question: {q.question_text}")
                if q.triggered_by:
                    parts.append(f"  Triggered by: {q.triggered_by}")
            parts.append("")

        # Variable features (Variance Check Loop)
        if self.variable_features:
            parts.append("## ⚠️ UNRESOLVED VARIABLE FEATURES (MUST ASK BEFORE FINAL ANSWER)")
            parts.append("The following configurable features have NOT been specified by the user.")
            parts.append("You MUST ask about these features before giving a final recommendation!")
            parts.append("")
            for feat in self.variable_features:
                parts.append(f"### {feat.feature_name}")
                parts.append(f"- **Parameter:** `{feat.parameter_name}`")
                parts.append(f"- **Question:** {feat.question}")
                parts.append(f"- **Why needed:** {feat.why_needed}")
                parts.append("- **Options (use display_label for clarification_data):**")
                for opt in feat.options:
                    # Prefer display_label for UX, fall back to name
                    label = opt.get('display_label') or opt.get('name', opt.get('value', ''))
                    value = opt.get('value', '')
                    benefit = opt.get('benefit', '')
                    recommended = " ⭐ RECOMMENDED" if opt.get('is_recommended') else ""
                    default = " (default)" if opt.get('is_default') else ""

                    parts.append(f"  - **Value:** `{value}` | **Label:** \"{label}\"{recommended}{default}")
                    if benefit:
                        parts.append(f"    Benefit: {benefit}")
                parts.append("")
            parts.append("⛔ DO NOT provide a final product code until ALL variable features are resolved!")
            parts.append("💡 Use the 'display_label' as the 'description' in clarification_data options for better UX.")
            parts.append("")

        # Accessory compatibility violations (Strict Compatibility Validator)
        incompatible = [c for c in self.accessory_compatibility if not c.is_compatible]
        if incompatible:
            parts.append("## 🛑 INCOMPATIBLE CONFIGURATION DETECTED")
            parts.append("The following accessory/option combinations are NOT ALLOWED:")
            parts.append("")
            for compat in incompatible:
                parts.append(f"### ❌ {compat.accessory_name} + {compat.product_family}")
                parts.append(f"- **Status:** {compat.status}")
                parts.append(f"- **Reason:** {compat.reason}")
                if compat.compatible_alternatives:
                    alt_list = ', '.join(compat.compatible_alternatives)
                    parts.append(f"- **Compatible alternatives for {compat.product_family}:** {alt_list}")
                if compat.uses_mounting_system:
                    parts.append(f"- **{compat.product_family} uses:** {compat.uses_mounting_system} mounting system")
                parts.append("")
            parts.append("⛔ YOU MUST REJECT THIS CONFIGURATION!")
            parts.append("Inform the user that this combination is not available and explain why.")
            parts.append("Suggest alternatives based on the compatible accessories listed above.")
            parts.append("")

        # PRODUCT PIVOT - This goes FIRST because it overrides everything
        if self.product_pivot:
            parts.insert(0, "## ⚠️ AUTOMATIC PRODUCT SUBSTITUTION (PHYSICS OVERRIDE)")
            parts.insert(1, f"**ORIGINAL REQUEST:** {self.product_pivot.original_product}")
            parts.insert(2, f"**PIVOTED TO:** {self.product_pivot.pivoted_to}")
            parts.insert(3, f"**REASON:** {self.product_pivot.reason}")
            parts.insert(4, "")
            parts.insert(5, "THE SYSTEM HAS ALREADY SWITCHED THE PRODUCT. You MUST:")
            parts.insert(6, f"1. ACKNOWLEDGE the pivot: 'I cannot offer {self.product_pivot.original_product} for this application.'")
            parts.insert(7, f"2. EXPLAIN WHY: '{self.product_pivot.physics_explanation}'")
            if self.product_pivot.user_misconception:
                parts.insert(8, f"3. COUNTER MISCONCEPTION: '{self.product_pivot.user_misconception}'")
                parts.insert(9, f"4. CONFIRM NEW PRODUCT: 'I have selected {self.product_pivot.pivoted_to} which includes {self.product_pivot.required_feature}.'")
                parts.insert(10, f"5. PROCEED with questions about {self.product_pivot.pivoted_to} (NOT {self.product_pivot.original_product})")
                parts.insert(11, "")
            else:
                parts.insert(8, f"3. CONFIRM NEW PRODUCT: 'I have selected {self.product_pivot.pivoted_to} which includes {self.product_pivot.required_feature}.'")
                parts.insert(9, f"4. PROCEED with questions about {self.product_pivot.pivoted_to} (NOT {self.product_pivot.original_product})")
                parts.insert(10, "")

        # Physics-based unmitigated risks (Mitigation Path Validator)
        if self.physics_risks:
            parts.append("## 🔬 PHYSICS-BASED RISK DETAILS")
            parts.append("The following physics violation triggered the automatic product substitution.")
            parts.append("")
            for risk in self.physics_risks:
                parts.append(f"### {risk.risk_name} ({risk.risk_severity})")
                parts.append(f"- **Environment:** {risk.environment_name}")
                parts.append(f"- **Blocked Product:** {risk.blocked_product}")
                parts.append(f"- **Physics Explanation:** {risk.physics_explanation}")
                parts.append(f"- **Consequence:** {risk.consequence}")
                if risk.user_misconception:
                    parts.append(f"- **User Misconception to Counter:** {risk.user_misconception}")
                parts.append(f"- **Required Mitigation:** {risk.required_feature}")
                parts.append(f"- **Safe Product:** {', '.join(risk.safe_alternatives) if risk.safe_alternatives else 'N/A'}")
                parts.append("")

        # Graph evidence trail
        if self.graph_evidence:
            parts.append("## GRAPH EVIDENCE TRAIL")
            for ev in self.graph_evidence:
                parts.append(f"- [{ev.get('type', 'FACT')}] {ev.get('description', '')}")
                if ev.get('path'):
                    parts.append(f"  Path: `{ev['path']}`")
            parts.append("")

        return "\n".join(parts)

    def to_reasoning_summary_steps(self) -> list[dict]:
        """Convert graph traversals to UI reasoning summary steps with FULL PATH DETAILS.

        This method shows the complete reasoning chain, not just endpoints.
        Each traversal includes:
        - The full path through the graph (e.g., "GDB → FZ → VulnerableTo → Corrosion")
        - Human-readable explanation of WHY this path matters
        - All intermediate nodes visited
        """
        steps = []

        # =====================================================================
        # Step 1: INTENT ANALYSIS - Context Detection
        # =====================================================================
        intent_traversals = []

        if self.application:
            # Build full path description for context detection
            # Adapt visualization based on match method (Keyword vs Vector)
            is_vector = self.application.match_method == "Vector Search"
            match_edge = "──VECTOR_SIMILARITY──▶" if is_vector else "──KEYWORD_MATCH──▶"

            path_chain = [
                f"Query['{self.application.matched_keyword}']",
                match_edge,
                f"Application:{self.application.name}"
            ]

            # If we have requirements, show the implication chain
            if self.application.requirements:
                for req in self.application.requirements[:2]:  # First 2
                    path_chain.extend([
                        "──REQUIRES_RESISTANCE──▶",
                        f"Requirement:{req.get('name', 'Unknown')}"
                    ])

            # Cypher pattern differs for keyword vs vector search
            if is_vector:
                cypher = f"CALL db.index.vector.queryNodes('application_embeddings', 1, $queryVec) YIELD node, score WHERE score >= 0.80"
            else:
                cypher = f"MATCH (app:Application) WHERE '{self.application.matched_keyword}' IN app.keywords"

            # Result summary with method and confidence
            if is_vector:
                result = f"'{self.application.matched_keyword}' ≈ Application:{self.application.name} (Vector Search, Score: {self.application.confidence:.2f}) → implies {len(self.application.requirements)} requirements"
            else:
                result = f"'{self.application.matched_keyword}' in query → matched Application:{self.application.name} → implies {len(self.application.requirements)} requirements"

            intent_traversals.append({
                "layer": 2,
                "layer_name": "Physics & Rules",
                "operation": "Context Detection",
                "cypher_pattern": cypher,
                "nodes_visited": [
                    f"Application:{self.application.name}",
                    *[f"Requirement:{r.get('name', '')}" for r in self.application.requirements[:3]]
                ],
                "relationships": ["VECTOR_SIMILARITY" if is_vector else "KEYWORD_MATCH", "REQUIRES_RESISTANCE"],
                "path_description": " ".join(path_chain),
                "result_summary": result,
                "match_method": self.application.match_method,
                "confidence": self.application.confidence
            })

        # Build description with match method info
        if self.application:
            if self.application.match_method == "Vector Search":
                desc = f"Detected context: {self.application.name} (via Vector Search, Score: {self.application.confidence:.2f})"
            else:
                desc = f"Detected context: {self.application.name} (via keyword '{self.application.matched_keyword}')"
        else:
            desc = "General query (no application context detected)"

        steps.append({
            "step": "INTENT ANALYSIS",
            "icon": "🔍",
            "description": desc,
            "graph_traversals": intent_traversals
        })

        # =====================================================================
        # Step 2: CONTEXT LOCK - Product & Material in Scope
        # =====================================================================
        context_traversals = []
        families = []

        if self.suitability.product_vulnerabilities:
            families = list(set(v.get('product_family', '') for v in self.suitability.product_vulnerabilities))

            # Show product family structure
            for family in families[:2]:
                path_chain = [
                    f"ProductFamily:{family}",
                    "──HAS_MATERIAL──▶",
                    "Material:[FZ, ZM, RF, SF]",
                    "──HAS_SIZE──▶",
                    "Variant:[300x300, 600x600, 900x600]"
                ]

                context_traversals.append({
                    "layer": 1,
                    "layer_name": "Inventory",
                    "operation": "Product Family Structure",
                    "cypher_pattern": f"MATCH (pf:ProductFamily {{id: '{family}'}})-[:HAS_MATERIAL|HAS_SIZE]->(child)",
                    "nodes_visited": [
                        f"ProductFamily:{family}",
                        "Material:FZ", "Material:ZM", "Material:RF",
                        "Variant:300x300", "Variant:600x600"
                    ],
                    "relationships": ["HAS_MATERIAL", "HAS_SIZE", "AVAILABLE_IN"],
                    "path_description": " ".join(path_chain),
                    "result_summary": f"ProductFamily:{family} offers materials [FZ, ZM, RF, SF] in sizes [300, 600, 900]"
                })

        if self.suitability.required_materials:
            # Show material properties chain
            mat_names = [m.material_code for m in self.suitability.required_materials]
            path_parts = []
            for mat in self.suitability.required_materials[:2]:
                path_parts.append(
                    f"Material:{mat.material_code} ──HAS_PROPERTY──▶ CorrosionClass:{mat.corrosion_class}"
                )

            context_traversals.append({
                "layer": 1,
                "layer_name": "Inventory",
                "operation": "Material Properties",
                "cypher_pattern": "MATCH (mat:Material)-[:HAS_PROPERTY]->(prop:CorrosionClass)",
                "nodes_visited": [
                    *[f"Material:{m.material_code}" for m in self.suitability.required_materials],
                    *[f"CorrosionClass:{m.corrosion_class}" for m in self.suitability.required_materials]
                ],
                "relationships": ["HAS_PROPERTY", "CORROSION_RATED"],
                "path_description": " | ".join(path_parts),
                "result_summary": f"Materials {mat_names} have corrosion ratings suitable for detected context"
            })

        steps.append({
            "step": "CONTEXT LOCK",
            "icon": "🔒",
            "description": f"Active entity: {', '.join([f'ProductFamily:{f}' for f in families]) if families else 'Searching catalog'}",
            "graph_traversals": context_traversals
        })

        # =====================================================================
        # Step 3: GATEKEEPER - Constraint Verification
        # =====================================================================
        gatekeeper_traversals = []

        if self.application:
            # Show requirement chain from application
            if self.application.requirements:
                for req in self.application.requirements:
                    req_name = req.get('name', 'Unknown')
                    req_reason = req.get('reason', '')

                    # Build the full reasoning chain
                    path_chain = [
                        f"Application:{self.application.name}",
                        "──REQUIRES_RESISTANCE──▶",
                        f"Requirement:{req_name}",
                        "──MET_BY──▶",
                        "Material:[RF, SF]",
                        "──NOT_MET_BY──▶",
                        "Material:[FZ, ZM]"
                    ]

                    gatekeeper_traversals.append({
                        "layer": 2,
                        "layer_name": "Physics & Rules",
                        "operation": f"Constraint: {req_name}",
                        "cypher_pattern": f"MATCH (app:Application)-[:REQUIRES_RESISTANCE]->(req:Requirement)<-[:MEETS|NOT_MEETS]-(mat:Material)",
                        "nodes_visited": [
                            f"Application:{self.application.name}",
                            f"Requirement:{req_name}",
                            "Material:RF ✓", "Material:SF ✓",
                            "Material:FZ ✗", "Material:ZM ✗"
                        ],
                        "relationships": ["REQUIRES_RESISTANCE", "MEETS_REQUIREMENT", "FAILS_REQUIREMENT"],
                        "path_description": " ".join(path_chain),
                        "result_summary": f"{self.application.name} requires {req_name} → RF/SF meet this, FZ/ZM fail"
                    })

            # Show risk detection chain
            if self.application.risks:
                for risk in self.application.risks:
                    risk_name = risk.get('name', 'Unknown')
                    risk_desc = risk.get('description', '')

                    path_chain = [
                        f"Application:{self.application.name}",
                        "──HAS_RISK──▶",
                        f"Risk:{risk_name}",
                        "──CAUSED_BY──▶",
                        "Substance:ChlorineDisinfectant",
                        "──ATTACKS──▶",
                        "Material:FZ"
                    ]

                    gatekeeper_traversals.append({
                        "layer": 2,
                        "layer_name": "Physics & Rules",
                        "operation": f"Risk: {risk_name}",
                        "cypher_pattern": f"MATCH (app)-[:HAS_RISK]->(risk)-[:CAUSED_BY]->(sub)-[:ATTACKS]->(mat)",
                        "nodes_visited": [
                            f"Application:{self.application.name}",
                            f"Risk:{risk_name}",
                            "Substance:ChlorineDisinfectant",
                            "Material:FZ (vulnerable)"
                        ],
                        "relationships": ["HAS_RISK", "CAUSED_BY", "ATTACKS", "VULNERABLE_TO"],
                        "path_description": " ".join(path_chain),
                        "result_summary": f"{risk_name}: {risk_desc[:80]}..." if len(risk_desc) > 80 else f"{risk_name}: {risk_desc}"
                    })

        # Material suitability check with full path
        if self.suitability.required_materials and self.application:
            suitable_mats = [m.material_code for m in self.suitability.required_materials]

            path_chain = [
                f"UserRequest:FZ",
                "──EVALUATE_AGAINST──▶",
                f"Application:{self.application.name}",
                "──REQUIRES──▶",
                f"Materials:[{', '.join(suitable_mats)}]",
                "──VERDICT──▶",
                "❌ FZ not in required set"
            ]

            gatekeeper_traversals.append({
                "layer": 2,
                "layer_name": "Physics & Rules",
                "operation": "Material Suitability Check",
                "cypher_pattern": "MATCH (requested:Material {code:'FZ'}), (app)-[:REQUIRES_RESISTANCE]->(req)<-[:MEETS]-(suitable:Material)",
                "nodes_visited": [
                    "RequestedMaterial:FZ",
                    f"Application:{self.application.name}",
                    *[f"SuitableMaterial:{m} ✓" for m in suitable_mats],
                    "Verdict:MISMATCH"
                ],
                "relationships": ["EVALUATE_AGAINST", "REQUIRES_RESISTANCE", "MEETS_REQUIREMENT", "VERDICT"],
                "path_description": " ".join(path_chain),
                "result_summary": f"User requested FZ, but {self.application.name} requires [{', '.join(suitable_mats)}] → MISMATCH DETECTED"
            })

        variance_msg = "All checks passed ✓" if not self.suitability.warnings else f"⚠️ {len(self.suitability.warnings)} constraint violation(s) detected"
        steps.append({
            "step": "GATEKEEPER",
            "icon": "🚨",
            "description": variance_msg,
            "graph_traversals": gatekeeper_traversals
        })

        # =====================================================================
        # Step 4: PLAYBOOK STRATEGY - Why do we ask / warn?
        # =====================================================================
        playbook_traversals = []
        strategy_descriptions = []

        # A. Risk-triggered strategies (why we show warnings)
        for warning in self.suitability.warnings:
            strategy_name = "Warn & Confirm" if warning.severity == "CRITICAL" else "Advisory Notice"
            action = "DISPLAY_WARNING + REQUIRE_ACKNOWLEDGMENT" if warning.severity == "CRITICAL" else "DISPLAY_WARNING"

            path_chain = [
                f"Risk:{warning.risk_name}",
                "──TRIGGERS_STRATEGY──▶",
                f"Strategy:{strategy_name}",
                "──ACTION──▶",
                f"'{action}'"
            ]

            playbook_traversals.append({
                "layer": 3,
                "layer_name": "Playbook",
                "operation": f"Risk Strategy: {strategy_name}",
                "cypher_pattern": f"MATCH (r:Risk {{name: '{warning.risk_name}'}})-[:TRIGGERS_STRATEGY]->(s:Strategy) RETURN s.name, s.action",
                "nodes_visited": [
                    f"Risk:{warning.risk_name}",
                    f"Strategy:{strategy_name}",
                    f"Action:{action}"
                ],
                "relationships": ["TRIGGERS_STRATEGY", "HAS_ACTION"],
                "path_description": " ".join(path_chain),
                "result_summary": f"Risk '{warning.risk_name}' triggers strategy: '{strategy_name}' (Action: {action})"
            })
            strategy_descriptions.append(f"Risk '{warning.risk_name}' → {strategy_name}")

        # B. Data collection strategies (why we ask questions)
        for clarif in self.clarifications:
            strategy_name = "Data Collection"
            action = "ASK_QUESTION"
            trigger_reason = clarif.triggered_by or "Product sizing requirement"

            path_chain = [
                f"ProductFamily:GDB",
                "──REQUIRES_PARAMETER──▶",
                f"Parameter:{clarif.param_name}",
                "──TRIGGERS_STRATEGY──▶",
                f"Strategy:{strategy_name}",
                "──ACTION──▶",
                f"Ask: '{clarif.question_text[:25]}...'"
            ]

            playbook_traversals.append({
                "layer": 3,
                "layer_name": "Playbook",
                "operation": f"Data Strategy: {clarif.param_name}",
                "cypher_pattern": f"MATCH (pf:ProductFamily)-[:REQUIRES_PARAMETER]->(p:Parameter {{name: '{clarif.param_name}'}})-[:TRIGGERS_STRATEGY]->(s:Strategy)",
                "nodes_visited": [
                    "ProductFamily:GDB",
                    f"Parameter:{clarif.param_name}",
                    f"Strategy:{strategy_name}",
                    f"Question:{clarif.question_id}"
                ],
                "relationships": ["REQUIRES_PARAMETER", "TRIGGERS_STRATEGY", "ASK_VIA"],
                "path_description": " ".join(path_chain),
                "result_summary": f"Missing '{clarif.param_name}' for sizing → Strategy: Ask Question"
            })
            strategy_descriptions.append(f"Missing '{clarif.param_name}' → Ask Question")

        # C. Contextual rules (application-specific questions)
        contextual_rules = [c for c in self.clarifications if c.triggered_by]
        for clarif in contextual_rules[:2]:  # Limit to 2
            path_chain = [
                f"Application:{self.application.name if self.application else 'Unknown'}",
                "──ACTIVATES_RULE──▶",
                f"Rule:{clarif.triggered_by}",
                "──IMPLIES──▶",
                f"Ask: {clarif.param_name}"
            ]

            playbook_traversals.append({
                "layer": 3,
                "layer_name": "Playbook",
                "operation": f"Contextual Rule: {clarif.triggered_by}",
                "cypher_pattern": f"MATCH (app:Application)-[:ACTIVATES_RULE]->(r:Rule)-[:IMPLIES]->(q:Question)",
                "nodes_visited": [
                    f"Application:{self.application.name if self.application else 'Unknown'}",
                    f"Rule:{clarif.triggered_by}",
                    f"Parameter:{clarif.param_name}"
                ],
                "relationships": ["ACTIVATES_RULE", "IMPLIES", "ASK_PARAMETER"],
                "path_description": " ".join(path_chain),
                "result_summary": f"Active rule: '{clarif.triggered_by}' implies asking about '{clarif.param_name}'"
            })

        # Build playbook description
        if strategy_descriptions:
            playbook_desc = " ➤ ".join(strategy_descriptions[:3])  # Limit to 3 for readability
            if len(strategy_descriptions) > 3:
                playbook_desc += f" (+{len(strategy_descriptions) - 3} more)"
        else:
            playbook_desc = "No active strategies"

        if playbook_traversals:
            steps.append({
                "step": "PLAYBOOK STRATEGY",
                "icon": "♟️",
                "description": playbook_desc,
                "graph_traversals": playbook_traversals
            })

        # =====================================================================
        # Step 5: GUARDIAN INSIGHT - Warnings & Recommendations
        # =====================================================================
        guardian_traversals = []

        for warning in self.suitability.warnings:
            # Build detailed warning path
            path_chain = [
                f"⛔ VIOLATION FOUND:",
                f"User requested {warning.risk_name}",
                "──CONFLICTS_WITH──▶",
                f"Context:{self.application.name if self.application else 'Unknown'}",
                "──SOLUTION──▶",
                f"Upgrade to: {warning.mitigation[:30]}"
            ]

            guardian_traversals.append({
                "layer": 2,
                "layer_name": "Physics & Rules",
                "operation": f"Violation: {warning.risk_type}",
                "cypher_pattern": warning.graph_path,
                "nodes_visited": [
                    f"RequestedConfig:{warning.risk_name}",
                    f"Conflict:{warning.risk_type}",
                    f"Context:{self.application.name if self.application else 'Unknown'}",
                    f"Solution:{warning.mitigation[:40]}"
                ],
                "relationships": ["CONFLICTS_WITH", "VIOLATES", "SOLUTION"],
                "path_description": " ".join(path_chain),
                "result_summary": f"Found conflict: {warning.description}. Mitigation: {warning.mitigation}"
            })

        # Clarification questions from Layer 3
        if self.clarifications:
            for clarif in self.clarifications[:2]:
                path_chain = [
                    f"ProductFamily:GDB",
                    "──REQUIRES_PARAMETER──▶",
                    f"Parameter:{clarif.param_name}",
                    "──ASKED_VIA──▶",
                    f"Question:'{clarif.question_text[:30]}...'"
                ]

                guardian_traversals.append({
                    "layer": 3,
                    "layer_name": "Playbook",
                    "operation": f"Need: {clarif.param_name}",
                    "cypher_pattern": f"MATCH (pf:ProductFamily)-[:REQUIRES_PARAMETER]->(p:Parameter {{name:'{clarif.param_name}'}})-[:ASKED_VIA]->(q:Question)",
                    "nodes_visited": [
                        "ProductFamily:GDB",
                        f"Parameter:{clarif.param_name}",
                        f"Question:{clarif.question_id}"
                    ],
                    "relationships": ["REQUIRES_PARAMETER", "ASKED_VIA"],
                    "path_description": " ".join(path_chain),
                    "result_summary": f"To size the product, need parameter '{clarif.param_name}': {clarif.question_text}"
                })

        # Build insight message
        if self.suitability.warnings:
            warning = self.suitability.warnings[0]
            insight_msg = f"⚠️ {warning.risk_type}: {warning.mitigation}"
        else:
            insight_msg = "✅ All safety checks passed"

        steps.append({
            "step": "GUARDIAN INSIGHT",
            "icon": "🛡️",
            "description": insight_msg,
            "graph_traversals": guardian_traversals
        })

        return steps


class GraphReasoningEngine:
    """Engine for graph-native reasoning about product suitability.

    This engine queries Neo4j directly to evaluate business rules stored
    as graph relationships, replacing the config-based approach.
    """

    def __init__(self, db):
        """Initialize with a Neo4jConnection instance.

        Args:
            db: Neo4jConnection instance with graph query methods
        """
        self.db = db

    def detect_application(self, query: str) -> Optional[ApplicationMatch]:
        """Hybrid search for Application nodes using keyword + vector fallback.

        WATERFALL STRATEGY:
        1. KEYWORD SEARCH (Fast & Precise): Check if any application keyword is in the query
        2. VECTOR SEARCH (Semantic & Smart): If keywords fail, use embeddings to find
           semantically similar applications (e.g., "Surgery Center" → "Hospital")

        Args:
            query: User's query string

        Returns:
            ApplicationMatch if found, None otherwise
        """
        query_lower = query.lower()

        # =========================================================================
        # STEP A: KEYWORD SEARCH (Fast & Precise)
        # =========================================================================
        applications = self.db.get_all_applications()

        for app in applications:
            app_id = app.get('id', '')
            name = app.get('name', '')
            keywords = app.get('keywords', [])

            # Check if name or any keyword is in the query
            all_keywords = [name.lower()] + [k.lower() for k in keywords]

            for keyword in all_keywords:
                if keyword in query_lower:
                    return ApplicationMatch(
                        id=app_id,
                        name=name,
                        keywords=keywords,
                        matched_keyword=keyword,
                        risks=app.get('risks', []),
                        requirements=app.get('requirements', []),
                        match_method="Keyword Match",
                        confidence=1.0
                    )

        # =========================================================================
        # STEP B: VECTOR SEARCH (Semantic Fallback)
        # =========================================================================
        # If keyword search found nothing, try semantic similarity
        try:
            # Generate embedding for the query
            from embeddings import generate_embedding
            query_embedding = generate_embedding(query)

            # Search for semantically similar applications
            # Using higher threshold (0.80) to avoid false positives
            vector_results = self.db.vector_search_applications(
                query_embedding=query_embedding,
                top_k=1,
                min_score=0.80
            )

            if vector_results:
                best_match = vector_results[0]
                return ApplicationMatch(
                    id=best_match.get('id', ''),
                    name=best_match.get('name', ''),
                    keywords=best_match.get('keywords', []),
                    matched_keyword=query,  # Original query as the "matched" term
                    risks=best_match.get('risks', []),
                    requirements=best_match.get('requirements', []),
                    match_method="Vector Search",
                    confidence=best_match.get('similarity_score', 0.0)
                )

        except Exception as e:
            # Graceful degradation: if vector search fails, just return None
            # This ensures the system works even without embeddings
            print(f"Vector search fallback failed (expected if embeddings not set up): {e}")

        return None

    def check_suitability(
        self,
        product_family: str,
        application: Optional[ApplicationMatch],
        requested_material: Optional[str] = None
    ) -> SuitabilityResult:
        """Check product suitability for an application via graph traversal.

        Traverses REQUIRES_RESISTANCE and VULNERABLE_TO relationships to
        find potential conflicts between the product/material and application.

        Args:
            product_family: Product family code (e.g., 'GDB', 'GDC')
            application: Detected application context
            requested_material: Material code requested by user (e.g., 'FZ', 'RF')

        Returns:
            SuitabilityResult with warnings and requirements
        """
        result = SuitabilityResult(is_suitable=True)

        if not application:
            return result

        # Step 1: Get requirements for the application (REQUIRES_RESISTANCE)
        app_requirements = self.db.get_application_requirements(application.id)

        # Step 2: Check if requested material meets requirements
        if requested_material:
            # Get materials that meet the application's requirements
            suitable_materials = self.db.get_materials_meeting_requirements(application.id)
            suitable_codes = [m.get('code', '') for m in suitable_materials]

            for mat in suitable_materials:
                result.required_materials.append(MaterialRequirement(
                    material_code=mat.get('code', ''),
                    material_name=mat.get('name', ''),
                    corrosion_class=mat.get('corrosion_class', ''),
                    reason=mat.get('requirement_name', '')
                ))

            if suitable_codes and requested_material not in suitable_codes:
                # Material mismatch detected
                result.is_suitable = False
                req_names = [r.get('name', '') for r in app_requirements]
                result.warnings.append(RiskWarning(
                    risk_name='Material Mismatch',
                    risk_type='MATERIAL_MISMATCH',
                    severity='CRITICAL',
                    description=f"{requested_material} does not meet requirements for {application.name}",
                    consequence=f"Application requires: {', '.join(req_names)}",
                    mitigation=f"Use {' or '.join(suitable_codes)} instead",
                    graph_path=f"({application.name})-[:REQUIRES_RESISTANCE]->(:Requirement)<-[:MEETS_REQUIREMENT]-({', '.join(suitable_codes)})"
                ))

        # Step 3: Get product vulnerabilities (VULNERABLE_TO, PRONE_TO)
        if product_family:
            vulnerabilities = self.db.get_product_vulnerabilities(product_family)
            result.product_vulnerabilities = vulnerabilities

            # Check if application generates substances the product is vulnerable to
            app_substances = self.db.get_application_generated_substances(application.id)

            for vuln in vulnerabilities:
                vuln_target = vuln.get('target_name', '')
                vuln_target_id = vuln.get('target_id', '')

                # Check against generated substances
                for sub in app_substances:
                    if sub.get('id') == vuln_target_id or sub.get('name') == vuln_target:
                        # Get mitigations for this risk
                        mitigations = self.db.get_risk_mitigations(vuln.get('risk_id'))
                        mitigation_str = ', '.join([m.get('name', '') for m in mitigations]) if mitigations else vuln.get('mitigation', 'Consider alternative product')

                        result.warnings.append(RiskWarning(
                            risk_name=vuln_target,
                            risk_type='PRODUCT_VULNERABILITY',
                            severity='CRITICAL' if vuln.get('severity') == 'CRITICAL' else 'WARNING',
                            description=f"{product_family} is vulnerable to {vuln_target} which {application.name} generates",
                            consequence=vuln.get('reason', vuln.get('consequence', '')),
                            mitigation=mitigation_str,
                            graph_path=f"({application.name})-[:GENERATES]->({vuln_target})<-[:VULNERABLE_TO]-({product_family})"
                        ))

            # Check if application has risks the product is prone to
            app_risks = application.risks or self.db.get_application_risks(application.id)
            for risk in app_risks:
                risk_name = risk.get('name', '')
                for vuln in vulnerabilities:
                    if vuln.get('target_name') == risk_name or vuln.get('risk_name') == risk_name:
                        mitigations = self.db.get_risk_mitigations(risk.get('id'))
                        mitigation_str = ', '.join([m.get('name', '') for m in mitigations]) if mitigations else 'Consider alternative product or environment'

                        result.warnings.append(RiskWarning(
                            risk_name=risk_name,
                            risk_type='APPLICATION_RISK',
                            severity=risk.get('severity', 'WARNING'),
                            description=f"{application.name} poses {risk_name} risk, {product_family} is affected",
                            consequence=risk.get('desc', ''),
                            mitigation=mitigation_str,
                            graph_path=f"({application.name})-[:HAS_RISK]->({risk_name})"
                        ))

        # Step 4: Check for outdoor environment + non-insulated housing
        if product_family in ['GDB', 'GDC', 'GDP']:
            outdoor_check = self.db.check_outdoor_suitability(product_family)
            if outdoor_check and outdoor_check.get('has_condensation_risk'):
                # Check if application mentions outdoor keywords
                outdoor_keywords = ['outdoor', 'roof', 'dach', 'zewnątrz', 'rooftop']
                if any(k in application.keywords for k in outdoor_keywords):
                    result.warnings.append(RiskWarning(
                        risk_name='Condensation Risk',
                        risk_type='ENVIRONMENT_RISK',
                        severity='CRITICAL',
                        description=f"Non-insulated {product_family} in outdoor/rooftop installation",
                        consequence='Water damage inside housing, filter damage, accelerated corrosion',
                        mitigation='Use GDMI insulated housing instead',
                        graph_path=f"(ENV_OUTDOOR)-[:HAS_RISK]->(RISK_COND)<-[:VULNERABLE_TO]-({product_family})"
                    ))

        return result

    def check_geometric_constraints(
        self,
        product_family: str,
        selected_options: list[str],
        user_max_length_mm: Optional[int] = None,
        housing_length_mm: Optional[int] = None
    ) -> list[GeometricConflict]:
        """Check if selected options fit within physical space constraints.

        This implements the "Physical Constraint Validator" - ensures that
        options which "consume" length (like 'Polis' after-filter rail)
        can physically fit in the available space.

        MATHEMATICAL TRUTH OVER USER REQUEST:
        If an option requires 900mm but user only has 800mm, this is a BLOCK.
        We cannot bend physics to accommodate user preferences.

        Args:
            product_family: Product family code (e.g., 'GDC')
            selected_options: List of option IDs/names selected by user (e.g., ['Polis'])
            user_max_length_mm: User's max available space constraint (e.g., 800)
            housing_length_mm: Currently selected housing length (e.g., 750)

        Returns:
            List of GeometricConflict objects for any impossible configurations
        """
        conflicts = []

        if not selected_options:
            return conflicts

        # Query graph for option geometric constraints
        option_constraints = self.db.get_option_geometric_constraints(
            product_family,
            selected_options
        )

        for opt in option_constraints:
            opt_id = opt.get('option_id', '')
            opt_name = opt.get('option_name', '')
            min_required = opt.get('min_required_housing_length', 0)
            physics_reason = opt.get('physics_logic', 'Option requires additional internal space')

            if min_required == 0:
                continue  # Option has no length requirement

            # Check 1: Does option fit in user's available space?
            if user_max_length_mm and min_required > user_max_length_mm:
                conflicts.append(GeometricConflict(
                    option_id=opt_id,
                    option_name=opt_name,
                    required_length_mm=min_required,
                    user_max_length_mm=user_max_length_mm,
                    current_housing_length_mm=housing_length_mm or 0,
                    is_conflict=True,
                    conflict_type='OPTION_EXCEEDS_USER_LIMIT',
                    physics_explanation=physics_reason,
                    consequence=f"The '{opt_name}' option requires {min_required}mm housing, but your space limit is {user_max_length_mm}mm. This is physically impossible.",
                    resolution_options=[
                        f"Remove the '{opt_name}' option",
                        f"Increase available installation space to at least {min_required}mm"
                    ],
                    graph_path=f"({opt_id})-[:REQUIRES_MIN_LENGTH]->({min_required}mm)"
                ))

            # Check 2: Does option fit in the selected housing length?
            elif housing_length_mm and min_required > housing_length_mm:
                conflicts.append(GeometricConflict(
                    option_id=opt_id,
                    option_name=opt_name,
                    required_length_mm=min_required,
                    user_max_length_mm=user_max_length_mm or 0,
                    current_housing_length_mm=housing_length_mm,
                    is_conflict=True,
                    conflict_type='OPTION_EXCEEDS_HOUSING',
                    physics_explanation=physics_reason,
                    consequence=f"The '{opt_name}' option requires {min_required}mm housing, but the selected housing is only {housing_length_mm}mm.",
                    resolution_options=[
                        f"Upgrade to {min_required}mm housing variant",
                        f"Remove the '{opt_name}' option"
                    ],
                    graph_path=f"({opt_id})-[:REQUIRES_MIN_LENGTH]->({min_required}mm)"
                ))

        return conflicts

    def check_variable_features(
        self,
        product_family: str,
        context: Optional[dict] = None,
        technical_state: Optional["TechnicalState"] = None
    ) -> list[VariableFeature]:
        """Check for variable features that require user selection.

        This implements the "Variance Check Loop" - the system must ask about
        ALL variable features (like housing length) before giving a final answer.

        IMPORTANT: This now checks the cumulative TechnicalState first.
        If housing_length can be derived from filter_depth, it's auto-resolved.

        Args:
            product_family: Product family code (e.g., 'GDB', 'GDMI')
            context: Dict of already-known values to check against
            technical_state: TechnicalState object with cumulative session data

        Returns:
            List of VariableFeature objects for unresolved features
        """
        context = context or {}
        unresolved_features = []

        if not product_family:
            return []

        # =========================================================================
        # CUMULATIVE STATE CHECK: Build comprehensive resolved params from state
        # =========================================================================
        resolved_params = set()

        # Add context keys
        for k, v in context.items():
            if v is not None:
                resolved_params.add(k.lower())

        # Check TechnicalState for derived values
        if technical_state:
            for tag in technical_state.tags.values():
                # Housing length can be auto-derived from filter depth
                if tag.housing_length:
                    resolved_params.add('housing_length')
                    resolved_params.add('length')
                    resolved_params.add('długość')

                if tag.filter_depth:
                    # If we have depth, we can derive length - mark as resolved
                    resolved_params.add('housing_length')
                    resolved_params.add('length')

                if tag.airflow_m3h:
                    resolved_params.add('airflow')
                    resolved_params.add('airflow_m3h')
                    resolved_params.add('przepływ')

                if tag.housing_width and tag.housing_height:
                    resolved_params.add('housing_size')
                    resolved_params.add('wymiary')

        # =========================================================================
        # LEGACY CONTEXT CHECK: For backwards compatibility
        # =========================================================================
        # Check for depth in context - if present, length is derivable
        if context.get('filter_depth') or context.get('depth'):
            resolved_params.add('housing_length')
            resolved_params.add('length')

        if context.get('airflow') or context.get('airflow_m3h'):
            resolved_params.add('airflow')
            resolved_params.add('airflow_m3h')

        # Query graph for variable features
        variable_features = self.db.get_variable_features(product_family)

        # Debug: Print what we're checking
        print(f"📊 [VAR FEATURES] Checking {len(variable_features)} variable features for {product_family}")
        print(f"   Resolved params: {resolved_params}")

        for feat in variable_features:
            param_name = feat.get('parameter_name', '')
            feature_name = feat.get('feature_name', '')
            param_key = param_name.lower() if param_name else feature_name.lower().replace(' ', '_')

            # Check if this feature is already resolved
            is_resolved = (
                param_key in resolved_params or
                param_name in resolved_params or
                param_name.lower() in resolved_params or
                feature_name.lower().replace(' ', '_') in resolved_params
            )

            # Special case: housing_length is derivable from filter_depth
            if 'length' in param_key or 'długość' in param_key:
                if any(k in resolved_params for k in ['housing_length', 'length', 'filter_depth', 'depth']):
                    is_resolved = True
                    print(f"   ✅ {feature_name}: RESOLVED (length derivable from depth/length in params)")

            # Special case: airflow
            if 'airflow' in param_key or 'przepływ' in param_key:
                if any(k in resolved_params for k in ['airflow', 'airflow_m3h', 'przepływ']):
                    is_resolved = True
                    print(f"   ✅ {feature_name}: RESOLVED (airflow in params)")

            if not is_resolved:
                print(f"   ❌ {feature_name} (param_key={param_key}): UNRESOLVED")
                unresolved_features.append(VariableFeature(
                    feature_id=feat.get('feature_id', ''),
                    feature_name=feature_name,
                    parameter_name=param_name or feature_name.lower().replace(' ', '_'),
                    question=feat.get('question', f'Please select {feature_name}'),
                    why_needed=feat.get('why_needed', ''),
                    options=feat.get('options', []),
                    is_resolved=False
                ))
            else:
                print(f"   ✅ {feature_name} (param_key={param_key}): RESOLVED")

        print(f"   Result: {len(unresolved_features)} unresolved features")
        return unresolved_features

    def validate_accessory_compatibility(
        self,
        product_family: str,
        accessories: list[str]
    ) -> list[AccessoryCompatibilityResult]:
        """Validate accessory/option compatibility with a product family.

        STRICT ALLOW-LIST: If there's no explicit HAS_COMPATIBLE_ACCESSORY
        relationship in the graph, the combination is NOT allowed.

        This prevents configuration hallucinations like GDC + EXL
        (carbon filter housing with bag filter locking mechanism).

        Args:
            product_family: Product family code (e.g., 'GDB', 'GDC')
            accessories: List of accessory codes to validate (e.g., ['EXL', 'L'])

        Returns:
            List of AccessoryCompatibilityResult for each accessory
        """
        results = []

        if not product_family or not accessories:
            return results

        for accessory in accessories:
            compat_data = self.db.get_accessory_compatibility(accessory, product_family)

            # Convert dict to dataclass
            is_compatible = compat_data.get('is_compatible', None)

            # Handle None (unknown) as incompatible for safety
            if is_compatible is None:
                is_compatible = False
                status = compat_data.get('status', 'UNKNOWN')
            else:
                status = compat_data.get('status', 'ALLOWED' if is_compatible else 'BLOCKED')

            results.append(AccessoryCompatibilityResult(
                accessory_code=accessory,
                accessory_name=compat_data.get('accessory', accessory),
                product_family=compat_data.get('product_family', product_family),
                is_compatible=is_compatible,
                status=status,
                reason=compat_data.get('reason'),
                compatible_alternatives=compat_data.get('compatible_alternatives', []),
                uses_mounting_system=compat_data.get('uses_mounting_system')
            ))

        return results

    def check_physics_risks(
        self,
        product_family: str,
        query: str
    ) -> list[UnmitigatedPhysicsRisk]:
        """Check for physics-based unmitigated risks.

        MITIGATION PATH VALIDATOR:
        If Environment CAUSES Risk, and Risk is MITIGATED_BY Feature,
        but Product does NOT have that Feature -> BLOCK.

        This moves physics logic FROM the LLM (unreliable) TO the Graph (authoritative).
        User arguments like "the air is warm" CANNOT override physics.

        Args:
            product_family: Product family code (e.g., 'GDB', 'GDMI')
            query: User's query to detect environment keywords

        Returns:
            List of UnmitigatedPhysicsRisk for blocking configurations
        """
        results = []

        if not product_family:
            return results

        # Extract environment keywords from query
        query_lower = query.lower()
        environment_keywords = []

        # Outdoor keywords
        outdoor_keywords = ['outdoor', 'roof', 'rooftop', 'dach', 'zewnątrz', 'outside', 'exterior', 'weather']
        if any(kw in query_lower for kw in outdoor_keywords):
            environment_keywords = outdoor_keywords

        if not environment_keywords:
            return results

        # Query the graph for unmitigated risks
        risk_data = self.db.check_unmitigated_physics_risks(
            product_family=product_family,
            environment_keywords=environment_keywords
        )

        for risk in risk_data:
            results.append(UnmitigatedPhysicsRisk(
                environment_id=risk.get('environment_id', ''),
                environment_name=risk.get('environment_name', ''),
                risk_id=risk.get('risk_id', ''),
                risk_name=risk.get('risk_name', ''),
                risk_severity=risk.get('risk_severity', 'WARNING'),
                physics_explanation=risk.get('physics_explanation', ''),
                consequence=risk.get('consequence', ''),
                user_misconception=risk.get('user_misconception'),
                required_feature=risk.get('required_feature', ''),
                mitigation_mechanism=risk.get('mitigation_mechanism', ''),
                safe_alternatives=risk.get('safe_alternatives', []),
                blocked_product=risk.get('blocked_product', product_family)
            ))

        return results

    def get_required_clarifications(
        self,
        product_family: Optional[str] = None,
        application: Optional[ApplicationMatch] = None,
        context: Optional[dict] = None
    ) -> list[ClarificationQuestion]:
        """Get clarification questions needed for product selection.

        Queries the Parameter, Question, and ClarificationRule nodes
        to determine what questions to ask the user.

        Args:
            product_family: Optional product family to filter params
            application: Optional detected application for contextual rules
            context: Dict of already-known values to skip

        Returns:
            List of ClarificationQuestion sorted by priority
        """
        context = context or {}

        questions = []
        seen_params = set()

        # Step 1: Get required parameters for the product family (global rules)
        if product_family:
            required_params = self.db.get_required_parameters(product_family)
            for param in required_params:
                param_id = param.get('param_id', '')
                param_name = param.get('param_name', '')

                # Skip if already provided in context
                if param_name in context and context[param_name]:
                    continue

                if param_id in seen_params:
                    continue
                seen_params.add(param_id)

                questions.append(ClarificationQuestion(
                    param_id=param_id,
                    param_name=param_name,
                    question_id=param.get('question_id', ''),
                    question_text=param.get('question_text', ''),
                    intent=param.get('intent', 'sizing'),
                    priority=param.get('priority', 1),
                    triggered_by=None
                ))

        # Step 2: Get contextual clarification rules based on application
        if application:
            contextual_params = self.db.get_contextual_clarifications(
                application.id,
                product_family
            )
            for param in contextual_params:
                param_id = param.get('param_id', '')
                param_name = param.get('param_name', '')

                # Skip if already provided in context
                if param_name in context and context[param_name]:
                    continue

                if param_id in seen_params:
                    continue
                seen_params.add(param_id)

                questions.append(ClarificationQuestion(
                    param_id=param_id,
                    param_name=param_name,
                    question_id=param.get('question_id', ''),
                    question_text=param.get('question_text', ''),
                    intent=param.get('intent', 'engineering'),
                    priority=param.get('priority', 5),
                    triggered_by=param.get('rule_name')
                ))

        # Sort by priority (lower = more important)
        questions.sort(key=lambda q: q.priority)

        return questions

    def get_sizing_formula(self, product_family: str) -> Optional[dict]:
        """Retrieve sizing rules from the graph.

        Args:
            product_family: Product family code

        Returns:
            Dict with sizing formula and reference values, or None
        """
        # This could be extended to query SizingRule nodes
        # For now, return standard reference values
        sizing_rules = {
            'GDB': {
                'reference': '3400 m³/h per 1/1 module (592×592mm) at 1.5 m/s',
                'sizes': {
                    '300x300': 850,
                    '600x600': 3400,
                    '900x600': 5000
                }
            },
            'GDMI': {
                'reference': '3400 m³/h per 1/1 module at 1.5 m/s',
                'sizes': {
                    '300x300': 850,
                    '600x600': 3400,
                    '900x600': 5000
                }
            },
            'GDC': {
                'reference': '2000-3000 m³/h per 600×600 module',
                'sizes': {
                    '600x600': 2500,
                    '900x600': 4000
                }
            },
            'GDP': {
                'reference': '3000-4000 m³/h per 600×600',
                'sizes': {
                    '600x600': 3500
                }
            }
        }
        return sizing_rules.get(product_family)

    def _extract_material_regex_fallback(self, query: str) -> Optional[str]:
        """FALLBACK: Regex-based material extraction. Only called when Scribe/state has no material."""
        query_upper = query.upper()

        # Material patterns with their codes
        material_patterns = {
            'FZ': [r'\bFZ\b', r'galvanized', r'zinc', r'cynk', r'ocynk'],
            'ZM': [r'\bZM\b', r'zinc.?magnesium', r'magneli'],
            'RF': [r'\bRF\b', r'stainless', r'stal nierdzewna', r'inox', r'304'],
            'SF': [r'\bSF\b', r'316', r'marine.?grade'],
        }

        for code, patterns in material_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    return code

        return None

    def _extract_product_family_regex_fallback(self, query: str) -> Optional[str]:
        """FALLBACK: Regex-based product family extraction. Only called when not pre-detected."""
        query_upper = query.upper()

        families = ['GDB', 'GDC', 'GDP', 'GDMI', 'GDF', 'GDR', 'PFF', 'BFF']

        for family in families:
            if family in query_upper:
                return family

        return None

    def _extract_accessories_regex_fallback(self, query: str) -> list[str]:
        """FALLBACK: Regex-based accessory extraction. Only called when Scribe/state has no accessories."""
        query_upper = query.upper()
        found_accessories = []

        # Known accessory patterns (order matters - longer patterns first)
        accessory_patterns = [
            # Full names/descriptions (check first)
            ('ECCENTRIC LOCK', 'EXL'),
            ('QUICK RELEASE', 'EXL'),
            ('QUICK-RELEASE', 'EXL'),
            ('LEFT HINGE', 'L'),
            ('LEFT-HINGE', 'L'),
            ('POLYSFILTER', 'Polis'),
            ('AFTER-FILTER RAIL', 'Polis'),
            ('AFTER FILTER RAIL', 'Polis'),
            ('AFTER-FILTER', 'Polis'),
            ('POLISHING RAIL', 'Polis'),
            ('BAYONET', 'Bayonet'),
            # Codes (check after)
            ('-EXL', 'EXL'),
            (' EXL', 'EXL'),
            ('/EXL', 'EXL'),
            ('+EXL', 'EXL'),
            ('_EXL', 'EXL'),
            ('-L-', 'L'),
            ('-L ', 'L'),
            (' L ', 'L'),  # Only match standalone L
            ('-POLIS', 'Polis'),
            (' POLIS', 'Polis'),
            ('(POLIS)', 'Polis'),
            ("'POLIS'", 'Polis'),
        ]

        for pattern, accessory in accessory_patterns:
            if pattern in query_upper:
                if accessory not in found_accessories:
                    found_accessories.append(accessory)

        # Also check for "with EXL" or "with L" patterns
        with_patterns = [
            (r'\bWITH\s+EXL\b', 'EXL'),
            (r'\bWITH\s+L\b', 'L'),
            (r'\bWITH\s+POLIS\b', 'Polis'),
            (r'\bADD\s+EXL\b', 'EXL'),
            (r'\bINCLUDE\s+EXL\b', 'EXL'),
            (r'\bEXL\s+LOCK', 'EXL'),
            (r'\bEXL\s+HANDLE', 'EXL'),
        ]

        for pattern, accessory in with_patterns:
            if re.search(pattern, query_upper):
                if accessory not in found_accessories:
                    found_accessories.append(accessory)

        return found_accessories

    def generate_reasoning_report(
        self,
        query: str,
        product_family: Optional[str] = None,
        context: Optional[dict] = None,
        material: Optional[str] = None,
        accessories: Optional[list] = None,
    ) -> GraphReasoningReport:
        """Generate complete graph reasoning report for LLM injection.

        This is the main entry point that orchestrates all reasoning steps.

        Args:
            query: User's original query
            product_family: Optional pre-detected product family
            context: Optional dict of known parameters
            material: Optional pre-extracted material code (from Scribe/state)
            accessories: Optional pre-extracted accessories list (from Scribe/state)

        Returns:
            GraphReasoningReport with all findings
        """
        context = context or {}
        reasoning_steps = []
        graph_evidence = []

        # Step 1: Extract product family if not provided
        if not product_family:
            product_family = self._extract_product_family_regex_fallback(query)
            if product_family:
                reasoning_steps.append({
                    'step': 'Product Family Detection',
                    'result': f"Detected {product_family} from query",
                    'source': 'EXTRACTION'
                })

        # Step 2: Material — use pre-extracted (Scribe/state), regex fallback
        requested_material = material or self._extract_material_regex_fallback(query)
        if requested_material:
            reasoning_steps.append({
                'step': 'Material Detection',
                'result': f"User requested {requested_material} material",
                'source': 'EXTRACTION'
            })

        # Step 3: Detect application context (Hybrid Search: Keyword + Vector)
        application = self.detect_application(query)
        if application:
            # Show match method in reasoning for transparency
            if application.match_method == "Vector Search":
                match_desc = f"'{application.matched_keyword}' ≈ {application.name} (Method: {application.match_method}, Score: {application.confidence:.2f})"
            else:
                match_desc = f"Matched '{application.matched_keyword}' → {application.name} (Method: {application.match_method})"

            reasoning_steps.append({
                'step': 'Application Detection',
                'result': match_desc,
                'source': 'GRAPH',
                'match_method': application.match_method,
                'confidence': application.confidence
            })
            graph_evidence.append({
                'type': 'APPLICATION_MATCH',
                'description': f"Query '{application.matched_keyword}' → {application.name} via {application.match_method}",
                'path': f"(Application {{name: '{application.name}'}})",
                'method': application.match_method,
                'confidence': application.confidence
            })

        # Step 4: Check suitability via graph traversal
        suitability = self.check_suitability(product_family, application, requested_material)

        for req in suitability.required_materials:
            graph_evidence.append({
                'type': 'MATERIAL_REQUIREMENT',
                'description': f"{application.name if application else 'Application'} requires {req.material_code} ({req.material_name})",
                'path': f"({application.name if application else '?'})-[:REQUIRES_MATERIAL]->({req.material_code})"
            })

        for warning in suitability.warnings:
            reasoning_steps.append({
                'step': f'{warning.risk_type} Check',
                'result': warning.description,
                'source': 'GRAPH',
                'severity': warning.severity
            })
            graph_evidence.append({
                'type': 'RISK_DETECTION',
                'description': warning.description,
                'path': warning.graph_path
            })

        # Step 5: Get required clarifications
        clarifications = self.get_required_clarifications(product_family, application, context)
        if clarifications:
            reasoning_steps.append({
                'step': 'Clarification Check',
                'result': f"{len(clarifications)} parameters need clarification",
                'source': 'GRAPH'
            })

        # Step 6: VARIANCE CHECK LOOP - Check for variable features
        # This ensures the system asks about ALL configurable features
        # (like housing length) before giving a final answer
        variable_features = []
        if product_family:
            variable_features = self.check_variable_features(product_family, context)
            if variable_features:
                feature_names = [f.feature_name for f in variable_features]
                reasoning_steps.append({
                    'step': 'Variance Detected',
                    'result': f"Product {product_family} has unresolved variable features: {', '.join(feature_names)}",
                    'source': 'GRAPH',
                    'requires_user_input': True
                })
                graph_evidence.append({
                    'type': 'VARIABLE_FEATURE',
                    'description': f"{product_family} requires selection of: {', '.join(feature_names)}",
                    'path': f"(ProductFamily:{product_family})-[:HAS_VARIABLE_FEATURE]->({', '.join(feature_names)})"
                })

        # Step 7: STRICT ACCESSORY COMPATIBILITY CHECK
        # Validates that requested accessories are compatible with the product family
        accessory_compatibility = []
        if product_family:
            requested_accessories = accessories or self._extract_accessories_regex_fallback(query)
            if requested_accessories:
                accessory_compatibility = self.validate_accessory_compatibility(
                    product_family, requested_accessories
                )

                for compat in accessory_compatibility:
                    if not compat.is_compatible:
                        # Incompatible configuration detected!
                        reasoning_steps.append({
                            'step': 'Accessory Compatibility Check',
                            'result': f"BLOCKED: {compat.accessory_name} is NOT compatible with {compat.product_family}",
                            'source': 'GRAPH',
                            'severity': 'CRITICAL',
                            'status': compat.status
                        })
                        graph_evidence.append({
                            'type': 'COMPATIBILITY_VIOLATION',
                            'description': f"{compat.accessory_name} + {compat.product_family}: {compat.reason}",
                            'path': f"({compat.product_family})-[:INCOMPATIBLE_WITH]->({compat.accessory_name})"
                        })
                    else:
                        reasoning_steps.append({
                            'step': 'Accessory Compatibility Check',
                            'result': f"ALLOWED: {compat.accessory_name} is compatible with {compat.product_family}",
                            'source': 'GRAPH',
                            'status': compat.status
                        })

        # Step 8: PHYSICS-BASED RISK CHECK (Mitigation Path Validator)
        # If Environment CAUSES Risk that needs Feature, and Product lacks Feature -> BLOCK
        # This is NON-NEGOTIABLE - user arguments cannot override physics
        physics_risks = []
        product_pivot = None
        original_product = product_family  # Save original for pivot tracking

        if product_family:
            physics_risks = self.check_physics_risks(product_family, query)

            # AUTOMATIC PIVOT: If CRITICAL risk detected, switch to safe product
            for risk in physics_risks:
                if risk.risk_severity == 'CRITICAL' and risk.safe_alternatives:
                    # Extract the safe product family code from the full name
                    safe_product_name = risk.safe_alternatives[0]
                    # Extract code (e.g., "GDMI" from "GDMI Modulfilterskåp")
                    safe_product_code = safe_product_name.split()[0] if safe_product_name else None

                    if safe_product_code:
                        # CREATE PIVOT RECORD
                        product_pivot = ProductPivot(
                            original_product=risk.blocked_product,
                            pivoted_to=safe_product_name,
                            reason=f"{risk.risk_name} in {risk.environment_name}",
                            physics_explanation=risk.physics_explanation or "",
                            user_misconception=risk.user_misconception,
                            required_feature=risk.required_feature or ""
                        )

                        reasoning_steps.append({
                            'step': 'Physics Risk Check - PIVOT',
                            'result': f"PIVOTED: {risk.blocked_product} -> {safe_product_name} (CRITICAL: {risk.risk_name})",
                            'source': 'GRAPH',
                            'severity': 'PIVOT',
                            'override_user': True,
                            'pivot_from': original_product,
                            'pivot_to': safe_product_code
                        })
                        graph_evidence.append({
                            'type': 'AUTOMATIC_PIVOT',
                            'description': f"Physics Override: {risk.blocked_product} replaced with {safe_product_name}",
                            'path': f"({risk.environment_name})-[:CAUSES]->({risk.risk_name})-[:MITIGATED_BY]->({risk.required_feature})<-[:HAS_FEATURE]-({safe_product_name})",
                            'reason': risk.physics_explanation,
                            'user_misconception': risk.user_misconception
                        })
                        break  # Only pivot once

                else:
                    # Non-critical or no alternative - just log the risk
                    reasoning_steps.append({
                        'step': 'Physics Risk Check',
                        'result': f"WARNING: {risk.blocked_product} in {risk.environment_name} has {risk.risk_name} risk",
                        'source': 'GRAPH',
                        'severity': risk.risk_severity,
                        'override_user': True
                    })
                    graph_evidence.append({
                        'type': 'PHYSICS_VIOLATION',
                        'description': f"{risk.environment_name} -> {risk.risk_name} (requires {risk.required_feature})",
                        'path': f"({risk.environment_name})-[:CAUSES]->({risk.risk_name})-[:MITIGATED_BY]->({risk.required_feature})",
                        'safe_alternatives': risk.safe_alternatives,
                        'physics': risk.physics_explanation
                    })

        return GraphReasoningReport(
            application=application,
            suitability=suitability,
            clarifications=clarifications,
            reasoning_steps=reasoning_steps,
            graph_evidence=graph_evidence,
            variable_features=variable_features,
            accessory_compatibility=accessory_compatibility,
            physics_risks=physics_risks,
            product_pivot=product_pivot
        )
