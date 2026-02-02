import os
from typing import Optional
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")

VECTOR_INDEX_NAME = "concept_embeddings"


def _format_display_label(name: str, max_length: int = 18) -> str:
    """Format a node name for display in the graph visualization.

    Creates human-readable labels:
    - GDC-FLEX-600x600 -> "GDC FLEX\n600x600"
    - RF - Stainless Steel -> "RF"
    - Long names get intelligently truncated
    """
    import re

    if not name:
        return "Node"

    # If short enough, return as-is
    if len(name) <= max_length:
        return name

    # Pattern: Product codes with dimensions (e.g., GDB-600x600, GDC-FLEX-600x600)
    dims_match = re.search(r'(\d{3,4}x\d{3,4})', name)
    if dims_match:
        dims = dims_match.group(1)
        prefix = name[:dims_match.start()].rstrip('-').rstrip()
        # Clean up prefix
        prefix = re.sub(r'[-_]+', ' ', prefix).strip()
        if prefix:
            return f"{prefix}\n{dims}"
        return dims

    # Pattern: Code with dash separator (e.g., FILTER-12345, PT-600x600)
    code_match = re.match(r'^([A-Z]{2,6})[-_](.+)$', name, re.IGNORECASE)
    if code_match:
        prefix = code_match.group(1)
        suffix = code_match.group(2)
        if len(suffix) <= 12:
            return f"{prefix}\n{suffix}"
        return f"{prefix}\n{suffix[:10]}.."

    # For materials/descriptions with " - "
    if " - " in name:
        code = name.split(" - ")[0].strip()
        return code if len(code) <= max_length else code[:max_length-2] + ".."

    # For names with spaces, try to break intelligently
    if " " in name and len(name) > max_length:
        words = name.split()
        line1 = words[0]
        line2 = " ".join(words[1:])
        if len(line2) > 12:
            line2 = line2[:10] + ".."
        return f"{line1}\n{line2}"

    # Default: truncate with ellipsis
    return name[:max_length-2] + ".."
VECTOR_DIMENSIONS = 3072

