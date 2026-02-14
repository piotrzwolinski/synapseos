"""Pydantic schemas for the Hybrid GraphRAG Sales Assistant."""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ProductType(str, Enum):
    CONSUMABLE = "Consumable"
    CAPITAL = "Capital"


# Hard Data Schemas
class Product(BaseModel):
    """Internal product with SKU and pricing."""
    sku: Optional[str] = None
    name: str
    price: Optional[float] = None
    dimensions: Optional[str] = None
    type: ProductType = ProductType.CONSUMABLE


# ========================================
# Technical Document Extraction Schemas
# ========================================

class FilterCartridge(BaseModel):
    """Activated carbon filter cartridge component.

    Source: Detailed component sections (e.g., pages describing ECO-C cylinders).
    Pattern: "ECO-C 2600 SC 3mm pellet... totalvikt 2.8 kg"
    """
    id: str = Field(..., description="Unique identifier (e.g., 'ECO-C-2600')")
    model_name: str = Field(..., description="Model designation (e.g., 'ECO-C 2600')")
    weight_kg: Optional[float] = Field(None, description="Total weight in kilograms")
    carbon_weight_kg: Optional[float] = Field(None, description="Carbon content weight in kg")
    diameter_mm: Optional[float] = Field(None, description="Cylinder diameter in mm")
    length_mm: Optional[float] = Field(None, description="Cylinder length in mm")
    pellet_size_mm: Optional[float] = Field(None, description="Pellet size (e.g., 3mm)")
    media_type: Optional[str] = Field(None, description="Media type (e.g., 'SC 3mm pellet')")
    compatible_housings: list[str] = Field(default_factory=list, description="Housing IDs this cartridge fits")


class DuctConnection(BaseModel):
    """Duct transition/reducer specification.

    Source: Transition tables (e.g., "PT PLAN ÖVERGÅNG" table).
    Pattern: Matrix of housing sizes to valid duct diameters.
    """
    id: str = Field(..., description="Unique identifier")
    housing_size: str = Field(..., description="Housing size designation (e.g., '600x600')")
    housing_width_mm: int = Field(..., description="Housing width in mm")
    housing_height_mm: int = Field(..., description="Housing height in mm")
    valid_duct_diameters_mm: list[int] = Field(..., description="List of compatible duct diameters")
    transition_type: Optional[str] = Field(None, description="Type of transition (e.g., 'PT', 'FZ')")


class ConfigurationOption(BaseModel):
    """Product configuration option.

    Source: "Option:" sections at bottom of product pages.
    Pattern: "Vänsterhängd lucka = L (left)", "Fläns ohålad=F"
    """
    code: str = Field(..., description="Option code (e.g., 'L', 'F', '50')")
    description: str = Field(..., description="Full description in English")
    original_text: Optional[str] = Field(None, description="Original text from document")
    category: Optional[str] = Field(None, description="Option category (e.g., 'Hinging', 'Flange', 'Frame')")


class MaterialSpecification(BaseModel):
    """Material specification with corrosion class mapping.

    Source: Page 4 material tables and product pages.
    Pattern: Material codes (FZ, ZM, RF) mapped to corrosion classes (C3, C4, C5).
    """
    code: str = Field(..., description="Material code (e.g., 'FZ', 'ZM', 'RF')")
    full_name: str = Field(..., description="Full material name (e.g., 'Sendzimir galvanized')")
    corrosion_class: Optional[str] = Field(None, description="ISO corrosion class (C3, C4, C5)")
    description: Optional[str] = Field(None, description="Material description and typical applications")


class FilterConsumable(BaseModel):
    """Consumable filter with part number.

    Source: Pages 7, 10, 15, 17, 19 - filter specifications with part numbers.
    Pattern: "61090M2359 ECO-C 2600 SC 3mm pellet 450mm 2,2 kg kol"
    """
    id: str = Field(..., description="Unique identifier")
    part_number: str = Field(..., description="Part number/SKU (e.g., '61090M2359')")
    model_name: Optional[str] = Field(None, description="Model name (e.g., 'ECO-C 2600')")
    filter_type: str = Field(..., description="Filter type (e.g., 'Carbon Cartridge', 'Bag Filter', 'Panel Filter')")
    weight_kg: Optional[float] = Field(None, description="Filter weight in kg")
    dimensions: Optional[str] = Field(None, description="Filter dimensions")
    media_type: Optional[str] = Field(None, description="Filter media type")
    efficiency_class: Optional[str] = Field(None, description="Filter efficiency class (e.g., 'ePM1 55%', 'HEPA H13')")
    compatible_housings: list[str] = Field(default_factory=list, description="Housing IDs this filter fits")


