"""
Engine Adapter - Integrates UniversalGraphEngine with existing API

This module provides a bridge between the new domain-agnostic engine
and the existing FastAPI endpoints.
"""

import os
from typing import Optional
from dataclasses import dataclass

from logic.reasoning_engine import (
    UniversalGraphEngine,
    ReasoningResult,
    LLMNarrativeLayer
)


@dataclass
class ConsultResponse:
    """Response format matching existing API."""
    response_type: str  # "FINAL_ANSWER" or "CLARIFICATION_NEEDED"
    reasoning_summary: list[dict]
    content_segments: list[dict]
    product_card: Optional[dict] = None
    clarification: Optional[dict] = None
    risk_detected: bool = False
    risk_severity: Optional[str] = None
    policy_warnings: list[str] = None

    def to_dict(self) -> dict:
        return {
            "response_type": self.response_type,
            "reasoning_summary": self.reasoning_summary,
            "content_segments": self.content_segments,
            "product_card": self.product_card,
            "clarification": self.clarification,
            "risk_detected": self.risk_detected,
            "risk_severity": self.risk_severity,
            "policy_warnings": self.policy_warnings or [],
        }


class GraphEngineAdapter:
    """
    Adapter that wraps UniversalGraphEngine for the existing API.

    This class:
    1. Initializes the generic engine with database connection
    2. Converts engine results to the existing response format
    3. Uses LLM to narrate results in natural language
    """

    def __init__(self, db_connection, llm_client):
        """
        Initialize the adapter.

        Args:
            db_connection: Database connection (FalkorDB graph)
            llm_client: LLM client for narrative generation
        """
        self.engine = UniversalGraphEngine(
            graph_connection=db_connection,
            embedding_provider=self._get_embedding
        )
        self.narrator = LLMNarrativeLayer(llm_client)
        self.llm = llm_client

    def _get_embedding(self, text: str) -> list[float]:
        """Generate embedding using configured provider."""
        from embeddings import generate_embedding
        return generate_embedding(text)

    def _build_reasoning_summary(self, result: ReasoningResult) -> list[dict]:
        """Convert reasoning trace to UI-friendly summary with graph traversals."""
        summary = []

        # Step 1: Context Detection
        if result.detected_contexts:
            ctx_names = [c.name for c in result.detected_contexts]
            summary.append({
                "step": "INTENT ANALYSIS",
                "icon": "🔍",
                "description": f"Detected contexts: {', '.join(ctx_names)}",
                "graph_traversals": [{
                    "layer": 2,
                    "layer_name": "Domain Rules",
                    "operation": "Context Detection (Vector KNN)",
                    "cypher_pattern": "CALL db.idx.vector.queryNodes('Context', 'embedding', ...)",
                    "nodes_visited": [f"Context:{c.name}" for c in result.detected_contexts],
                    "relationships": [],
                    "result_summary": f"Matched {len(result.detected_contexts)} contexts"
                }]
            })

        # Step 2: Constraint Retrieval
        if result.active_constraints:
            constraints_desc = [f"{c.target_key} {c.operator.value} {c.required_value}"
                               for c in result.active_constraints[:3]]
            summary.append({
                "step": "CONSTRAINT RETRIEVAL",
                "icon": "⚖️",
                "description": f"Active constraints: {', '.join(constraints_desc)}",
                "graph_traversals": [{
                    "layer": 2,
                    "layer_name": "Domain Rules",
                    "operation": "Constraint Propagation",
                    "cypher_pattern": "(Context)-[:IMPLIES_CONSTRAINT]->(Constraint)",
                    "nodes_visited": [f"Constraint:{c.id}" for c in result.active_constraints],
                    "relationships": ["IMPLIES_CONSTRAINT"],
                    "result_summary": f"Found {len(result.active_constraints)} constraints"
                }]
            })

        # Step 3: Inventory Filtering
        valid_count = len(result.valid_items)
        rejected_count = len(result.rejected_items)
        summary.append({
            "step": "INVENTORY FILTERING",
            "icon": "🔒",
            "description": f"Valid items: {valid_count}, Rejected: {rejected_count}",
            "graph_traversals": [{
                "layer": 1,
                "layer_name": "Inventory",
                "operation": "Item Filtering",
                "cypher_pattern": "(Item)-[:HAS_PROP]->(Property) WHERE ...",
                "nodes_visited": [f"Item:{i.name}" for i in result.valid_items],
                "relationships": ["HAS_PROP", "SATISFIES"],
                "result_summary": f"Filtered {valid_count + rejected_count} items → {valid_count} valid"
            }]
        })

        # Step 4: Risk/Clarification
        if result.detected_risks:
            risk_names = [r["name"] for r in result.detected_risks]
            summary.append({
                "step": "RISK ASSESSMENT",
                "icon": "⚠️",
                "description": f"Detected risks: {', '.join(risk_names)}",
                "graph_traversals": [{
                    "layer": 2,
                    "layer_name": "Domain Rules",
                    "operation": "Risk Detection",
                    "cypher_pattern": "(Context)-[:GENERATES_RISK]->(Risk)",
                    "nodes_visited": [f"Risk:{r['name']}" for r in result.detected_risks],
                    "relationships": ["GENERATES_RISK"],
                    "result_summary": f"Found {len(result.detected_risks)} risks"
                }]
            })

        if result.needs_clarification and result.discriminator:
            summary.append({
                "step": "ENTROPY REDUCTION",
                "icon": "❓",
                "description": f"Need to ask: {result.discriminator.name}",
                "graph_traversals": [{
                    "layer": 3,
                    "layer_name": "Playbook",
                    "operation": "Discriminator Selection",
                    "cypher_pattern": "(Property)-[:DEPENDS_ON]->(Discriminator)",
                    "nodes_visited": [f"Discriminator:{result.discriminator.name}"],
                    "relationships": ["DEPENDS_ON", "HAS_OPTION"],
                    "result_summary": result.discriminator.why_needed
                }]
            })

        return summary

    def _build_content_segments(self, result: ReasoningResult, narrative: str) -> list[dict]:
        """Build content segments from reasoning result and narrative."""
        segments = []

        # Split narrative into sentences and tag appropriately
        sentences = narrative.split(". ")

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Detect segment type based on content
            if any(ctx.name.lower() in sentence.lower() for ctx in result.detected_contexts):
                # Mentions a detected context
                segments.append({
                    "text": sentence + ". ",
                    "type": "INFERENCE",
                    "inference_logic": "Context-based requirement from domain rules"
                })
            elif any(item.name.lower() in sentence.lower() for item in result.valid_items):
                # Mentions a valid item
                item = next((i for i in result.valid_items if i.name.lower() in sentence.lower()), None)
                if item:
                    segments.append({
                        "text": sentence + ". ",
                        "type": "GRAPH_FACT",
                        "source_id": item.id,
                        "node_type": "Item",
                        "evidence_snippet": item.description or item.name
                    })
                else:
                    segments.append({"text": sentence + ". ", "type": "GENERAL"})
            else:
                segments.append({"text": sentence + ". ", "type": "GENERAL"})

        return segments

    def _build_product_card(self, result: ReasoningResult) -> Optional[dict]:
        """Build product card if we have a single valid item."""
        if len(result.valid_items) != 1:
            return None

        item = result.valid_items[0]
        return {
            "title": item.name,
            "specs": item.properties,
            "confidence": "high",
            "warning": None,
            "actions": ["Add to Quote", "View Datasheet"]
        }

    def _build_clarification(self, result: ReasoningResult) -> Optional[dict]:
        """Build clarification request if needed."""
        if not result.needs_clarification or not result.discriminator:
            return None

        disc = result.discriminator
        return {
            "missing_info": disc.name,
            "why_needed": disc.why_needed or "Required to select the correct product variant",
            "question": disc.question,
            "options": disc.options
        }

    def process_query(self, user_query: str, context: dict = None) -> ConsultResponse:
        """
        Process a user query through the universal engine.

        Args:
            user_query: Natural language query
            context: Optional context (previous answers, hints)

        Returns:
            ConsultResponse matching existing API format
        """
        # Extract any previous answers from context
        asked_discriminators = context.get("asked_discriminators", []) if context else []
        item_hint = context.get("item_hint") if context else None

        # Run the engine
        result = self.engine.process_query(
            user_query=user_query,
            item_hint=item_hint,
            asked_discriminators=asked_discriminators
        )

        # Generate narrative using LLM
        try:
            narrative = self.narrator.narrate_result(result, user_query)
        except Exception as e:
            # Fallback to simple narrative
            narrative = self._simple_narrative(result)

        # Build response
        response_type = "CLARIFICATION_NEEDED" if result.needs_clarification else "FINAL_ANSWER"

        # Check for critical risks
        critical_risks = [r for r in result.detected_risks if r.get("severity") == "CRITICAL"]
        risk_detected = len(critical_risks) > 0 or len(result.rejected_items) > 0
        risk_severity = "CRITICAL" if critical_risks else ("WARNING" if result.detected_risks else None)

        # Build policy warnings
        policy_warnings = []
        for item, violation in result.rejected_items:
            if violation.constraint.severity.value == "CRITICAL":
                policy_warnings.append(
                    f"REJECTED: {item.name} - {violation.message}"
                )

        return ConsultResponse(
            response_type=response_type,
            reasoning_summary=self._build_reasoning_summary(result),
            content_segments=self._build_content_segments(result, narrative),
            product_card=self._build_product_card(result),
            clarification=self._build_clarification(result),
            risk_detected=risk_detected,
            risk_severity=risk_severity,
            policy_warnings=policy_warnings
        )

    def _simple_narrative(self, result: ReasoningResult) -> str:
        """Generate simple narrative without LLM."""
        parts = []

        if result.detected_contexts:
            ctx_names = [c.name for c in result.detected_contexts]
            parts.append(f"I detected the following contexts: {', '.join(ctx_names)}.")

        if result.active_constraints:
            parts.append(f"This implies {len(result.active_constraints)} technical requirements.")

        if result.valid_items:
            item_names = [i.name for i in result.valid_items[:3]]
            parts.append(f"Valid products: {', '.join(item_names)}.")

        if result.rejected_items:
            parts.append(f"{len(result.rejected_items)} products were rejected due to constraint violations.")

        if result.needs_clarification and result.discriminator:
            parts.append(f"To proceed, I need to know: {result.discriminator.question}")

        return " ".join(parts)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_engine_adapter() -> GraphEngineAdapter:
    """
    Factory function to create an engine adapter with FalkorDB connection.

    Returns:
        Configured GraphEngineAdapter
    """
    try:
            from falkordb import FalkorDB

            db = FalkorDB(
                host=os.getenv("FALKORDB_HOST", "localhost"),
                port=int(os.getenv("FALKORDB_PORT", 6379))
            )
            from config_loader import get_config
            _graph_name = os.getenv("FALKORDB_GRAPH", get_config().graph_name or "default")
            graph = db.select_graph(_graph_name)

            # Simple LLM wrapper
            class SimpleLLM:
                def generate(self, prompt):
                    import google.generativeai as genai
                    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
                    response = genai.GenerativeModel("gemini-2.0-flash").generate_content(prompt)
                    return response.text

            return GraphEngineAdapter(graph, SimpleLLM())

    except ImportError:
        # FalkorDB is the only supported backend
        raise ImportError("FalkorDB package is required. Install with: pip install falkordb")
