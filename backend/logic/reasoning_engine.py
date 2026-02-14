"""
Universal Neuro-Symbolic Reasoning Engine

A domain-agnostic reasoning engine that works with ANY business domain
by leveraging a generic 3-layer graph schema:
- Layer 1: Inventory (Items, Properties)
- Layer 2: Domain Rules (Contexts, Constraints, Risks)
- Layer 3: Playbook (Discriminators, Options, Strategies)

The engine uses:
- Vector search for semantic context detection
- Graph traversal for constraint propagation
- Entropy reduction for question selection

NO HARDCODED DOMAIN LOGIC - all knowledge is in the graph.
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum
import json


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class Operator(str, Enum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"
    IN = "IN"
    NOT_IN = "NOT_IN"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"


@dataclass
class DetectedContext:
    """A context detected via vector similarity search."""
    id: str
    name: str
    description: str
    similarity_score: float
    keywords: list[str] = field(default_factory=list)


@dataclass
class Constraint:
    """A requirement imposed by a context."""
    id: str
    target_key: str
    operator: Operator
    required_value: Any
    severity: Severity
    reason: Optional[str] = None
    source_context: Optional[str] = None


@dataclass
class Item:
    """An inventory item with its properties."""
    id: str
    name: str
    description: Optional[str] = None
    properties: dict[str, Any] = field(default_factory=dict)
    categories: list[str] = field(default_factory=list)


@dataclass
class ConstraintViolation:
    """A violation of a constraint by an item."""
    item_id: str
    item_name: str
    constraint: Constraint
    actual_value: Any
    message: str


@dataclass
class Discriminator:
    """A question to reduce entropy in item selection."""
    id: str
    name: str
    question: str
    priority: int
    options: list[dict[str, str]] = field(default_factory=list)
    why_needed: Optional[str] = None


@dataclass
class ReasoningResult:
    """The complete result of the reasoning process."""
    # Context Detection (Layer 2)
    detected_contexts: list[DetectedContext] = field(default_factory=list)

    # Constraint Propagation (Layer 2)
    active_constraints: list[Constraint] = field(default_factory=list)

    # Inventory Filtering (Layer 1)
    valid_items: list[Item] = field(default_factory=list)
    rejected_items: list[tuple[Item, ConstraintViolation]] = field(default_factory=list)

    # Entropy Reduction (Layer 3)
    needs_clarification: bool = False
    discriminator: Optional[Discriminator] = None

    # Strategies (Layer 3)
    triggered_strategies: list[dict] = field(default_factory=list)

    # Risk Assessment (Layer 2)
    detected_risks: list[dict] = field(default_factory=list)
    mitigations: list[dict] = field(default_factory=list)

    # Metadata
    reasoning_trace: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "detected_contexts": [
                {"id": c.id, "name": c.name, "score": c.similarity_score}
                for c in self.detected_contexts
            ],
            "active_constraints": [
                {
                    "id": c.id,
                    "target_key": c.target_key,
                    "operator": c.operator.value,
                    "required_value": c.required_value,
                    "severity": c.severity.value,
                    "reason": c.reason
                }
                for c in self.active_constraints
            ],
            "valid_items": [
                {"id": i.id, "name": i.name, "properties": i.properties}
                for i in self.valid_items
            ],
            "rejected_items": [
                {
                    "item": {"id": item.id, "name": item.name},
                    "violation": {
                        "constraint": v.constraint.id,
                        "reason": v.message
                    }
                }
                for item, v in self.rejected_items
            ],
            "needs_clarification": self.needs_clarification,
            "discriminator": {
                "id": self.discriminator.id,
                "question": self.discriminator.question,
                "options": self.discriminator.options,
                "why_needed": self.discriminator.why_needed
            } if self.discriminator else None,
            "detected_risks": self.detected_risks,
            "mitigations": self.mitigations,
            "reasoning_trace": self.reasoning_trace
        }


class UniversalGraphEngine:
    """
    Domain-agnostic neuro-symbolic reasoning engine.

    This engine implements the following algorithm:
    1. VECTOR MAPPING: Embed query → Find matching Contexts via KNN
    2. CONSTRAINT RETRIEVAL: Traverse (Context)-[:IMPLIES_CONSTRAINT]->(Constraint)
    3. INVENTORY FILTERING: Find Items that satisfy all Constraints
    4. ENTROPY REDUCTION: If multiple valid Items, find Discriminator to ask
    5. RISK ASSESSMENT: Check for risks and mitigations
    6. STRATEGY ACTIVATION: Trigger relevant strategies (cross-sell, warnings)

    The engine has NO hardcoded domain knowledge - everything comes from the graph.
    """

    def __init__(self, graph_connection, embedding_provider):
        """
        Initialize the engine.

        Args:
            graph_connection: Database connection (FalkorDB, Neo4j, etc.)
            embedding_provider: Function to generate embeddings (OpenAI, etc.)
        """
        self.db = graph_connection
        self.embed = embedding_provider
        self._trace = []

    def _log_trace(self, step: str, layer: int, operation: str, result: Any):
        """Log a reasoning step for explainability."""
        self._trace.append({
            "step": step,
            "layer": layer,
            "layer_name": {1: "Inventory", 2: "Domain Rules", 3: "Playbook"}.get(layer, "Unknown"),
            "operation": operation,
            "result": result
        })

    # =========================================================================
    # STEP 1: VECTOR MAPPING (Context Detection)
    # =========================================================================

    def detect_contexts(self, query: str, top_k: int = 3, threshold: float = 0.7) -> list[DetectedContext]:
        """
        Detect relevant contexts from user query using vector similarity.

        This is the "Neuro" part - using embeddings to map natural language
        to structured graph nodes.

        Args:
            query: User's natural language query
            top_k: Number of contexts to retrieve
            threshold: Minimum similarity score

        Returns:
            List of detected contexts with similarity scores
        """
        # Generate embedding for user query
        query_embedding = self.embed(query)

        # FalkorDB vector KNN query
        # This finds Context nodes whose embeddings are closest to the query
        cypher = """
        CALL db.idx.vector.queryNodes('Context', 'embedding', $top_k, vecf32($embedding))
        YIELD node, score
        WHERE score >= $threshold
        RETURN node.id AS id,
               node.name AS name,
               node.description AS description,
               node.keywords AS keywords,
               score
        ORDER BY score DESC
        """

        results = self.db.query(cypher, {
            "embedding": query_embedding,
            "top_k": top_k,
            "threshold": threshold
        })

        contexts = []
        for record in results:
            ctx = DetectedContext(
                id=record["id"],
                name=record["name"],
                description=record["description"] or "",
                similarity_score=record["score"],
                keywords=record["keywords"] or []
            )
            contexts.append(ctx)

        self._log_trace(
            step="Context Detection",
            layer=2,
            operation=f"Vector KNN search (top_k={top_k}, threshold={threshold})",
            result=[{"name": c.name, "score": round(c.similarity_score, 3)} for c in contexts]
        )

        return contexts

    def detect_contexts_by_keywords(self, query: str) -> list[DetectedContext]:
        """
        Fallback context detection using keyword matching.

        Used when vector search is not available or as supplementary detection.
        """
        query_lower = query.lower()

        cypher = """
        MATCH (ctx:Context)
        WHERE ctx.keywords IS NOT NULL
        WITH ctx, [kw IN ctx.keywords WHERE toLower($query) CONTAINS toLower(kw)] AS matched
        WHERE size(matched) > 0
        RETURN ctx.id AS id,
               ctx.name AS name,
               ctx.description AS description,
               ctx.keywords AS keywords,
               size(matched) AS match_count,
               matched[0] AS matched_keyword
        ORDER BY match_count DESC
        """

        results = self.db.query(cypher, {"query": query_lower})

        contexts = []
        for record in results:
            ctx = DetectedContext(
                id=record["id"],
                name=record["name"],
                description=record["description"] or "",
                similarity_score=0.8 + (0.05 * record["match_count"]),  # Synthetic score
                keywords=record["keywords"] or []
            )
            contexts.append(ctx)

        self._log_trace(
            step="Context Detection (Keywords)",
            layer=2,
            operation="Keyword matching fallback",
            result=[{"name": c.name, "matched": c.keywords} for c in contexts]
        )

        return contexts

    # =========================================================================
    # STEP 2: CONSTRAINT RETRIEVAL (Rule Propagation)
    # =========================================================================

    def get_constraints_for_contexts(self, context_ids: list[str]) -> list[Constraint]:
        """
        Retrieve all constraints implied by the detected contexts.

        This traverses (Context)-[:IMPLIES_CONSTRAINT]->(Constraint)
        to find all requirements that apply.

        Args:
            context_ids: IDs of detected contexts

        Returns:
            List of active constraints
        """
        if not context_ids:
            return []

        cypher = """
        MATCH (ctx:Context)-[r:IMPLIES_CONSTRAINT]->(con:Constraint)
        WHERE ctx.id IN $context_ids
        RETURN con.id AS id,
               con.target_key AS target_key,
               con.operator AS operator,
               con.required_value AS required_value,
               con.severity AS severity,
               r.reason AS reason,
               ctx.name AS source_context
        """

        results = self.db.query(cypher, {"context_ids": context_ids})

        constraints = []
        for record in results:
            constraint = Constraint(
                id=record["id"],
                target_key=record["target_key"],
                operator=Operator(record["operator"]),
                required_value=record["required_value"],
                severity=Severity(record["severity"]),
                reason=record["reason"],
                source_context=record["source_context"]
            )
            constraints.append(constraint)

        self._log_trace(
            step="Constraint Retrieval",
            layer=2,
            operation=f"Traversed IMPLIES_CONSTRAINT from {len(context_ids)} contexts",
            result=[{"key": c.target_key, "op": c.operator.value, "val": c.required_value} for c in constraints]
        )

        return constraints

    # =========================================================================
    # STEP 3: INVENTORY FILTERING (Item Selection)
    # =========================================================================

    def get_items_by_category(self, category_name: Optional[str] = None) -> list[Item]:
        """
        Retrieve items from inventory, optionally filtered by category.
        """
        if category_name:
            cypher = """
            MATCH (i:Item)-[:IN_CATEGORY]->(c:Category {name: $category})
            OPTIONAL MATCH (i)-[:HAS_PROP]->(p:Property)
            RETURN i.id AS id,
                   i.name AS name,
                   i.description AS description,
                   collect({key: p.key, value: p.value}) AS properties
            """
            params = {"category": category_name}
        else:
            cypher = """
            MATCH (i:Item)
            OPTIONAL MATCH (i)-[:HAS_PROP]->(p:Property)
            RETURN i.id AS id,
                   i.name AS name,
                   i.description AS description,
                   collect({key: p.key, value: p.value}) AS properties
            """
            params = {}

        results = self.db.query(cypher, params)

        items = []
        for record in results:
            props = {p["key"]: p["value"] for p in record["properties"] if p["key"]}
            item = Item(
                id=record["id"],
                name=record["name"],
                description=record["description"],
                properties=props
            )
            items.append(item)

        return items

    def get_items_matching_query(self, query: str) -> list[Item]:
        """
        Find items that match the user's query (by name, category, or properties).
        """
        query_lower = query.lower()

        cypher = """
        MATCH (i:Item)
        WHERE toLower(i.name) CONTAINS $query
           OR toLower(i.description) CONTAINS $query
        OPTIONAL MATCH (i)-[:HAS_PROP]->(p:Property)
        OPTIONAL MATCH (i)-[:IN_CATEGORY]->(c:Category)
        RETURN i.id AS id,
               i.name AS name,
               i.description AS description,
               collect(DISTINCT {key: p.key, value: p.value}) AS properties,
               collect(DISTINCT c.name) AS categories
        """

        results = self.db.query(cypher, {"query": query_lower})

        items = []
        for record in results:
            props = {p["key"]: p["value"] for p in record["properties"] if p["key"]}
            item = Item(
                id=record["id"],
                name=record["name"],
                description=record["description"],
                properties=props,
                categories=record["categories"] or []
            )
            items.append(item)

        self._log_trace(
            step="Item Retrieval",
            layer=1,
            operation=f"Found items matching '{query}'",
            result=[{"id": i.id, "name": i.name} for i in items]
        )

        return items

    def check_constraint(self, item: Item, constraint: Constraint) -> Optional[ConstraintViolation]:
        """
        Check if an item satisfies a single constraint.

        Returns None if satisfied, or a ConstraintViolation if not.
        """
        prop_value = item.properties.get(constraint.target_key)

        # Handle EXISTS/NOT_EXISTS operators
        if constraint.operator == Operator.EXISTS:
            if prop_value is None:
                return ConstraintViolation(
                    item_id=item.id,
                    item_name=item.name,
                    constraint=constraint,
                    actual_value=None,
                    message=f"Missing required property: {constraint.target_key}"
                )
            return None

        if constraint.operator == Operator.NOT_EXISTS:
            if prop_value is not None:
                return ConstraintViolation(
                    item_id=item.id,
                    item_name=item.name,
                    constraint=constraint,
                    actual_value=prop_value,
                    message=f"Property should not exist: {constraint.target_key}"
                )
            return None

        # If property doesn't exist and we need to check its value, it's a violation
        if prop_value is None:
            return ConstraintViolation(
                item_id=item.id,
                item_name=item.name,
                constraint=constraint,
                actual_value=None,
                message=f"Missing property '{constraint.target_key}' required by {constraint.source_context}"
            )

        # Check value-based constraints
        required = constraint.required_value
        satisfied = False

        if constraint.operator == Operator.EQUALS:
            satisfied = str(prop_value).lower() == str(required).lower()
        elif constraint.operator == Operator.NOT_EQUALS:
            satisfied = str(prop_value).lower() != str(required).lower()
        elif constraint.operator == Operator.IN:
            allowed = [v.strip().lower() for v in str(required).split(",")]
            satisfied = str(prop_value).lower() in allowed
        elif constraint.operator == Operator.NOT_IN:
            forbidden = [v.strip().lower() for v in str(required).split(",")]
            satisfied = str(prop_value).lower() not in forbidden
        elif constraint.operator == Operator.GREATER_THAN:
            try:
                satisfied = float(prop_value) > float(required)
            except (ValueError, TypeError):
                satisfied = False
        elif constraint.operator == Operator.LESS_THAN:
            try:
                satisfied = float(prop_value) < float(required)
            except (ValueError, TypeError):
                satisfied = False

        if not satisfied:
            return ConstraintViolation(
                item_id=item.id,
                item_name=item.name,
                constraint=constraint,
                actual_value=prop_value,
                message=f"{constraint.target_key}={prop_value} does not satisfy {constraint.operator.value} {required} (required by {constraint.source_context}: {constraint.reason})"
            )

        return None

    def filter_items_by_constraints(
        self,
        items: list[Item],
        constraints: list[Constraint]
    ) -> tuple[list[Item], list[tuple[Item, ConstraintViolation]]]:
        """
        Filter items by checking all constraints.

        Returns:
            Tuple of (valid_items, rejected_items_with_violations)
        """
        valid = []
        rejected = []

        for item in items:
            violations = []
            for constraint in constraints:
                violation = self.check_constraint(item, constraint)
                if violation:
                    violations.append(violation)

            if violations:
                # Use the most severe violation for rejection reason
                critical = [v for v in violations if v.constraint.severity == Severity.CRITICAL]
                if critical:
                    rejected.append((item, critical[0]))
                else:
                    rejected.append((item, violations[0]))
            else:
                valid.append(item)

        self._log_trace(
            step="Inventory Filtering",
            layer=1,
            operation=f"Checked {len(items)} items against {len(constraints)} constraints",
            result={
                "valid": [i.name for i in valid],
                "rejected": [f"{i.name}: {v.message}" for i, v in rejected]
            }
        )

        return valid, rejected

    # =========================================================================
    # STEP 4: ENTROPY REDUCTION (Question Selection)
    # =========================================================================

    def get_discriminators_for_items(self, items: list[Item]) -> list[Discriminator]:
        """
        Find discriminators that can reduce entropy among the valid items.

        Looks for properties that vary across items and have linked Discriminators.
        """
        if len(items) <= 1:
            return []

        item_ids = [i.id for i in items]

        # Find properties that vary across the items and have discriminators
        cypher = """
        MATCH (i:Item)-[:HAS_PROP]->(p:Property)-[:DEPENDS_ON]->(d:Discriminator)
        WHERE i.id IN $item_ids
        WITH d, p.key AS prop_key, collect(DISTINCT p.value) AS values
        WHERE size(values) > 1
        OPTIONAL MATCH (d)-[:HAS_OPTION]->(o:Option)
        RETURN d.id AS id,
               d.name AS name,
               d.question AS question,
               d.priority AS priority,
               prop_key,
               values AS varying_values,
               collect({value: o.value, description: o.description}) AS options
        ORDER BY d.priority ASC
        """

        results = self.db.query(cypher, {"item_ids": item_ids})

        discriminators = []
        for record in results:
            disc = Discriminator(
                id=record["id"],
                name=record["name"],
                question=record["question"],
                priority=record["priority"] or 99,
                options=[o for o in record["options"] if o["value"]],
                why_needed=f"Property '{record['prop_key']}' varies: {record['varying_values']}"
            )
            discriminators.append(disc)

        self._log_trace(
            step="Entropy Reduction",
            layer=3,
            operation=f"Found discriminators for {len(items)} valid items",
            result=[{"name": d.name, "why": d.why_needed} for d in discriminators]
        )

        return discriminators

    def get_next_discriminator(self, items: list[Item], asked: list[str] = None) -> Optional[Discriminator]:
        """
        Get the next most important discriminator to ask.

        Args:
            items: Current valid items
            asked: List of discriminator IDs already asked

        Returns:
            The next Discriminator to ask, or None if no more needed
        """
        asked = asked or []
        discriminators = self.get_discriminators_for_items(items)

        # Filter out already asked
        remaining = [d for d in discriminators if d.id not in asked]

        if not remaining:
            return None

        # Return highest priority (lowest number)
        return min(remaining, key=lambda d: d.priority)

    # =========================================================================
    # STEP 5: RISK ASSESSMENT
    # =========================================================================

    def assess_risks(self, context_ids: list[str], item_ids: list[str]) -> tuple[list[dict], list[dict]]:
        """
        Assess risks based on contexts and check for mitigations.

        Returns:
            Tuple of (detected_risks, available_mitigations)
        """
        if not context_ids:
            return [], []

        # Find risks generated by contexts
        cypher_risks = """
        MATCH (ctx:Context)-[r:GENERATES_RISK]->(risk:Risk)
        WHERE ctx.id IN $context_ids
        RETURN risk.id AS id,
               risk.name AS name,
               risk.description AS description,
               risk.severity AS severity,
               r.probability AS probability,
               ctx.name AS source_context
        """

        risk_results = self.db.query(cypher_risks, {"context_ids": context_ids})

        risks = []
        for record in risk_results:
            risks.append({
                "id": record["id"],
                "name": record["name"],
                "description": record["description"],
                "severity": record["severity"],
                "probability": record["probability"],
                "source": record["source_context"]
            })

        # Find mitigations if we have items
        mitigations = []
        if item_ids and risks:
            risk_ids = [r["id"] for r in risks]
            cypher_mitigations = """
            MATCH (i:Item)-[:MITIGATES]->(risk:Risk)
            WHERE i.id IN $item_ids AND risk.id IN $risk_ids
            RETURN i.id AS item_id,
                   i.name AS item_name,
                   risk.id AS risk_id,
                   risk.name AS risk_name
            """

            mit_results = self.db.query(cypher_mitigations, {
                "item_ids": item_ids,
                "risk_ids": risk_ids
            })

            for record in mit_results:
                mitigations.append({
                    "item_id": record["item_id"],
                    "item_name": record["item_name"],
                    "mitigates_risk": record["risk_name"]
                })

        self._log_trace(
            step="Risk Assessment",
            layer=2,
            operation=f"Assessed risks for {len(context_ids)} contexts",
            result={"risks": [r["name"] for r in risks], "mitigations": len(mitigations)}
        )

        return risks, mitigations

    # =========================================================================
    # STEP 6: STRATEGY ACTIVATION
    # =========================================================================

    def get_triggered_strategies(self, context_ids: list[str], item_ids: list[str]) -> list[dict]:
        """
        Get strategies triggered by contexts or enabled by items.

        Strategies can be: cross-sell suggestions, warnings, recommendations.
        """
        strategies = []

        # Context-triggered strategies
        if context_ids:
            cypher_ctx = """
            MATCH (ctx:Context)-[:TRIGGERS_STRATEGY]->(st:Strategy)
            WHERE ctx.id IN $context_ids
            RETURN st.id AS id,
                   st.name AS name,
                   st.type AS type,
                   st.message AS message,
                   st.priority AS priority,
                   ctx.name AS trigger
            """

            results = self.db.query(cypher_ctx, {"context_ids": context_ids})
            for record in results:
                strategies.append({
                    "id": record["id"],
                    "name": record["name"],
                    "type": record["type"],
                    "message": record["message"],
                    "priority": record["priority"],
                    "trigger": f"Context: {record['trigger']}"
                })

        # Item-enabled strategies (cross-sell)
        if item_ids:
            cypher_item = """
            MATCH (i:Item)-[:ENABLES_STRATEGY]->(st:Strategy)
            WHERE i.id IN $item_ids
            RETURN st.id AS id,
                   st.name AS name,
                   st.type AS type,
                   st.message AS message,
                   st.priority AS priority,
                   i.name AS trigger
            """

            results = self.db.query(cypher_item, {"item_ids": item_ids})
            for record in results:
                strategies.append({
                    "id": record["id"],
                    "name": record["name"],
                    "type": record["type"],
                    "message": record["message"],
                    "priority": record["priority"],
                    "trigger": f"Item: {record['trigger']}"
                })

        # Sort by priority
        strategies.sort(key=lambda s: s.get("priority", 99))

        self._log_trace(
            step="Strategy Activation",
            layer=3,
            operation="Checked triggered strategies",
            result=[s["name"] for s in strategies]
        )

        return strategies

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    def process_query(
        self,
        user_query: str,
        item_hint: Optional[str] = None,
        asked_discriminators: list[str] = None,
        user_answers: dict[str, str] = None
    ) -> ReasoningResult:
        """
        Main entry point for the reasoning engine.

        Executes the full neuro-symbolic reasoning pipeline:
        1. Detect contexts from query (vector + keyword)
        2. Retrieve constraints from contexts
        3. Find matching items
        4. Filter items by constraints
        5. Check if clarification needed
        6. Assess risks and strategies

        Args:
            user_query: Natural language query from user
            item_hint: Optional hint about which item family/category to search
            asked_discriminators: List of already-asked discriminator IDs
            user_answers: Dict of discriminator_id -> user's answer

        Returns:
            Complete ReasoningResult with all findings
        """
        self._trace = []
        result = ReasoningResult()

        # =====================================================================
        # STEP 1: CONTEXT DETECTION
        # =====================================================================
        try:
            # Try vector search first
            contexts = self.detect_contexts(user_query)
        except Exception as e:
            # Fallback to keyword matching
            self._log_trace("Context Detection", 2, "Vector search failed, using keywords", str(e))
            contexts = self.detect_contexts_by_keywords(user_query)

        result.detected_contexts = contexts
        context_ids = [c.id for c in contexts]

        # =====================================================================
        # STEP 2: CONSTRAINT RETRIEVAL
        # =====================================================================
        constraints = self.get_constraints_for_contexts(context_ids)
        result.active_constraints = constraints

        # =====================================================================
        # STEP 3: ITEM RETRIEVAL
        # =====================================================================
        if item_hint:
            items = self.get_items_matching_query(item_hint)
        else:
            # Extract potential item mentions from query
            items = self.get_items_matching_query(user_query)

        if not items:
            # Fallback: get all items
            items = self.get_items_by_category()

        # =====================================================================
        # STEP 4: CONSTRAINT FILTERING
        # =====================================================================
        valid_items, rejected = self.filter_items_by_constraints(items, constraints)
        result.valid_items = valid_items
        result.rejected_items = rejected

        # =====================================================================
        # STEP 5: ENTROPY REDUCTION
        # =====================================================================
        if len(valid_items) > 1:
            discriminator = self.get_next_discriminator(valid_items, asked_discriminators)
            if discriminator:
                result.needs_clarification = True
                result.discriminator = discriminator

        # =====================================================================
        # STEP 6: RISK ASSESSMENT
        # =====================================================================
        valid_item_ids = [i.id for i in valid_items]
        risks, mitigations = self.assess_risks(context_ids, valid_item_ids)
        result.detected_risks = risks
        result.mitigations = mitigations

        # =====================================================================
        # STEP 7: STRATEGY ACTIVATION
        # =====================================================================
        strategies = self.get_triggered_strategies(context_ids, valid_item_ids)
        result.triggered_strategies = strategies

        # =====================================================================
        # ATTACH REASONING TRACE
        # =====================================================================
        result.reasoning_trace = self._trace

        return result


# =============================================================================
# LLM NARRATIVE LAYER
# =============================================================================

class LLMNarrativeLayer:
    """
    Translates graph reasoning results into natural language.

    The LLM does NOT make decisions - it only:
    1. Extracts parameters from user text
    2. Narrates the graph results in a human-friendly way
    """

    def __init__(self, llm_client):
        self.llm = llm_client

    def narrate_result(self, result: ReasoningResult, user_query: str) -> str:
        """
        Convert a ReasoningResult into natural language response.
        """
        # Build a structured prompt for the LLM
        prompt = f"""You are a Senior Application Engineer narrating graph reasoning results.