class CompetitorProduct(BaseModel):
    """Competitor product reference."""
    name: str
    manufacturer: Optional[str] = None


class ProductMapping(BaseModel):
    """Mapping between competitor product and our equivalent."""
    competitor_product: str
    our_product_sku: Optional[str] = None
    our_product_name: Optional[str] = None
    notes: Optional[str] = None


# Soft Knowledge Schemas
class Concept(BaseModel):
    """A semantic concept extracted from case studies."""
    name: str
    description: Optional[str] = None
    embedding: Optional[list[float]] = None


class Observation(BaseModel):
    """An observation from a project/case study."""
    description: str
    context: Optional[str] = None


class Action(BaseModel):
    """An action taken in response to an observation."""
    description: str
    outcome: Optional[str] = None


class Project(BaseModel):
    """A project or case study."""
    name: str
    customer: Optional[str] = None
    date: Optional[str] = None
    summary: Optional[str] = None


# Extraction Schemas (LLM output structure)
class ExtractedHardData(BaseModel):
    """Hard data extracted from case study text."""
    products: list[Product] = Field(default_factory=list)
    competitor_products: list[CompetitorProduct] = Field(default_factory=list)
    product_mappings: list[ProductMapping] = Field(default_factory=list)


class ExtractedSoftKnowledge(BaseModel):
    """Soft knowledge extracted from case study text."""
    concepts: list[str] = Field(default_factory=list, description="Key concepts for semantic search")
    observations: list[str] = Field(default_factory=list, description="Key observations from the case")
    actions: list[str] = Field(default_factory=list, description="Actions taken and their outcomes")


class ExtractionResult(BaseModel):
    """Complete extraction result from LLM."""
    hard_data: ExtractedHardData
    soft_knowledge: ExtractedSoftKnowledge


# API Request/Response Schemas
class IngestRequest(BaseModel):
    """Request to ingest a case study."""
    text: str = Field(..., description="The case study text to ingest")
    project_name: str = Field(..., description="Name for this project/case")
    customer: Optional[str] = Field(None, description="Customer name")


class ConsultRequest(BaseModel):
    """Request to consult the knowledge graph."""
    query: str = Field(..., description="The sales question or scenario")
    session_id: Optional[str] = Field(None, description="Session ID for Layer 4 graph state persistence")


class ConsultResponse(BaseModel):
    """Response from the knowledge graph consultation."""
    answer: str = Field(..., description="Synthesized answer")
    concepts_matched: list[str] = Field(default_factory=list, description="Concepts that matched the query")
    observations: list[str] = Field(default_factory=list, description="Relevant observations")
    actions: list[str] = Field(default_factory=list, description="Suggested actions from past cases")
    products_mentioned: list[str] = Field(default_factory=list, description="Products referenced")


class GraphEvidence(BaseModel):
    """A piece of evidence from the knowledge graph."""
    fact: str = Field(..., description="The factual claim")
    source_id: str = Field(..., description="Node ID in the graph")
    confidence: str = Field(default="verified", description="verified or inferred")


class PolicyCheckResult(BaseModel):
    """Result of a Guardian policy check."""
    policy_id: str = Field(..., description="Policy identifier")
    policy_name: str = Field(..., description="Human-readable policy name")
    triggered: bool = Field(default=False, description="Whether the policy was triggered")
    passed: bool = Field(default=True, description="Whether validation passed")
    message: str = Field(default="", description="Validation message")
    recommendation: str = Field(default="", description="Recommendation if failed")


class StructuredResponse(BaseModel):
    """Enhanced structured response with explainability.

    This model provides clear separation between verified graph data
    and general model knowledge, with full reasoning transparency.
    """
    # Intent and reasoning
    intent_analysis: str = Field(..., description="What the user is trying to accomplish")
    policy_analysis: str = Field(default="", description="Guardian reasoning and policy checks")

    # Evidence classification
    graph_evidence: list[GraphEvidence] = Field(
        default_factory=list,
        description="Facts from the graph with citations"
    )
    general_knowledge: str = Field(
        default="",
        description="Additional context from model training (clearly marked as unverified)"
    )

    # Final output
    final_answer: str = Field(..., description="The complete response to the user")
    confidence_level: str = Field(
        default="medium",
        description="high (graph data), medium (partial), low (general knowledge)"
    )

    # Metadata
    sources: list[str] = Field(default_factory=list, description="Node IDs used")
    warnings: list[str] = Field(default_factory=list, description="Policy warnings")
    policy_checks: list[PolicyCheckResult] = Field(
        default_factory=list,
        description="Detailed policy check results"
    )

    # For UI "thinking" indicator
    thought_process: str = Field(
        default="",
        description="Step-by-step reasoning for UI display"
    )