class Neo4jConnection:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI")
        self.user = os.getenv("NEO4J_USER")
        self.password = os.getenv("NEO4J_PASSWORD")
        self.database = os.getenv("NEO4J_DATABASE", "neo4j")
        self.driver = None

    def connect(self):
        if not self.driver:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                max_connection_lifetime=300,  # 5 minutes
                keep_alive=True,
            )
        return self.driver

    def reconnect(self):
        """Force reconnection by closing existing driver and creating new one."""
        if self.driver:
            try:
                self.driver.close()
            except Exception:
                pass
            self.driver = None
        return self.connect()

    def close(self):
        if self.driver:
            self.driver.close()

    def _execute_with_retry(self, query_func, max_retries=2):
        """Execute a query function with automatic retry on connection failure."""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return query_func()
            except (ServiceUnavailable, SessionExpired) as e:
                last_error = e
                if attempt < max_retries:
                    # Connection is stale, reconnect and retry
                    self.reconnect()
                else:
                    raise
            except Exception as e:
                # Check if it's a connection-related error by message
                error_msg = str(e).lower()
                if "defunct" in error_msg or "connection" in error_msg:
                    last_error = e
                    if attempt < max_retries:
                        self.reconnect()
                    else:
                        raise
                else:
                    raise
        raise last_error

    def verify_connection(self):
        """Verify the connection and return database info"""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("RETURN 1 AS test")
                return result.single()["test"] == 1
        return self._execute_with_retry(_query)

    def get_node_count(self):
        """Get count of all nodes in the database"""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("MATCH (n) RETURN count(n) AS count")
                return result.single()["count"]
        return self._execute_with_retry(_query)

    def get_relationship_count(self):
        """Get count of all relationships in the database"""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("MATCH ()-[r]->() RETURN count(r) AS count")
                return result.single()["count"]
        return self._execute_with_retry(_query)

    def clear_graph(self):
        """Delete all nodes and relationships from the database"""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                session.run("MATCH (n) DETACH DELETE n")
                return True
        return self._execute_with_retry(_query)

    def get_graph_data(self):
        """Get all nodes and relationships for visualization"""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # Get all nodes
                nodes_result = session.run("""
                    MATCH (n)
                    RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties
                """)
                nodes = []
                for record in nodes_result:
                    node_props = dict(record["properties"])
                    # Exclude embedding vectors from visualization (they're huge)
                    node_props.pop("embedding", None)
                    name = node_props.get("name") or node_props.get("title") or node_props.get("id") or f"Node {record['id']}"
                    nodes.append({
                        "id": str(record["id"]),
                        "label": record["labels"][0] if record["labels"] else "Node",
                        "name": str(name),
                        "properties": node_props
                    })

                # Get all relationships
                rels_result = session.run("""
                    MATCH (a)-[r]->(b)
                    RETURN elementId(r) AS id, type(r) AS type, elementId(a) AS source, elementId(b) AS target, properties(r) AS properties
                """)
                relationships = []
                for record in rels_result:
                    relationships.append({
                        "id": str(record["id"]),
                        "type": record["type"],
                        "source": str(record["source"]),
                        "target": str(record["target"]),
                        "properties": dict(record["properties"])
                    })

                return {"nodes": nodes, "relationships": relationships}
        return self._execute_with_retry(_query)

    def fetch_graph_neighborhood(self, node_id: str, depth: int = 1, max_nodes: int = 50) -> dict:
        """Fetch neighborhood of a node - generic, works with ANY node type.

        Args:
            node_id: The node identifier (can be elementId or name property)
            depth: How many hops to traverse (default 1)
            max_nodes: Maximum number of neighbor nodes to return

        Returns:
            dict with center_node, nodes[], relationships[], truncated
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # First, find the center node by elementId or name
                center_result = session.run("""
                    MATCH (center)
                    WHERE elementId(center) = $node_id OR center.name = $node_id
                    RETURN elementId(center) AS id, labels(center) AS labels, properties(center) AS properties
                    LIMIT 1
                """, node_id=node_id)

                center_record = center_result.single()
                if not center_record:
                    return None

                center_props = dict(center_record["properties"])
                center_props.pop("embedding", None)
                center_name = (center_props.get("name") or center_props.get("title") or
                              center_props.get("id") or f"Node {center_record['id']}")

                center_node = {
                    "id": str(center_record["id"]),
                    "labels": list(center_record["labels"]),
                    "name": str(center_name),
                    "display_label": _format_display_label(str(center_name)),
                    "properties": center_props
                }

                # Fetch neighborhood using variable-length path
                # This works without APOC and handles any depth
                neighbor_result = session.run("""
                    MATCH (center)-[r*1..""" + str(depth) + """]-(neighbor)
                    WHERE elementId(center) = $center_id
                    WITH DISTINCT neighbor, r
                    LIMIT $max_nodes
                    RETURN elementId(neighbor) AS id, labels(neighbor) AS labels, properties(neighbor) AS properties
                """, center_id=center_record["id"], max_nodes=max_nodes)

                nodes = [center_node]
                node_ids = {center_record["id"]}

                neighbor_count = 0
                for record in neighbor_result:
                    neighbor_count += 1
                    node_props = dict(record["properties"])
                    node_props.pop("embedding", None)
                    name = (node_props.get("name") or node_props.get("title") or
                           node_props.get("id") or f"Node {record['id']}")

                    if record["id"] not in node_ids:
                        nodes.append({
                            "id": str(record["id"]),
                            "labels": list(record["labels"]),
                            "name": str(name),
                            "display_label": _format_display_label(str(name)),
                            "properties": node_props
                        })
                        node_ids.add(record["id"])

                # Fetch all relationships between the collected nodes
                if len(node_ids) > 1:
                    node_id_list = list(node_ids)
                    rels_result = session.run("""
                        MATCH (a)-[r]->(b)
                        WHERE elementId(a) IN $node_ids AND elementId(b) IN $node_ids
                        RETURN elementId(r) AS id, type(r) AS type,
                               elementId(a) AS source, elementId(b) AS target,
                               properties(r) AS properties
                    """, node_ids=node_id_list)

                    relationships = []
                    for record in rels_result:
                        relationships.append({
                            "id": str(record["id"]),
                            "type": record["type"],
                            "source": str(record["source"]),
                            "target": str(record["target"]),
                            "properties": dict(record["properties"])
                        })
                else:
                    relationships = []

                return {
                    "center_node": center_node,
                    "nodes": nodes,
                    "relationships": relationships,
                    "truncated": neighbor_count >= max_nodes
                }

        return self._execute_with_retry(_query)

    # Vector Index Methods
    def create_vector_index(self, index_name: str = VECTOR_INDEX_NAME, dimensions: int = VECTOR_DIMENSIONS):
        """Create a vector index on Concept.embedding for semantic search."""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                session.run(f"""
                    CREATE VECTOR INDEX {index_name} IF NOT EXISTS
                    FOR (c:Concept) ON (c.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {dimensions},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                """)
                return True
        return self._execute_with_retry(_query)

    def vector_search_concepts(self, query_embedding: list[float], top_k: int = 3) -> list[dict]:
        """Perform vector similarity search on Concept nodes.

        Args:
            query_embedding: The query embedding vector
            top_k: Number of results to return

        Returns:
            List of dicts with concept name and similarity score
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
                    YIELD node, score
                    RETURN node.name AS concept, node.description AS description, score
                """, index_name=VECTOR_INDEX_NAME, top_k=top_k, embedding=query_embedding)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    # Generic Node/Relationship Creation
    def create_node(self, label: str, properties: dict) -> dict:
        """Create or merge a node with given label and properties.

        Uses MERGE to avoid duplicates based on 'name' property.
        """
        name = properties.get("name")
        if not name:
            raise ValueError("Node must have a 'name' property")

        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run(f"""
                    MERGE (n:{label} {{name: $name}})
                    SET n += $properties
                    RETURN n, id(n) AS id
                """, name=name, properties=properties)
                record = result.single()
                if record:
                    return {"id": record["id"], "properties": dict(record["n"])}
                return None
        return self._execute_with_retry(_query)

    def create_safety_risk_node(self, properties: dict) -> dict:
        """Create a SafetyRisk node with dual labels (Observation:SafetyRisk).

        This node is both an Observation (for normal graph traversal) and
        a SafetyRisk (for priority safety checking).

        Required properties:
        - name: Unique identifier
        - type: "SAFETY_CRITICAL"
        - description: HAZARD + PROHIBITION + REQUIRED format
        - hazard_trigger: What input causes the risk (e.g., "Standard Polyester Filters")
        - hazard_environment: The dangerous condition (e.g., "Wood Sanding / ATEX Zone 22")
        - safe_alternative: The required safe option (e.g., "Conductive Filters")
        """
        name = properties.get("name")
        if not name:
            raise ValueError("SafetyRisk node must have a 'name' property")

        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # Create node with both Observation and SafetyRisk labels
                result = session.run("""
                    MERGE (n:Observation:SafetyRisk {name: $name})
                    SET n += $properties
                    RETURN n, id(n) AS id
                """, name=name, properties=properties)
                record = result.single()
                if record:
                    return {"id": record["id"], "properties": dict(record["n"])}
                return None
        return self._execute_with_retry(_query)

    def create_triggers_risk_relationship(self, concept_name: str, safety_risk_name: str) -> dict:
        """Create a TRIGGERS_RISK relationship from a Concept to a SafetyRisk node.

        This relationship indicates that a particular concept (e.g., "Standard Polyester Filters")
        can trigger a safety risk when present in a query context.
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (c:Concept {name: $concept_name})
                    MATCH (sr:SafetyRisk {name: $safety_risk_name})
                    MERGE (c)-[r:TRIGGERS_RISK]->(sr)
                    RETURN r
                """, concept_name=concept_name, safety_risk_name=safety_risk_name)
                return result.single() is not None
        return self._execute_with_retry(_query)

    def create_relationship(
        self,
        from_label: str,
        from_name: str,
        rel_type: str,
        to_label: str,
        to_name: str,
        properties: Optional[dict] = None
    ) -> bool:
        """Create a relationship between two nodes.

        Args:
            from_label: Label of the source node
            from_name: Name of the source node
            rel_type: Type of relationship
            to_label: Label of the target node
            to_name: Name of the target node
            properties: Optional relationship properties

        Returns:
            True if relationship was created
        """
        props = properties or {}

        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                session.run(f"""
                    MATCH (a:{from_label} {{name: $from_name}})
                    MATCH (b:{to_label} {{name: $to_name}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    SET r += $properties
                """, from_name=from_name, to_name=to_name, properties=props)
                return True
        return self._execute_with_retry(_query)

    # Graph Traversal Methods
    def get_observations_for_concept(self, concept_name: str) -> list[dict]:
        """Traverse from Concept to Observations and Actions.

        Args:
            concept_name: The name of the concept to traverse from

        Returns:
            List of dicts with project, observation, and action info
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (c:Concept {name: $name})<-[:RELATES_TO]-(o:Observation)
                    OPTIONAL MATCH (o)-[:LED_TO]->(a:Action)
                    OPTIONAL MATCH (p:Project)-[:HAS_OBSERVATION]->(o)
                    RETURN p.name AS project, o.description AS observation,
                           a.description AS action, a.outcome AS outcome
                """, name=concept_name)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_product_by_competitor(self, competitor_name: str) -> list[dict]:
        """Look up our equivalent products for a competitor product.

        Args:
            competitor_name: Name of the competitor product

        Returns:
            List of our equivalent products with their details
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (cp:CompetitorProduct {name: $name})-[:EQUIVALENT_TO]->(p:Product)
                    RETURN p.sku AS sku, p.name AS name, p.price AS price,
                           p.dimensions AS dimensions, p.type AS type,
                           cp.manufacturer AS competitor_manufacturer
                """, name=competitor_name)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_all_products(self) -> list[dict]:
        """Get all products with their competitor mappings.

        Returns:
            List of products with competitor equivalents
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (p:Product)
                    OPTIONAL MATCH (cp:CompetitorProduct)-[:EQUIVALENT_TO]->(p)
                    RETURN p.sku AS sku, p.name AS name, p.price AS price,
                           p.dimensions AS dimensions, p.type AS type,
                           collect(cp.name) AS competitor_equivalents
                """)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def search_competitor_mentions(self, text: str) -> list[dict]:
        """Search for competitor product mentions in text.

        Args:
            text: Text to search for competitor mentions

        Returns:
            List of matching competitor products and their equivalents
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # Get all competitor products and check if they're mentioned
                result = session.run("""
                    MATCH (cp:CompetitorProduct)
                    WHERE toLower($text) CONTAINS toLower(cp.name)
                    OPTIONAL MATCH (cp)-[:EQUIVALENT_TO]->(p:Product)
                    RETURN cp.name AS competitor_product, cp.manufacturer AS manufacturer,
                           p.sku AS our_sku, p.name AS our_product, p.price AS our_price
                """, text=text)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    # Data Explorer Methods
    def get_all_projects_with_details(self) -> list[dict]:
        """Get all projects with observation counts and related concepts."""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (p:Project)
                    OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)
                    OPTIONAL MATCH (o)-[:RELATES_TO]->(c:Concept)
                    WITH p, count(DISTINCT o) AS observations_count, collect(DISTINCT c.name) AS concepts
                    RETURN p.name AS name, p.customer AS customer, p.date AS date,
                           p.summary AS summary, observations_count, concepts
                    ORDER BY p.name
                """)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_all_concepts_with_details(self) -> list[dict]:
        """Get all concepts with related observation and action counts."""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (c:Concept)
                    OPTIONAL MATCH (o:Observation)-[:RELATES_TO]->(c)
                    OPTIONAL MATCH (o)-[:LED_TO]->(a:Action)
                    WITH c, count(DISTINCT o) AS observations_count, count(DISTINCT a) AS actions_count
                    RETURN c.name AS name, c.description AS description,
                           observations_count, actions_count
                    ORDER BY c.name
                """)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_all_observations_with_details(self) -> list[dict]:
        """Get all observations with project, concepts, and actions."""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (o:Observation)
                    OPTIONAL MATCH (p:Project)-[:HAS_OBSERVATION]->(o)
                    OPTIONAL MATCH (o)-[:RELATES_TO]->(c:Concept)
                    OPTIONAL MATCH (o)-[:LED_TO]->(a:Action)
                    WITH o, p.name AS project, collect(DISTINCT c.name) AS concepts,
                         collect(DISTINCT a.description) AS actions
                    RETURN o.description AS description, o.context AS context,
                           project, concepts, actions
                    ORDER BY project, o.description
                """)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_all_actions_with_details(self) -> list[dict]:
        """Get all actions with related observations and outcomes."""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (a:Action)
                    OPTIONAL MATCH (o:Observation)-[:LED_TO]->(a)
                    OPTIONAL MATCH (p:Project)-[:HAS_OBSERVATION]->(o)
                    WITH a, count(DISTINCT o) AS observations_count,
                         collect(DISTINCT p.name) AS projects
                    RETURN a.description AS description, a.outcome AS outcome,
                           observations_count, projects
                    ORDER BY a.description
                """)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_all_competitors_with_details(self) -> list[dict]:
        """Get all competitor products with their equivalent products."""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (cp:CompetitorProduct)
                    OPTIONAL MATCH (cp)-[:EQUIVALENT_TO]->(p:Product)
                    WITH cp, collect({
                        sku: p.sku,
                        name: p.name,
                        price: p.price
                    }) AS equivalents
                    RETURN cp.name AS name, cp.manufacturer AS manufacturer, equivalents
                    ORDER BY cp.manufacturer, cp.name
                """)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_project_details(self, project_name: str) -> dict:
        """Get full project details with all related data."""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (p:Project {name: $name})
                    OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)
                    OPTIONAL MATCH (o)-[:RELATES_TO]->(c:Concept)
                    OPTIONAL MATCH (o)-[:LED_TO]->(a:Action)
                    WITH p, o, collect(DISTINCT c.name) AS obs_concepts,
                         collect(DISTINCT {description: a.description, outcome: a.outcome}) AS obs_actions
                    WITH p, collect({
                        description: o.description,
                        context: o.context,
                        concepts: obs_concepts,
                        actions: obs_actions
                    }) AS observations
                    RETURN p.name AS name, p.customer AS customer, p.date AS date,
                           p.summary AS summary, observations
                """, name=project_name)
                record = result.single()
                return dict(record) if record else None
        return self._execute_with_retry(_query)

    def get_concept_details(self, concept_name: str) -> dict:
        """Get full concept details with related observations and actions."""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (c:Concept {name: $name})
                    OPTIONAL MATCH (o:Observation)-[:RELATES_TO]->(c)
                    OPTIONAL MATCH (o)-[:LED_TO]->(a:Action)
                    OPTIONAL MATCH (p:Project)-[:HAS_OBSERVATION]->(o)
                    WITH c, collect(DISTINCT {
                        description: o.description,
                        project: p.name,
                        actions: collect(DISTINCT a.description)
                    }) AS observations
                    RETURN c.name AS name, c.description AS description, observations
                """, name=concept_name)
                record = result.single()
                return dict(record) if record else None
        return self._execute_with_retry(_query)

    # GraphRAG Hybrid Retrieval Methods
    def hybrid_retrieval(self, query_embedding: list[float], top_k: int = 5, min_score: float = 0.5) -> list[dict]:
        """Perform hybrid vector + graph retrieval for GraphRAG.

        1. Vector search on Concepts to find entry points
        2. Traverse to Events, Observations, Actions
        3. Reconstruct the decision chain (Symptom -> Constraint -> Solution)

        Args:
            query_embedding: The query embedding vector
            top_k: Number of concepts to retrieve
            min_score: Minimum similarity score threshold

        Returns:
            List of context dicts with project, events, observations, actions
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    // Step 1: Vector search for relevant concepts
                    CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
                    YIELD node as concept, score
                    WHERE score > $min_score

                    // Step 2: Find logic nodes (Observations/Actions) related to this concept
                    OPTIONAL MATCH (logic_node)-[:RELATES_TO]->(concept)
                    WHERE logic_node:Observation OR logic_node:Action

                    // Step 3: Find the Event that reported/proposed this logic
                    OPTIONAL MATCH (event:Event)-[:REPORTED|PROPOSED]->(logic_node)

                    // Step 4: Get Project context
                    OPTIONAL MATCH (event)-[:PART_OF]->(project:Project)

                    // Step 5: Get the sender
                    OPTIONAL MATCH (event)-[:SENT_BY]->(person:Person)

                    // Step 6: Find causality chain (what this revealed or addresses)
                    OPTIONAL MATCH (logic_node)-[:REVEALED]->(revealed:Observation)
                    OPTIONAL MATCH (logic_node)-[:ADDRESSES]->(addresses:Observation)
                    OPTIONAL MATCH (addressing_action:Action)-[:ADDRESSES]->(logic_node)

                    RETURN DISTINCT
                        concept.name AS concept,
                        score,
                        project.name AS project,
                        event.summary AS event_summary,
                        event.date AS event_date,
                        person.name AS sender,
                        labels(logic_node)[0] AS logic_type,
                        logic_node.type AS logic_subtype,
                        logic_node.description AS logic_description,
                        logic_node.citation AS logic_citation,
                        revealed.description AS revealed_constraint,
                        addresses.description AS addresses_problem,
                        addressing_action.description AS solution_action
                    ORDER BY score DESC
                    LIMIT 15
                """, index_name=VECTOR_INDEX_NAME, top_k=top_k, embedding=query_embedding, min_score=min_score)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def check_safety_risks(self, query_embedding: list[float], top_k: int = 5, min_score: float = 0.7) -> list[dict]:
        """PRIORITY SAFETY CHECK: Find SafetyRisk nodes only when query matches hazard scenario.

        This is NOT a general concept match - it specifically looks for SAFETY-RELATED concepts
        that indicate the query is about a potentially dangerous scenario.

        Safety-triggering concepts are those with TRIGGERS_RISK relationships, which are only
        created for concepts explicitly tied to safety hazards (e.g., "Wood Dust", "ATEX Zone",
        "Spark Risk", "Electrostatic Charge").

        Args:
            query_embedding: The query embedding vector
            top_k: Number of concepts to check (keep low for precision)
            min_score: HIGH threshold (0.7+) to only match truly relevant queries

        Returns:
            List of SafetyRisk nodes with full details, or empty list if safe
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # ONLY match concepts that have TRIGGERS_RISK relationships
                # This excludes generic concepts like prices, product names, etc.
                result = session.run("""
                    // Step 1: Vector search for concepts matching the query
                    CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
                    YIELD node as concept, score
                    WHERE score > $min_score

                    // Step 2: ONLY consider concepts that DIRECTLY trigger safety risks
                    // This filters out incidental matches like prices or product names
                    MATCH (concept)-[:TRIGGERS_RISK]->(safety_risk:SafetyRisk)

                    // Step 3: Get project context for the safety risk
                    OPTIONAL MATCH (event:Event)-[:REPORTED]->(safety_risk)
                    OPTIONAL MATCH (event)-[:PART_OF]->(project:Project)

                    RETURN DISTINCT
                        concept.name AS triggering_concept,
                        score AS concept_score,
                        safety_risk.name AS risk_name,
                        safety_risk.type AS risk_type,
                        safety_risk.description AS risk_description,
                        safety_risk.hazard_trigger AS hazard_trigger,
                        safety_risk.hazard_environment AS hazard_environment,
                        safety_risk.safe_alternative AS safe_alternative,
                        safety_risk.citation AS citation,
                        project.name AS project
                    ORDER BY score DESC
                """, index_name=VECTOR_INDEX_NAME, top_k=top_k, embedding=query_embedding, min_score=min_score)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_project_story(self, project_name: str) -> dict:
        """Get the full story/decision chain for a project.

        Reconstructs the chronological chain of events with their
        observations and actions.

        Args:
            project_name: Name of the project

        Returns:
            Dict with project info and ordered event chain
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (p:Project {name: $name})

                    // Get all events in order
                    OPTIONAL MATCH (e:Event)-[:PART_OF]->(p)
                    OPTIONAL MATCH (e)-[:SENT_BY]->(person:Person)
                    OPTIONAL MATCH (e)-[:REPORTED]->(obs:Observation)
                    OPTIONAL MATCH (e)-[:PROPOSED]->(act:Action)

                    WITH p, e, person,
                         collect(DISTINCT {type: obs.type, desc: obs.description}) AS observations,
                         collect(DISTINCT {type: act.type, desc: act.description}) AS actions
                    ORDER BY e.step

                    RETURN p.name AS project,
                           p.customer AS customer,
                           collect({
                               step: e.step,
                               date: e.date,
                               summary: e.summary,
                               sender: person.name,
                               observations: observations,
                               actions: actions
                           }) AS event_chain
                """, name=project_name)
                record = result.single()
                return dict(record) if record else None
        return self._execute_with_retry(_query)

    def get_similar_cases(self, query_embedding: list[float], top_k: int = 3) -> list[dict]:
        """Find similar past cases based on concept similarity.

        Args:
            query_embedding: The query embedding vector
            top_k: Number of similar cases to return

        Returns:
            List of similar projects with their key observations and solutions
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    // Find relevant concepts (higher threshold to reduce false matches)
                    CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
                    YIELD node as concept, score
                    WHERE score > 0.8

                    // Find projects mentioning these concepts
                    MATCH (logic_node)-[:RELATES_TO]->(concept)
                    MATCH (event:Event)-[:REPORTED|PROPOSED]->(logic_node)
                    MATCH (event)-[:PART_OF]->(project:Project)

                    // Get symptoms (initial observations)
                    OPTIONAL MATCH (symptom:Observation {type: 'Symptom'})<-[:REPORTED]-(e1:Event)-[:PART_OF]->(project)

                    // Get solutions (workarounds/actions)
                    OPTIONAL MATCH (solution:Action {type: 'Workaround'})<-[:PROPOSED]-(e2:Event)-[:PART_OF]->(project)

                    WITH project, concept, score,
                         collect(DISTINCT symptom.description)[0..2] AS symptoms,
                         collect(DISTINCT solution.description)[0..2] AS solutions

                    RETURN DISTINCT
                        project.name AS project,
                        project.customer AS customer,
                        collect(DISTINCT concept.name) AS matched_concepts,
                        max(score) AS relevance_score,
                        symptoms,
                        solutions
                    ORDER BY relevance_score DESC
                    LIMIT $top_k
                """, index_name=VECTOR_INDEX_NAME, top_k=top_k * 2, embedding=query_embedding)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_project_timeline(self, project_name: str) -> dict:
        """Get the full timeline for a project with logic nodes (for Deep Dive feature).

        Fetches all events in chronological order with their associated
        Observations and Actions, including citations for source verification.

        Args:
            project_name: Name of the project

        Returns:
            Dict with project info and timeline with logic nodes
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (p:Project {name: $name})
                    OPTIONAL MATCH (e:Event)-[:PART_OF]->(p)
                    OPTIONAL MATCH (e)-[:SENT_BY]->(person:Person)
                    OPTIONAL MATCH (e)-[:REPORTED]->(obs:Observation)
                    OPTIONAL MATCH (e)-[:PROPOSED]->(act:Action)

                    WITH p, e, person, obs, act
                    ORDER BY e.step

                    WITH p, e, person,
                         CASE
                             WHEN obs IS NOT NULL THEN {
                                 node_type: 'Observation',
                                 type: obs.type,
                                 description: obs.description,
                                 citation: obs.citation
                             }
                             WHEN act IS NOT NULL THEN {
                                 node_type: 'Action',
                                 type: act.type,
                                 description: act.description,
                                 citation: act.citation
                             }
                             ELSE null
                         END AS logic_node

                    RETURN p.name AS project,
                           p.customer AS customer,
                           collect({
                               step: e.step,
                               date: e.date,
                               time: e.time,
                               summary: e.summary,
                               sender: person.name,
                               sender_email: person.email,
                               logic_node: logic_node
                           }) AS timeline
                """, name=project_name)
                record = result.single()
                if record:
                    data = dict(record)
                    # Filter out null entries and sort by step
                    if data.get("timeline"):
                        data["timeline"] = [
                            t for t in data["timeline"]
                            if t.get("step") is not None
                        ]
                        data["timeline"].sort(key=lambda x: x.get("step", 0))
                    return data
                return None
        return self._execute_with_retry(_query)


    def delete_project(self, project_name: str) -> dict:
        """Delete a project and ALL its related data from the graph.

        This removes:
        - The Project node
        - All Events linked to this project
        - All Persons who sent events in this project (if not linked elsewhere)
        - All Observations reported by events in this project
        - All Actions proposed by events in this project
        - Concepts that were ONLY linked to this project's data (orphaned concepts)

        Args:
            project_name: Name of the project to delete

        Returns:
            Dict with counts of deleted items
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # First, get counts before deletion
                count_result = session.run("""
                    MATCH (p:Project {name: $name})
                    OPTIONAL MATCH (e:Event)-[:PART_OF]->(p)
                    OPTIONAL MATCH (e)-[:REPORTED]->(obs:Observation)
                    OPTIONAL MATCH (e)-[:PROPOSED]->(act:Action)
                    OPTIONAL MATCH (e)-[:SENT_BY]->(person:Person)
                    RETURN
                        count(DISTINCT p) AS projects,
                        count(DISTINCT e) AS events,
                        count(DISTINCT obs) AS observations,
                        count(DISTINCT act) AS actions,
                        count(DISTINCT person) AS persons
                """, name=project_name)
                counts = dict(count_result.single())

                # Delete all related nodes
                # Order matters: delete relationships first, then nodes
                session.run("""
                    MATCH (p:Project {name: $name})
                    OPTIONAL MATCH (e:Event)-[:PART_OF]->(p)
                    OPTIONAL MATCH (e)-[:REPORTED]->(obs:Observation)
                    OPTIONAL MATCH (e)-[:PROPOSED]->(act:Action)

                    // Delete observations and their relationships
                    DETACH DELETE obs

                    // Delete actions and their relationships
                    WITH p, e, act
                    DETACH DELETE act

                    // Delete events
                    WITH p, e
                    DETACH DELETE e

                    // Delete the project
                    WITH p
                    DETACH DELETE p
                """, name=project_name)

                # Clean up orphaned concepts (concepts with no remaining relationships)
                cleanup_result = session.run("""
                    MATCH (c:Concept)
                    WHERE NOT (c)<-[:RELATES_TO]-()
                    WITH c, count(c) AS orphan_count
                    DETACH DELETE c
                    RETURN orphan_count
                """)
                orphan_record = cleanup_result.single()
                orphaned_concepts = orphan_record["orphan_count"] if orphan_record else 0

                # Clean up orphaned persons (persons with no remaining events)
                session.run("""
                    MATCH (person:Person)
                    WHERE NOT (person)<-[:SENT_BY]-()
                    DETACH DELETE person
                """)

                counts["orphaned_concepts_removed"] = orphaned_concepts
                return counts
        return self._execute_with_retry(_query)

    def get_all_threads_summary(self) -> list[dict]:
        """Get summary of all email threads (projects) in the knowledge base.

        Returns list of projects with their event counts, date range, and key info.
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (p:Project)
                    OPTIONAL MATCH (e:Event)-[:PART_OF]->(p)
                    OPTIONAL MATCH (e)-[:SENT_BY]->(person:Person)
                    OPTIONAL MATCH (e)-[:REPORTED]->(obs:Observation)
                    OPTIONAL MATCH (e)-[:PROPOSED]->(act:Action)
                    OPTIONAL MATCH (obs)-[:RELATES_TO]->(c1:Concept)
                    OPTIONAL MATCH (act)-[:RELATES_TO]->(c2:Concept)

                    WITH p,
                         count(DISTINCT e) AS event_count,
                         count(DISTINCT obs) AS observation_count,
                         count(DISTINCT act) AS action_count,
                         collect(DISTINCT person.name) AS participants,
                         collect(DISTINCT e.date) AS dates,
                         collect(DISTINCT c1.name) + collect(DISTINCT c2.name) AS all_concepts

                    RETURN p.name AS name,
                           p.customer AS customer,
                           p.summary AS summary,
                           event_count,
                           observation_count,
                           action_count,
                           participants,
                           [d IN dates WHERE d IS NOT NULL | d] AS dates,
                           [c IN all_concepts WHERE c IS NOT NULL][0..5] AS key_concepts
                    ORDER BY p.name
                """)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def search_by_project_name(self, search_term: str) -> list[dict]:
        """Search for projects matching a name pattern and return their full context.

        This is used to supplement vector search when a project name is mentioned.

        Args:
            search_term: The search query (will be fuzzy matched against project names)

        Returns:
            List of matching project data with events, actions, concepts
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    // Find projects with name containing the search term (case-insensitive)
                    MATCH (p:Project)
                    WHERE toLower(p.name) CONTAINS toLower($search_term)

                    // Get all events for this project
                    OPTIONAL MATCH (e:Event)-[:PART_OF]->(p)
                    OPTIONAL MATCH (e)-[:SENT_BY]->(person:Person)
                    OPTIONAL MATCH (e)-[:REPORTED]->(obs:Observation)
                    OPTIONAL MATCH (e)-[:PROPOSED]->(act:Action)
                    OPTIONAL MATCH (obs)-[:RELATES_TO]->(c1:Concept)
                    OPTIONAL MATCH (act)-[:RELATES_TO]->(c2:Concept)

                    WITH p, e, person, obs, act,
                         collect(DISTINCT c1.name) + collect(DISTINCT c2.name) AS concepts
                    ORDER BY e.step

                    RETURN DISTINCT
                        p.name AS project,
                        'direct_match' AS concept,
                        1.0 AS score,
                        e.summary AS event_summary,
                        e.date AS event_date,
                        person.name AS sender,
                        CASE WHEN obs IS NOT NULL THEN 'Observation'
                             WHEN act IS NOT NULL THEN 'Action'
                             ELSE null END AS logic_type,
                        COALESCE(obs.type, act.type) AS logic_subtype,
                        COALESCE(obs.description, act.description) AS logic_description,
                        COALESCE(obs.citation, act.citation) AS logic_citation,
                        null AS revealed_constraint,
                        null AS addresses_problem,
                        null AS solution_action
                """, search_term=search_term)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    # ========================================
    # Knowledge Source Discovery Methods
    # ========================================

    def create_knowledge_candidate(
        self,
        raw_name: str,
        source_type: str,
        inference_logic: str,
        citation: str,
        event_name: str
    ) -> dict:
        """Create a KnowledgeCandidate node linked to an Event.

        Args:
            raw_name: The raw name/term extracted from the email
            source_type: Type of source (Software, Data, Manual, Process)
            inference_logic: Explanation of WHY this was inferred (forensic reasoning)
            citation: Direct quote from the email
            event_name: Name of the event that suggests this

        Returns:
            Dict with created candidate info
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MERGE (kc:KnowledgeCandidate {raw_name: $raw_name, inference_logic: $inference_logic})
                    ON CREATE SET
                        kc.type = $source_type,
                        kc.citation = $citation,
                        kc.created_at = datetime(),
                        kc.status = 'pending'
                    WITH kc
                    OPTIONAL MATCH (e:Event {name: $event_name})
                    FOREACH (_ IN CASE WHEN e IS NOT NULL THEN [1] ELSE [] END |
                        MERGE (e)-[:SUGGESTS]->(kc)
                    )
                    RETURN kc.raw_name AS raw_name, kc.type AS type,
                           kc.inference_logic AS inference_logic, kc.status AS status,
                           elementId(kc) AS id
                """, raw_name=raw_name, source_type=source_type, inference_logic=inference_logic,
                     citation=citation, event_name=event_name)
                record = result.single()
                return dict(record) if record else None
        return self._execute_with_retry(_query)

    def get_all_knowledge_candidates(self, status: str = None) -> list[dict]:
        """Get all KnowledgeCandidate nodes.

        Args:
            status: Filter by status ('pending', 'verified', 'rejected')

        Returns:
            List of candidate dicts with event and project info
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                where_clause = "WHERE kc.status = $status" if status else ""
                result = session.run(f"""
                    MATCH (kc:KnowledgeCandidate)
                    {where_clause}
                    OPTIONAL MATCH (e:Event)-[:SUGGESTS]->(kc)
                    OPTIONAL MATCH (e)-[:PART_OF]->(p:Project)
                    OPTIONAL MATCH (kc)-[:RESOLVED_TO]->(vs:VerifiedSource)
                    WITH kc, e, p, vs
                    ORDER BY kc.created_at DESC
                    RETURN elementId(kc) AS id,
                           kc.raw_name AS raw_name,
                           kc.type AS type,
                           kc.inference_logic AS inference_logic,
                           kc.citation AS citation,
                           kc.status AS status,
                           kc.created_at AS created_at,
                           collect(DISTINCT p.name) AS projects,
                           collect(DISTINCT e.name) AS events,
                           vs.name AS verified_as
                """, status=status)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def verify_knowledge_candidate(
        self,
        candidate_id: str,
        action: str,
        verified_name: str = None,
        description: str = None,
        existing_source_id: str = None
    ) -> dict:
        """Verify a KnowledgeCandidate.

        Args:
            candidate_id: Element ID of the KnowledgeCandidate
            action: 'reject', 'create_new', or 'map_to_existing'
            verified_name: Name for new VerifiedSource (if create_new)
            description: Description for new source
            existing_source_id: Element ID of existing VerifiedSource (if map_to_existing)

        Returns:
            Result dict with action taken
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                if action == "reject":
                    session.run("""
                        MATCH (kc:KnowledgeCandidate)
                        WHERE elementId(kc) = $candidate_id
                        SET kc.status = 'rejected'
                    """, candidate_id=candidate_id)
                    return {"action": "rejected", "candidate_id": candidate_id}

                elif action == "create_new":
                    result = session.run("""
                        MATCH (kc:KnowledgeCandidate)
                        WHERE elementId(kc) = $candidate_id
                        SET kc.status = 'verified'

                        // Create the VerifiedSource
                        MERGE (vs:VerifiedSource {name: $verified_name})
                        ON CREATE SET
                            vs.type = kc.type,
                            vs.description = $description,
                            vs.created_at = datetime()

                        // Link candidate to verified source
                        MERGE (kc)-[:RESOLVED_TO]->(vs)

                        // Create alias for future matching
                        MERGE (vs)-[:ALIASED_AS {pattern: kc.raw_name}]->(kc)

                        RETURN vs.name AS source_name, elementId(vs) AS source_id
                    """, candidate_id=candidate_id, verified_name=verified_name,
                         description=description or "")
                    record = result.single()
                    return {
                        "action": "created",
                        "candidate_id": candidate_id,
                        "source_name": record["source_name"] if record else None,
                        "source_id": record["source_id"] if record else None
                    }

                elif action == "map_to_existing":
                    result = session.run("""
                        MATCH (kc:KnowledgeCandidate)
                        WHERE elementId(kc) = $candidate_id
                        MATCH (vs:VerifiedSource)
                        WHERE elementId(vs) = $existing_source_id
                        SET kc.status = 'verified'
                        MERGE (kc)-[:RESOLVED_TO]->(vs)
                        MERGE (vs)-[:ALIASED_AS {pattern: kc.raw_name}]->(kc)
                        RETURN vs.name AS source_name
                    """, candidate_id=candidate_id, existing_source_id=existing_source_id)
                    record = result.single()
                    return {
                        "action": "mapped",
                        "candidate_id": candidate_id,
                        "source_name": record["source_name"] if record else None
                    }

                return {"action": "unknown", "error": "Invalid action"}
        return self._execute_with_retry(_query)

    def get_verified_sources_library(self) -> list[dict]:
        """Get all VerifiedSource nodes with usage stats.

        Returns:
            List of verified sources with usage frequency and expert info
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (vs:VerifiedSource)
                    OPTIONAL MATCH (kc:KnowledgeCandidate)-[:RESOLVED_TO]->(vs)
                    OPTIONAL MATCH (e:Event)-[:SUGGESTS]->(kc)
                    OPTIONAL MATCH (e)-[:PART_OF]->(p:Project)
                    OPTIONAL MATCH (e)-[:SENT_BY]->(person:Person)
                    OPTIONAL MATCH (vs)-[alias:ALIASED_AS]->()

                    WITH vs,
                         count(DISTINCT p) AS project_count,
                         count(DISTINCT kc) AS mention_count,
                         collect(DISTINCT p.name) AS projects,
                         collect(DISTINCT person.name) AS experts,
                         collect(DISTINCT alias.pattern) AS aliases

                    RETURN elementId(vs) AS id,
                           vs.name AS name,
                           vs.type AS type,
                           vs.description AS description,
                           project_count,
                           mention_count,
                           projects[0..5] AS recent_projects,
                           experts[0..3] AS top_experts,
                           aliases AS known_aliases
                    ORDER BY mention_count DESC
                """)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_verified_source_details(self, source_id: str) -> dict:
        """Get full details for a VerifiedSource.

        Args:
            source_id: Element ID of the VerifiedSource

        Returns:
            Detailed info about the source
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (vs:VerifiedSource)
                    WHERE elementId(vs) = $source_id
                    OPTIONAL MATCH (kc:KnowledgeCandidate)-[:RESOLVED_TO]->(vs)
                    OPTIONAL MATCH (e:Event)-[:SUGGESTS]->(kc)
                    OPTIONAL MATCH (e)-[:PART_OF]->(p:Project)
                    OPTIONAL MATCH (e)-[:SENT_BY]->(person:Person)

                    WITH vs, kc, e, p, person
                    ORDER BY e.date DESC

                    WITH vs,
                         collect(DISTINCT {
                             project: p.name,
                             event_date: e.date,
                             sender: person.name,
                             citation: kc.citation,
                             context: kc.context
                         }) AS mentions

                    RETURN elementId(vs) AS id,
                           vs.name AS name,
                           vs.type AS type,
                           vs.description AS description,
                           mentions
                """, source_id=source_id)
                record = result.single()
                return dict(record) if record else None
        return self._execute_with_retry(_query)

    def find_alias_matches(self, text: str) -> list[dict]:
        """Find VerifiedSource matches based on ALIASED_AS patterns.

        Used by the retriever for self-learning injection.

        Args:
            text: Text to search for alias patterns

        Returns:
            List of matching verified sources with their alias info
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (vs:VerifiedSource)-[alias:ALIASED_AS]->(kc:KnowledgeCandidate)
                    WHERE toLower($text) CONTAINS toLower(alias.pattern)
                    OPTIONAL MATCH (e:Event)-[:SUGGESTS]->(kc)
                    OPTIONAL MATCH (e)-[:SENT_BY]->(person:Person)
                    RETURN vs.name AS verified_name,
                           vs.type AS source_type,
                           vs.description AS description,
                           alias.pattern AS matched_pattern,
                           person.name AS verified_by
                    LIMIT 5
                """, text=text)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def delete_knowledge_candidate(self, candidate_id: str) -> bool:
        """Delete a KnowledgeCandidate node.

        Args:
            candidate_id: Element ID of the candidate to delete

        Returns:
            True if deleted successfully
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                session.run("""
                    MATCH (kc:KnowledgeCandidate)
                    WHERE elementId(kc) = $candidate_id
                    DETACH DELETE kc
                """, candidate_id=candidate_id)
                return True
        return self._execute_with_retry(_query)

    def get_expert_knowledge_map(self) -> list[dict]:
        """Get SME connectivity - which experts are linked to which verified sources.

        Returns:
            List of experts with their associated tools/sources and usage count
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (p:Person)<-[:SENT_BY]-(e:Event)-[:SUGGESTS]->(kc:KnowledgeCandidate)-[:RESOLVED_TO]->(vs:VerifiedSource)
                    WITH p, vs, count(DISTINCT e) AS usage_count
                    ORDER BY usage_count DESC
                    WITH p, collect({source: vs.name, type: vs.type, usage_count: usage_count}) AS sources
                    RETURN p.name AS expert_name,
                           p.email AS expert_email,
                           size(sources) AS source_count,
                           sources[0..5] AS top_sources
                    ORDER BY source_count DESC
                    LIMIT 20
                """)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_knowledge_stats(self) -> dict:
        """Get overall knowledge discovery statistics.

        Returns:
            Dict with stats about candidates, sources, and coverage
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (kc:KnowledgeCandidate)
                    WITH count(CASE WHEN kc.status = 'pending' THEN 1 END) AS pending,
                         count(CASE WHEN kc.status = 'verified' THEN 1 END) AS verified,
                         count(CASE WHEN kc.status = 'rejected' THEN 1 END) AS rejected,
                         count(kc) AS total_candidates
                    OPTIONAL MATCH (vs:VerifiedSource)
                    WITH pending, verified, rejected, total_candidates, count(vs) AS total_sources
                    OPTIONAL MATCH (p:Project)
                    WITH pending, verified, rejected, total_candidates, total_sources, count(p) AS total_projects
                    RETURN pending, verified, rejected, total_candidates, total_sources, total_projects
                """)
                record = result.single()
                return dict(record) if record else {
                    "pending": 0, "verified": 0, "rejected": 0,
                    "total_candidates": 0, "total_sources": 0, "total_projects": 0
                }
        return self._execute_with_retry(_query)

    # ========================================
    # Configuration Graph Query Methods
    # ========================================

    def get_cartridges_for_housing(self, housing_id: str) -> list[dict]:
        """Get all filter cartridges compatible with a housing.

        Args:
            housing_id: The ProductVariant ID (housing name)

        Returns:
            List of compatible FilterCartridge nodes with details
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pv:ProductVariant {name: $housing_id})-[:ACCEPTS_CARTRIDGE]->(fc:FilterCartridge)
                    RETURN fc.name AS id,
                           fc.model_name AS model_name,
                           fc.weight_kg AS weight_kg,
                           fc.carbon_weight_kg AS carbon_weight_kg,
                           fc.diameter_mm AS diameter_mm,
                           fc.length_mm AS length_mm,
                           fc.pellet_size_mm AS pellet_size_mm,
                           fc.media_type AS media_type
                """, housing_id=housing_id)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_duct_connections_for_variant(self, variant_id: str) -> list[dict]:
        """Get duct connection options for a product variant.

        Args:
            variant_id: The ProductVariant ID

        Returns:
            List of DuctConnection nodes with valid diameters
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pv:ProductVariant {name: $variant_id})-[:COMPATIBLE_WITH_DUCT]->(dc:DuctConnection)
                    RETURN dc.name AS id,
                           dc.housing_size AS housing_size,
                           dc.valid_duct_diameters_mm AS valid_duct_diameters_mm,
                           dc.transition_type AS transition_type
                """, variant_id=variant_id)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_variant_options(self, variant_id: str) -> dict:
        """Get configuration options for a product variant.

        Args:
            variant_id: The ProductVariant ID

        Returns:
            Dict with available_options array and options_json
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pv:ProductVariant {name: $variant_id})
                    RETURN pv.available_options AS available_options,
                           pv.options_json AS options_json
                """, variant_id=variant_id)
                record = result.single()
                return dict(record) if record else {"available_options": [], "options_json": None}
        return self._execute_with_retry(_query)

    def find_housings_by_duct_diameter(self, duct_diameter_mm: int) -> list[dict]:
        """Find all product variants compatible with a specific duct diameter.

        Args:
            duct_diameter_mm: The required duct diameter in mm

        Returns:
            List of ProductVariant nodes that support this diameter
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pv:ProductVariant)-[:COMPATIBLE_WITH_DUCT]->(dc:DuctConnection)
                    WHERE $diameter IN dc.valid_duct_diameters_mm
                    RETURN DISTINCT pv.name AS id,
                           pv.family AS family,
                           pv.width_mm AS width_mm,
                           pv.height_mm AS height_mm,
                           dc.valid_duct_diameters_mm AS all_valid_diameters
                """, diameter=duct_diameter_mm)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def find_housings_by_cartridge(self, cartridge_model: str) -> list[dict]:
        """Find all housings that accept a specific cartridge model.

        Args:
            cartridge_model: The cartridge model name (e.g., 'ECO-C 2600')

        Returns:
            List of ProductVariant nodes that accept this cartridge
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pv:ProductVariant)-[:ACCEPTS_CARTRIDGE]->(fc:FilterCartridge)
                    WHERE toLower(fc.model_name) CONTAINS toLower($model)
                       OR toLower(fc.name) CONTAINS toLower($model)
                    RETURN DISTINCT pv.name AS id,
                           pv.family AS family,
                           pv.width_mm AS width_mm,
                           pv.height_mm AS height_mm,
                           fc.model_name AS cartridge_model,
                           fc.weight_kg AS cartridge_weight_kg
                """, model=cartridge_model)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_full_variant_details(self, variant_id: str) -> dict:
        """Get complete details for a product variant including all relationships.

        Args:
            variant_id: The ProductVariant ID

        Returns:
            Dict with variant properties, cartridges, duct connections, filters, materials, and options
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pv:ProductVariant {name: $variant_id})
                    OPTIONAL MATCH (pv)-[:ACCEPTS_CARTRIDGE]->(fc:FilterCartridge)
                    OPTIONAL MATCH (pv)-[:ACCEPTS_FILTER]->(fcons:FilterConsumable)
                    OPTIONAL MATCH (pv)-[:COMPATIBLE_WITH_DUCT]->(dc:DuctConnection)
                    OPTIONAL MATCH (pv)-[:IS_CATEGORY]->(cat:Category)
                    WITH pv,
                         collect(DISTINCT {
                             id: fc.name,
                             model_name: fc.model_name,
                             weight_kg: fc.weight_kg,
                             media_type: fc.media_type
                         }) AS cartridges,
                         collect(DISTINCT {
                             id: fcons.name,
                             part_number: fcons.part_number,
                             model_name: fcons.model_name,
                             filter_type: fcons.filter_type,
                             weight_kg: fcons.weight_kg
                         }) AS consumable_filters,
                         collect(DISTINCT {
                             housing_size: dc.housing_size,
                             valid_diameters: dc.valid_duct_diameters_mm
                         }) AS duct_connections,
                         collect(DISTINCT {type: cat.type, value: cat.name}) AS categories
                    RETURN pv.name AS id,
                           pv.family AS family,
                           pv.width_mm AS width_mm,
                           pv.height_mm AS height_mm,
                           pv.depth_mm AS depth_mm,
                           pv.airflow_m3h AS airflow_m3h,
                           pv.weight_kg AS weight_kg,
                           pv.price AS price,
                           pv.available_options AS available_options,
                           pv.available_materials AS available_materials,
                           pv.compatible_duct_diameters_mm AS compatible_duct_diameters_mm,
                           cartridges,
                           consumable_filters,
                           duct_connections,
                           categories
                """, variant_id=variant_id)
                record = result.single()
                if record:
                    data = dict(record)
                    # Filter out empty entries from collections
                    data["cartridges"] = [c for c in data.get("cartridges", []) if c.get("id")]
                    data["consumable_filters"] = [f for f in data.get("consumable_filters", []) if f.get("id")]
                    data["duct_connections"] = [d for d in data.get("duct_connections", []) if d.get("housing_size")]
                    data["categories"] = [c for c in data.get("categories", []) if c.get("type")]
                    return data
                return None
        return self._execute_with_retry(_query)

    def get_filters_for_housing(self, housing_id: str) -> list[dict]:
        """Get all consumable filters compatible with a housing.

        Args:
            housing_id: The ProductVariant ID (housing name)

        Returns:
            List of compatible FilterConsumable nodes with details
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pv:ProductVariant {name: $housing_id})-[:ACCEPTS_FILTER]->(f:FilterConsumable)
                    RETURN f.name AS id,
                           f.part_number AS part_number,
                           f.model_name AS model_name,
                           f.filter_type AS filter_type,
                           f.weight_kg AS weight_kg,
                           f.dimensions AS dimensions,
                           f.efficiency_class AS efficiency_class,
                           f.media_type AS media_type
                """, housing_id=housing_id)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def find_variants_by_material(self, material_code: str) -> list[dict]:
        """Find all product variants available in a specific material.

        Args:
            material_code: The material code (e.g., 'FZ', 'ZM', 'RF')

        Returns:
            List of ProductVariant nodes that support this material
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pv:ProductVariant)
                    WHERE $material IN pv.available_materials
                    RETURN pv.name AS id,
                           pv.family AS family,
                           pv.width_mm AS width_mm,
                           pv.height_mm AS height_mm,
                           pv.available_materials AS available_materials
                """, material=material_code)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def find_variants_by_corrosion_class(self, corrosion_class: str) -> list[dict]:
        """Find all product variants suitable for a corrosion class.

        Args:
            corrosion_class: The corrosion class (e.g., 'C3', 'C4', 'C5')

        Returns:
            List of ProductVariant nodes with materials meeting the corrosion class
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # First get materials that meet the corrosion class
                result = session.run("""
                    MATCH (ms:MaterialSpecification)
                    WHERE ms.corrosion_class >= $class
                    WITH collect(ms.code) AS suitable_materials
                    MATCH (pv:ProductVariant)
                    WHERE any(m IN pv.available_materials WHERE m IN suitable_materials)
                    RETURN pv.name AS id,
                           pv.family AS family,
                           pv.width_mm AS width_mm,
                           pv.height_mm AS height_mm,
                           pv.available_materials AS available_materials,
                           [m IN pv.available_materials WHERE m IN suitable_materials] AS suitable_materials
                """, **{"class": corrosion_class})
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_material_specifications(self) -> list[dict]:
        """Get all material specifications with corrosion class mappings.

        Returns:
            List of MaterialSpecification nodes
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (ms:MaterialSpecification)
                    RETURN ms.code AS code,
                           ms.full_name AS full_name,
                           ms.corrosion_class AS corrosion_class,
                           ms.description AS description
                    ORDER BY ms.corrosion_class, ms.code
                """)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def find_filter_by_part_number(self, part_number: str) -> dict:
        """Find a filter consumable by its part number.

        Args:
            part_number: The part number/SKU (e.g., '61090M2359')

        Returns:
            FilterConsumable details or None
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (f:FilterConsumable)
                    WHERE f.part_number = $part_number OR f.name CONTAINS $part_number
                    OPTIONAL MATCH (pv:ProductVariant)-[:ACCEPTS_FILTER]->(f)
                    RETURN f.name AS id,
                           f.part_number AS part_number,
                           f.model_name AS model_name,
                           f.filter_type AS filter_type,
                           f.weight_kg AS weight_kg,
                           f.dimensions AS dimensions,
                           f.efficiency_class AS efficiency_class,
                           collect(DISTINCT pv.name) AS compatible_housings
                """, part_number=part_number)
                record = result.single()
                return dict(record) if record else None
        return self._execute_with_retry(_query)

    def find_variants_by_duct_diameter(self, duct_diameter_mm: int) -> list[dict]:
        """Find all product variants compatible with a specific duct diameter.

        Uses the compatible_duct_diameters_mm property directly on ProductVariant.

        Args:
            duct_diameter_mm: The required duct diameter in mm

        Returns:
            List of ProductVariant nodes that support this diameter
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pv:ProductVariant)
                    WHERE $diameter IN pv.compatible_duct_diameters_mm
                    RETURN pv.name AS id,
                           pv.family AS family,
                           pv.width_mm AS width_mm,
                           pv.height_mm AS height_mm,
                           pv.compatible_duct_diameters_mm AS all_valid_diameters
                """, diameter=duct_diameter_mm)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    # ========================================
    # Configuration Graph Search Methods
    # ========================================

    def search_product_variants(self, search_term: str) -> list[dict]:
        """Search ProductVariant nodes by name, family, or ID.

        Args:
            search_term: The search query (matches name, family)

        Returns:
            List of matching ProductVariant nodes with full details
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pv:ProductVariant)
                    WHERE toLower(pv.name) CONTAINS toLower($term)
                       OR toLower(pv.family) CONTAINS toLower($term)
                    OPTIONAL MATCH (pv)-[:ACCEPTS_CARTRIDGE]->(fc:FilterCartridge)
                    OPTIONAL MATCH (pv)-[:ACCEPTS_FILTER]->(fcons:FilterConsumable)
                    OPTIONAL MATCH (pv)-[:IS_CATEGORY]->(cat:Category)
                    RETURN pv.name AS id,
                           pv.family AS family,
                           pv.width_mm AS width_mm,
                           pv.height_mm AS height_mm,
                           pv.depth_mm AS depth_mm,
                           pv.airflow_m3h AS airflow_m3h,
                           pv.weight_kg AS weight_kg,
                           pv.price AS price,
                           pv.available_options AS available_options,
                           pv.options_json AS options_json,
                           pv.available_materials AS available_materials,
                           pv.compatible_duct_diameters_mm AS compatible_duct_diameters_mm,
                           pv.cartridge_count AS cartridge_count,
                           pv.is_insulated AS is_insulated,
                           pv.special_features AS special_features,
                           pv.length_min_mm AS length_min_mm,
                           pv.length_max_mm AS length_max_mm,
                           pv.reference_airflow_m3h AS reference_airflow_m3h,
                           pv.standard_length_mm AS standard_length_mm,
                           pv.available_depths_mm AS available_depths_mm,
                           collect(DISTINCT fc.model_name) AS compatible_cartridges,
                           collect(DISTINCT fcons.part_number) AS compatible_filters,
                           collect(DISTINCT {type: cat.type, value: cat.name}) AS categories
                    LIMIT 10
                """, term=search_term)
                results = []
                for record in result:
                    data = dict(record)
                    # Filter out null entries from categories
                    data["categories"] = [c for c in data.get("categories", []) if c.get("type")]
                    results.append(data)
                return results
        return self._execute_with_retry(_query)

    def search_variant_options(self, search_term: str) -> list[dict]:
        """Search ProductVariant nodes that have options matching the search term.

        Searches inside options_json for matching descriptions or codes.

        Args:
            search_term: The search query (matches option description or code)

        Returns:
            List of ProductVariant nodes with matching options highlighted
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # Search variants that have the search term in their options_json
                result = session.run("""
                    MATCH (pv:ProductVariant)
                    WHERE pv.options_json IS NOT NULL
                      AND toLower(pv.options_json) CONTAINS toLower($term)
                    RETURN pv.name AS id,
                           pv.family AS family,
                           pv.options_json AS options_json,
                           pv.available_options AS available_options
                    LIMIT 20
                """, term=search_term)
                return [dict(record) for record in result]
        return self._execute_with_retry(_query)

    def get_variant_by_name(self, variant_name: str) -> dict:
        """Get a specific ProductVariant by exact name.

        Args:
            variant_name: The exact variant name/ID

        Returns:
            Full ProductVariant details or None
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pv:ProductVariant {name: $name})
                    OPTIONAL MATCH (pv)-[:ACCEPTS_CARTRIDGE]->(fc:FilterCartridge)
                    OPTIONAL MATCH (pv)-[:ACCEPTS_FILTER]->(fcons:FilterConsumable)
                    OPTIONAL MATCH (pv)-[:COMPATIBLE_WITH_DUCT]->(dc:DuctConnection)
                    OPTIONAL MATCH (pv)-[:IS_CATEGORY]->(cat:Category)
                    RETURN pv.name AS id,
                           pv.family AS family,
                           pv.width_mm AS width_mm,
                           pv.height_mm AS height_mm,
                           pv.depth_mm AS depth_mm,
                           pv.airflow_m3h AS airflow_m3h,
                           pv.weight_kg AS weight_kg,
                           pv.price AS price,
                           pv.available_options AS available_options,
                           pv.options_json AS options_json,
                           pv.available_materials AS available_materials,
                           pv.compatible_duct_diameters_mm AS compatible_duct_diameters_mm,
                           collect(DISTINCT {
                               model_name: fc.model_name,
                               weight_kg: fc.weight_kg,
                               media_type: fc.media_type
                           }) AS cartridges,
                           collect(DISTINCT {
                               part_number: fcons.part_number,
                               filter_type: fcons.filter_type,
                               efficiency_class: fcons.efficiency_class
                           }) AS filters,
                           collect(DISTINCT dc.valid_duct_diameters_mm) AS duct_diameters,
                           collect(DISTINCT {type: cat.type, value: cat.name}) AS categories
                """, name=variant_name)
                record = result.single()
                if record:
                    data = dict(record)
                    # Filter out empty entries
                    data["cartridges"] = [c for c in data.get("cartridges", []) if c.get("model_name")]
                    data["filters"] = [f for f in data.get("filters", []) if f.get("part_number")]
                    data["categories"] = [c for c in data.get("categories", []) if c.get("type")]
                    return data
                return None
        return self._execute_with_retry(_query)

    def configuration_graph_search(self, query: str) -> dict:
        """Comprehensive search across Configuration Graph entities.

        Searches ProductVariants, FilterCartridges, FilterConsumables, MaterialSpecifications, and options.

        Args:
            query: The search query

        Returns:
            Dict with matching variants, cartridges, filters, materials, and options
        """
        def _query():
            driver = self.connect()
            results = {
                "variants": [],
                "cartridges": [],
                "filters": [],
                "materials": [],
                "option_matches": []
            }

            with driver.session(database=self.database) as session:
                # Search ProductVariants by name/family
                pv_result = session.run("""
                    MATCH (pv:ProductVariant)
                    WHERE toLower(pv.name) CONTAINS toLower($term)
                       OR toLower(pv.family) CONTAINS toLower($term)
                    RETURN pv.name AS id,
                           pv.family AS family,
                           pv.width_mm AS width_mm,
                           pv.height_mm AS height_mm,
                           pv.available_options AS available_options,
                           pv.options_json AS options_json,
                           pv.available_materials AS available_materials,
                           pv.cartridge_count AS cartridge_count,
                           pv.is_insulated AS is_insulated,
                           pv.special_features AS special_features,
                           pv.length_min_mm AS length_min_mm,
                           pv.length_max_mm AS length_max_mm,
                           pv.reference_airflow_m3h AS reference_airflow_m3h,
                           pv.standard_length_mm AS standard_length_mm,
                           pv.available_depths_mm AS available_depths_mm
                    LIMIT 5
                """, term=query)
                results["variants"] = [dict(r) for r in pv_result]

                # Search FilterCartridges
                fc_result = session.run("""
                    MATCH (fc:FilterCartridge)
                    WHERE toLower(fc.model_name) CONTAINS toLower($term)
                       OR toLower(fc.name) CONTAINS toLower($term)
                    RETURN fc.name AS id,
                           fc.model_name AS model_name,
                           fc.weight_kg AS weight_kg,
                           fc.media_type AS media_type
                    LIMIT 5
                """, term=query)
                results["cartridges"] = [dict(r) for r in fc_result]

                # Search FilterConsumables by part number or model
                fcons_result = session.run("""
                    MATCH (f:FilterConsumable)
                    WHERE toLower(f.part_number) CONTAINS toLower($term)
                       OR toLower(f.model_name) CONTAINS toLower($term)
                       OR toLower(f.filter_type) CONTAINS toLower($term)
                    RETURN f.name AS id,
                           f.part_number AS part_number,
                           f.model_name AS model_name,
                           f.filter_type AS filter_type,
                           f.weight_kg AS weight_kg
                    LIMIT 5
                """, term=query)
                results["filters"] = [dict(r) for r in fcons_result]

                # Search MaterialSpecifications by code, name, or corrosion class
                mat_result = session.run("""
                    MATCH (m:MaterialSpecification)
                    WHERE toLower(m.code) CONTAINS toLower($term)
                       OR toLower(m.full_name) CONTAINS toLower($term)
                       OR toLower(m.name) CONTAINS toLower($term)
                       OR toLower(m.description) CONTAINS toLower($term)
                    RETURN m.code AS code,
                           m.full_name AS full_name,
                           m.corrosion_class AS corrosion_class,
                           m.description AS description
                    LIMIT 5
                """, term=query)
                results["materials"] = [dict(r) for r in mat_result]

                # Search for options containing the term
                opt_result = session.run("""
                    MATCH (pv:ProductVariant)
                    WHERE pv.options_json IS NOT NULL
                      AND toLower(pv.options_json) CONTAINS toLower($term)
                    RETURN pv.name AS variant_id,
                           pv.family AS family,
                           pv.options_json AS options_json
                    LIMIT 10
                """, term=query)
                results["option_matches"] = [dict(r) for r in opt_result]

            return results
        return self._execute_with_retry(_query)

    # =========================================================================
    # ACTIVE LEARNING - Learned Rules from Human Feedback
    # =========================================================================

    LEARNED_RULES_INDEX = "learned_rules_keywords"

    def ensure_learned_rules_index(self) -> bool:
        """Ensure the vector index for learned rules exists.

        Creates a vector index on Keyword.embedding if it doesn't exist.
        Returns True if index exists or was created, False on error.
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # Check if index exists
                result = session.run("""
                    SHOW INDEXES
                    WHERE name = $index_name
                    RETURN count(*) AS count
                """, index_name=self.LEARNED_RULES_INDEX)

                count = result.single()["count"]
                if count > 0:
                    return True  # Index already exists

                # Create the vector index
                session.run(f"""
                    CREATE VECTOR INDEX {self.LEARNED_RULES_INDEX} IF NOT EXISTS
                    FOR (k:Keyword)
                    ON (k.embedding)
                    OPTIONS {{
                        indexConfig: {{
                            `vector.dimensions`: {VECTOR_DIMENSIONS},
                            `vector.similarity_function`: 'cosine'
                        }}
                    }}
                """)
                return True

        try:
            return self._execute_with_retry(_query)
        except Exception as e:
            print(f"Warning: Could not create learned rules index: {e}")
            return False

    def save_learned_rule(self, trigger_text: str, rule_text: str,
                          embedding: list[float], context: str = None,
                          confirmed_by: str = "expert") -> dict:
        """Save a learned rule from confirmed inference.

        Creates or updates:
        - Keyword node with the trigger text and its embedding
        - Requirement node with the rule text
        - IMPLIES relationship between them

        Args:
            trigger_text: The context trigger (e.g., "Swimming Pool", "Basen")
            rule_text: The engineering rule (e.g., "Requires C5 corrosion class")
            embedding: Vector embedding of the trigger_text
            context: Optional additional context
            confirmed_by: Who confirmed this rule

        Returns:
            Dict with created/updated node IDs and status
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    // Create or update Keyword node
                    MERGE (k:Keyword {name: $trigger})
                    ON CREATE SET
                        k.embedding = $embedding,
                        k.created_at = datetime(),
                        k.confirmed_by = $confirmed_by
                    ON MATCH SET
                        k.embedding = $embedding,
                        k.updated_at = datetime()

                    // Create or update Requirement node
                    MERGE (r:Requirement {text: $rule})
                    ON CREATE SET
                        r.created_at = datetime(),
                        r.context = $context

                    // Create IMPLIES relationship
                    MERGE (k)-[rel:IMPLIES]->(r)
                    ON CREATE SET
                        rel.confidence = 1.0,
                        rel.created_at = datetime(),
                        rel.source = 'human_feedback'
                    ON MATCH SET
                        rel.confidence = rel.confidence + 0.1,
                        rel.updated_at = datetime()

                    RETURN
                        elementId(k) AS keyword_id,
                        elementId(r) AS requirement_id,
                        k.name AS keyword,
                        r.text AS requirement,
                        rel.confidence AS confidence
                """,
                trigger=trigger_text,
                rule=rule_text,
                embedding=embedding,
                context=context,
                confirmed_by=confirmed_by)

                record = result.single()
                return {
                    "status": "success",
                    "keyword_id": record["keyword_id"],
                    "requirement_id": record["requirement_id"],
                    "keyword": record["keyword"],
                    "requirement": record["requirement"],
                    "confidence": record["confidence"]
                }

        return self._execute_with_retry(_query)

    def get_semantic_rules(self, query_embedding: list[float],
                           top_k: int = 5, min_score: float = 0.75) -> list[dict]:
        """Retrieve learned rules using vector similarity search.

        Finds Keyword nodes semantically similar to the query and returns
        their associated Requirements.

        Args:
            query_embedding: Vector embedding of the user query
            top_k: Maximum number of rules to return
            min_score: Minimum similarity score (0.0-1.0)

        Returns:
            List of dicts with keyword, rule, and similarity score
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # First check if the index exists
                index_check = session.run("""
                    SHOW INDEXES WHERE name = $index_name
                    RETURN count(*) AS count
                """, index_name=self.LEARNED_RULES_INDEX)

                if index_check.single()["count"] == 0:
                    return []  # No index, no rules

                # Vector search for similar keywords
                result = session.run("""
                    CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
                    YIELD node AS keyword, score
                    WHERE score >= $min_score

                    // Get the associated requirements
                    MATCH (keyword)-[rel:IMPLIES]->(req:Requirement)

                    RETURN
                        keyword.name AS trigger,
                        req.text AS rule,
                        score AS similarity,
                        rel.confidence AS confidence,
                        req.context AS context
                    ORDER BY score DESC, rel.confidence DESC
                """,
                index_name=self.LEARNED_RULES_INDEX,
                top_k=top_k,
                embedding=query_embedding,
                min_score=min_score)

                return [dict(record) for record in result]

        try:
            return self._execute_with_retry(_query)
        except Exception as e:
            # If vector search fails (e.g., no index), return empty
            print(f"Warning: Semantic rules search failed: {e}")
            return []

    def get_rules_by_keyword(self, keyword: str) -> list[dict]:
        """Fallback: Get rules by exact or partial keyword match.

        Used when vector search is not available or as a complement.
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (k:Keyword)-[rel:IMPLIES]->(r:Requirement)
                    WHERE toLower(k.name) CONTAINS toLower($keyword)
                    RETURN
                        k.name AS trigger,
                        r.text AS rule,
                        1.0 AS similarity,
                        rel.confidence AS confidence,
                        r.context AS context
                    ORDER BY rel.confidence DESC
                    LIMIT 10
                """, keyword=keyword)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def get_all_learned_rules(self) -> list[dict]:
        """Get all learned rules (for admin/debugging)."""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (k:Keyword)-[rel:IMPLIES]->(r:Requirement)
                    RETURN
                        k.name AS trigger,
                        r.text AS rule,
                        rel.confidence AS confidence,
                        rel.created_at AS created_at,
                        r.context AS context
                    ORDER BY rel.created_at DESC
                """)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def delete_learned_rule(self, trigger: str, rule: str) -> bool:
        """Delete a specific learned rule."""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (k:Keyword {name: $trigger})-[rel:IMPLIES]->(r:Requirement {text: $rule})
                    DELETE rel

                    // Clean up orphan nodes
                    WITH k, r
                    OPTIONAL MATCH (k)-[k_rel:IMPLIES]->()
                    OPTIONAL MATCH ()-[r_rel:IMPLIES]->(r)
                    WITH k, r, count(k_rel) AS k_rels, count(r_rel) AS r_rels

                    // Delete keyword if no more relationships
                    FOREACH (_ IN CASE WHEN k_rels = 0 THEN [1] ELSE [] END |
                        DELETE k
                    )

                    // Delete requirement if no more relationships
                    FOREACH (_ IN CASE WHEN r_rels = 0 THEN [1] ELSE [] END |
                        DELETE r
                    )

                    RETURN true AS deleted
                """, trigger=trigger, rule=rule)
                return result.single() is not None

        return self._execute_with_retry(_query)


db = Neo4jConnection()