USER QUERY: {user_query}

REASONING RESULT:
- Detected Contexts: {[c.name for c in result.detected_contexts]}
- Active Constraints: {[(c.target_key, c.operator.value, c.required_value) for c in result.active_constraints]}
- Valid Items: {[i.name for i in result.valid_items]}
- Rejected Items: {[(i.name, v.message) for i, v in result.rejected_items]}
- Needs Clarification: {result.needs_clarification}
- Question to Ask: {result.discriminator.question if result.discriminator else None}
- Detected Risks: {[r['name'] for r in result.detected_risks]}

INSTRUCTIONS:
1. Write a natural, consultant-style response
2. If items were rejected, explain WHY using physics/real-world reasoning
3. If clarification is needed, explain WHY you need that information
4. Do NOT mention "graph", "nodes", "constraints" - speak naturally
5. Use the Sandwich Method for rejections: acknowledge intent, explain constraint, offer solution

Write the response:"""

        response = self.llm.generate(prompt)
        return response

    def extract_parameters(self, user_text: str, discriminator: Discriminator) -> Optional[str]:
        """
        Extract the answer to a discriminator from user text.
        """
        prompt = f"""Extract the user's answer to this question from their text.

QUESTION: {discriminator.question}
VALID OPTIONS: {[o['value'] for o in discriminator.options]}
USER TEXT: {user_text}

If the user provided a clear answer matching one of the options, return just that option value.
If the user's answer is unclear or doesn't match, return "UNCLEAR".

EXTRACTED ANSWER:"""

        answer = self.llm.generate(prompt).strip()

        if answer == "UNCLEAR":
            return None

        # Validate against options
        valid_values = [o['value'].lower() for o in discriminator.options]
        if answer.lower() in valid_values:
            return answer

        return None