class ProductListResponse(BaseModel):
    """Response listing all products."""
    products: list[dict] = Field(default_factory=list)


# =============================================================================
# EXPLAINABLE UI RESPONSE SCHEMA
# =============================================================================

class ReferenceDetail(BaseModel):
    """Detail about a referenced source."""
    name: str = Field(..., description="Human-readable name of the source")
    type: str = Field(..., description="Type: Product, Spec, Case, Material, etc.")
    source_doc: str = Field(default="", description="Document reference (e.g., 'PDF p.3')")
    confidence: str = Field(default="verified", description="verified or inferred")


class ReasoningStep(BaseModel):
    """A single step in the reasoning chain with source attribution."""
    step: str = Field(..., description="Description of this reasoning step")
    source: str = Field(..., description="GRAPH | LLM | POLICY | FILTER")
    node_id: Optional[str] = Field(None, description="Graph node ID if source=GRAPH")
    confidence: str = Field(default="high", description="high/medium/low")


# =============================================================================
# DEEP EXPLAINABILITY SCHEMA (Enterprise UI)
# =============================================================================

class GraphTraversal(BaseModel):
    """Details of a graph traversal operation."""
    layer: int = Field(..., description="Graph layer: 1=Inventory, 2=Physics/Rules, 3=Playbook")
    layer_name: str = Field(..., description="Human-readable layer name")
    operation: str = Field(..., description="What was queried (e.g., 'Application Detection')")
    cypher_pattern: Optional[str] = Field(None, description="Cypher pattern used")
    nodes_visited: list[str] = Field(default_factory=list, description="Nodes traversed")
    relationships: list[str] = Field(default_factory=list, description="Relationships traversed")
    result_summary: Optional[str] = Field(None, description="Summary of what was found")
    path_description: Optional[str] = Field(None, description="Full reasoning chain like 'GDB → FZ → VulnerableTo → Corrosion'")


class ReasoningSummaryStep(BaseModel):
    """A high-level reasoning step for the UI timeline with graph traversal details."""
    step: str = Field(..., description="Step label (e.g., 'Analysis', 'Guardian Check')")
    icon: str = Field(default="🔍", description="Emoji icon for the step")
    description: str = Field(..., description="Description of what happened")
    # Graph traversal details for transparency
    graph_traversals: list[GraphTraversal] = Field(
        default_factory=list,
        description="Graph operations performed in this step"
    )


class ContentSegment(BaseModel):
    """A segment of the answer with source attribution."""
    text: str = Field(..., description="The text content of this segment")
    type: str = Field(..., description="GENERAL | INFERENCE | GRAPH_FACT")
    # For INFERENCE type
    inference_logic: Optional[str] = Field(None, description="The reasoning behind this inference")
    # For GRAPH_FACT type
    source_id: Optional[str] = Field(None, description="Node ID in the knowledge graph")
    source_text: Optional[str] = Field(None, description="Human-readable source (e.g., 'PDF p.4')")
    # Rich evidence fields for GRAPH_FACT
    node_type: Optional[str] = Field(None, description="Type of graph node (e.g., 'ProductVariant', 'Material')")
    evidence_snippet: Optional[str] = Field(None, description="The specific text/description from the graph that justifies the fact")
    source_document: Optional[str] = Field(None, description="Source document filename")
    page_number: Optional[int] = Field(None, description="Page number in source document")
    key_specs: Optional[dict[str, str]] = Field(None, description="Key specifications from the graph node")


class ProductCard(BaseModel):
    """Structured product recommendation card."""
    title: str = Field(..., description="Product name/title")
    specs: dict[str, str] = Field(default_factory=dict, description="Key-value specs")
    warning: Optional[str] = Field(None, description="Warning message if any")
    confidence: str = Field(default="high", description="Recommendation confidence")
    actions: list[str] = Field(default_factory=list, description="Available actions (e.g., 'Add to Quote')")


class ClarificationOption(BaseModel):
    """An option presented to the user for clarification."""
    value: str = Field(..., description="The value to use if selected")
    description: str = Field(..., description="Human-readable description of this option")
    display_label: Optional[str] = Field(None, description="Short user-facing label for the pill button (e.g., '550mm (Short Housing)')")


class ClarificationRequest(BaseModel):
    """Request for clarification when critical parameters are missing."""
    missing_info: str = Field(..., description="What information is missing")
    why_needed: str = Field(..., description="Why this information is needed (engineering context)")
    options: list[ClarificationOption] = Field(
        default_factory=list,
        description="Optional multiple-choice options to help the user"
    )
    question: str = Field(..., description="The question to ask the user")


class ProductPivotInfo(BaseModel):
    """Information about automatic product substitution due to physics constraints.

    When a CRITICAL physics risk is detected and the selected product lacks
    the required mitigation, the system automatically pivots to a safe product.
    This is displayed as a prominent banner in the UI.
    """
    original_product: str = Field(..., description="Product the user originally requested")
    pivoted_to: str = Field(..., description="Product the system auto-selected")
    reason: str = Field(..., description="Risk that triggered the pivot")
    physics_explanation: str = Field(..., description="Why this is non-negotiable (physics)")
    user_misconception: Optional[str] = Field(None, description="Counter to user's wrong argument")
    required_feature: str = Field(..., description="Feature the safe product has")


class DeepExplainableResponse(BaseModel):
    """Enterprise-grade explainable response with segmented content.

    This schema provides:
    - High-level reasoning timeline (Polish, synthesized)
    - Content broken into attributed segments (GRAPH_FACT, INFERENCE, GENERAL)
    - Structured product cards
    - Autonomous risk detection via LLM engineering knowledge
    - Automatic product pivot for physics violations
    """
    # Reasoning timeline for "Thinking" UI
    reasoning_summary: list[ReasoningSummaryStep] = Field(
        default_factory=list,
        description="High-level reasoning steps in Polish"
    )

    # Segmented answer content
    content_segments: list[ContentSegment] = Field(
        default_factory=list,
        description="Answer broken into attributed segments"
    )

    # Product recommendation (optional)
    product_card: Optional[ProductCard] = Field(
        None,
        description="Structured product recommendation (backward compat, first card)"
    )
    product_cards: list[ProductCard] = Field(
        default_factory=list,
        description="Multiple product cards (for assembly/multi-stage systems)"
    )

    # Autonomous Guardian - Risk Detection
    risk_detected: bool = Field(
        default=False,
        description="True if LLM detected engineering incompatibility"
    )
    risk_severity: Optional[str] = Field(
        default=None,
        description="Risk severity level: CRITICAL, WARNING, or INFO"
    )
    risk_resolved: bool = Field(
        default=False,
        description="True if a previously detected risk was mitigated by the final recommendation"
    )

    # Physics Override - Automatic Product Pivot
    product_pivot: Optional[ProductPivotInfo] = Field(
        default=None,
        description="Set when system auto-switched product due to CRITICAL physics risk"
    )

    # Clarification Mode - Missing critical parameters
    clarification_needed: bool = Field(
        default=False,
        description="True if critical parameters are missing and clarification is needed"
    )
    clarification: Optional[ClarificationRequest] = Field(
        None,
        description="Clarification request details when clarification_needed=True"
    )

    # Metadata
    query_language: str = Field(default="pl", description="Detected query language")
    confidence_level: str = Field(default="medium", description="high/medium/low")
    policy_warnings: list[str] = Field(default_factory=list, description="Policy violations or engineering warnings")

    # Stats for UI
    graph_facts_count: int = Field(default=0, description="Number of GRAPH_FACT segments")
    inference_count: int = Field(default=0, description="Number of INFERENCE segments")

    # Performance timing (for dev mode)
    timings: Optional[dict] = Field(default=None, description="Operation timings in seconds")


class ExplainableResponse(BaseModel):
    """Structured response for the Explainable UI.

    This schema separates reasoning from final answer and provides
    traceable references for every fact derived from the Knowledge Graph.
    """
    # Reasoning transparency with source attribution
    reasoning_chain: list[ReasoningStep] = Field(
        default_factory=list,
        description="Step-by-step reasoning with GRAPH vs LLM attribution"
    )

    # Legacy field for backwards compatibility
    reasoning_steps: list[str] = Field(
        default_factory=list,
        description="Simple text steps (deprecated, use reasoning_chain)"
    )

    # The answer with inline citations
    final_answer_markdown: str = Field(
        ...,
        description="Markdown answer with [[REF:ID]] markers after verified facts"
    )

    # Reference lookup table
    references: dict[str, ReferenceDetail] = Field(
        default_factory=dict,
        description="Map of reference IDs to their details"
    )

    # Metadata
    query_language: str = Field(default="en", description="Detected query language")
    confidence_level: str = Field(default="medium", description="high/medium/low")
    policy_warnings: list[str] = Field(default_factory=list, description="Any policy violations")

    # Graph vs LLM breakdown
    graph_facts_count: int = Field(default=0, description="Number of facts from Knowledge Graph")
    llm_inferences_count: int = Field(default=0, description="Number of inferences from LLM pretraining")


# =============================================================================
# GRAPH NEIGHBORHOOD RESPONSE SCHEMA
# =============================================================================

class GraphNode(BaseModel):
    """A node in the graph neighborhood response."""
    id: str = Field(..., description="Node element ID")
    labels: list[str] = Field(default_factory=list, description="Node labels (types)")
    name: str = Field(..., description="Full name for the node")
    display_label: str = Field(default="", description="Formatted label for graph visualization (may include newlines)")
    properties: dict = Field(default_factory=dict, description="Node properties (excluding embedding)")


class GraphRelationship(BaseModel):
    """A relationship in the graph neighborhood response."""
    id: str = Field(..., description="Relationship element ID")
    type: str = Field(..., description="Relationship type (e.g., RELATES_TO)")
    source: str = Field(..., description="Source node element ID")
    target: str = Field(..., description="Target node element ID")
    properties: dict = Field(default_factory=dict, description="Relationship properties")


class GraphNeighborhoodResponse(BaseModel):
    """Response for graph neighborhood query."""
    center_node: GraphNode = Field(..., description="The center node of the neighborhood")
    nodes: list[GraphNode] = Field(default_factory=list, description="All nodes in the neighborhood including center")
    relationships: list[GraphRelationship] = Field(default_factory=list, description="Relationships between nodes")
    truncated: bool = Field(default=False, description="True if max_nodes limit was reached")


# =============================================================================
# LAYER 4: SESSION GRAPH STATE
# =============================================================================

class TagUnitState(BaseModel):
    """State of a single tag/item in the active project."""
    tag_id: str = Field(..., description="Tag identifier (e.g., '5684')")
    filter_width: Optional[int] = Field(None, description="Filter width in mm")
    filter_height: Optional[int] = Field(None, description="Filter height in mm")
    filter_depth: Optional[int] = Field(None, description="Filter depth in mm")
    housing_width: Optional[int] = Field(None, description="Housing width in mm (derived)")
    housing_height: Optional[int] = Field(None, description="Housing height in mm (derived)")
    housing_length: Optional[int] = Field(None, description="Housing length in mm (derived)")
    airflow_m3h: Optional[int] = Field(None, description="Airflow capacity")
    product_family: Optional[str] = Field(None, description="Product family (GDB, GDC, etc.)")
    product_code: Optional[str] = Field(None, description="Full product code")
    weight_kg: Optional[float] = Field(None, description="Weight in kg")
    is_complete: bool = Field(default=False, description="All required specs present")


class ActiveProjectState(BaseModel):
    """State of the active project configuration."""
    name: Optional[str] = Field(None, description="Project name")
    customer: Optional[str] = Field(None, description="Customer name")
    locked_material: Optional[str] = Field(None, description="Locked material code")
    detected_family: Optional[str] = Field(None, description="Detected product family")


class SessionGraphState(BaseModel):
    """Complete session state from the graph database (Layer 4)."""
    session_id: str = Field(..., description="Session identifier")
    project: Optional[ActiveProjectState] = Field(None, description="Active project")
    tags: list[TagUnitState] = Field(default_factory=list, description="Tag unit specs")
    tag_count: int = Field(default=0, description="Number of tag units")
    reasoning_paths: list[dict] = Field(default_factory=list, description="Per-tag reasoning audit trail")


class SessionGraphVisualization(BaseModel):
    """Session graph nodes and relationships for ForceGraph2D visualization."""
    nodes: list[GraphNode] = Field(default_factory=list, description="Graph nodes")
    relationships: list[GraphRelationship] = Field(default_factory=list, description="Graph relationships")


# Backwards-compatible alias
EntityCard = ProductCard
