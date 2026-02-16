import os
import time
from typing import Optional
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv(dotenv_path="../.env")

# Simple TTL cache for expensive queries
_query_cache = {}
_cache_ttl = 300  # 5 minutes


def _get_cached(key: str):
    """Get value from cache if not expired."""
    if key in _query_cache:
        value, timestamp = _query_cache[key]
        if time.time() - timestamp < _cache_ttl:
            return value
        del _query_cache[key]
    return None


def _set_cached(key: str, value):
    """Store value in cache."""
    _query_cache[key] = (value, time.time())

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
                max_connection_lifetime=3600,  # 1 hour (was 5 min)
                max_connection_pool_size=50,   # More connections for parallel queries
                connection_acquisition_timeout=30,
                keep_alive=True,
            )
        return self.driver

    def warmup(self):
        """Pre-connect and warm up connection pool. Call on server start."""
        import time
        t = time.time()
        driver = self.connect()
        try:
            with driver.session(database=self.database) as session:
                # Simple query to establish SSL connection and warm pool
                session.run("RETURN 1").single()
            elapsed = time.time() - t
            print(f"✓ Neo4j connection warmed up in {elapsed:.2f}s")

            # Pre-load cached data
            self.get_all_applications()
            print("✓ Applications cache loaded")
        except Exception as e:
            print(f"⚠ Neo4j warmup failed: {e}")

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
        Uses fulltext index for fast case-insensitive substring matching.

        Args:
            search_term: The search query (will be fuzzy matched against project names)

        Returns:
            List of matching project data with events, actions, concepts
        """
        def _query():
            driver = self.connect()
            # Escape special Lucene characters and prepare wildcard search
            safe_term = search_term.replace("~", "\\~").replace("*", "\\*").replace("?", "\\?")
            wildcard_term = f"*{safe_term}*"

            with driver.session(database=self.database) as session:
                try:
                    # Use fulltext index for fast search (was 4.28s, now ~100ms)
                    result = session.run("""
                        // Find projects using fulltext index
                        CALL db.index.fulltext.queryNodes("project_fulltext", $search_term)
                        YIELD node AS p, score

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
                    """, search_term=wildcard_term)
                    return [dict(record) for record in result]
                except Exception:
                    # Fallback to old query if fulltext index doesn't exist
                    result = session.run("""
                        MATCH (p:Project)
                        WHERE toLower(p.name) CONTAINS toLower($search_term)
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
                            p.name AS project, 'direct_match' AS concept, 1.0 AS score,
                            e.summary AS event_summary, e.date AS event_date, person.name AS sender,
                            CASE WHEN obs IS NOT NULL THEN 'Observation'
                                 WHEN act IS NOT NULL THEN 'Action'
                                 ELSE null END AS logic_type,
                            COALESCE(obs.type, act.type) AS logic_subtype,
                            COALESCE(obs.description, act.description) AS logic_description,
                            COALESCE(obs.citation, act.citation) AS logic_citation,
                            null AS revealed_constraint, null AS addresses_problem,
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

        Uses fulltext index for fast case-insensitive substring matching.

        Args:
            search_term: The search query (matches name, family)

        Returns:
            List of matching ProductVariant nodes with full details
        """
        def _query():
            driver = self.connect()
            # Escape special Lucene characters and prepare wildcard search
            safe_term = search_term.replace("~", "\\~").replace("*", "\\*").replace("?", "\\?")
            wildcard_term = f"*{safe_term}*"

            with driver.session(database=self.database) as session:
                try:
                    # Use fulltext index for fast search
                    result = session.run("""
                        CALL db.index.fulltext.queryNodes("product_variant_fulltext", $term)
                        YIELD node AS pv, score
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
                        ORDER BY score DESC
                        LIMIT 10
                    """, term=wildcard_term)
                except Exception:
                    # Fallback to old query if fulltext index doesn't exist
                    result = session.run("""
                        MATCH (pv:ProductVariant)
                        WHERE toLower(pv.name) CONTAINS toLower($term)
                           OR toLower(pv.family) CONTAINS toLower($term)
                        OPTIONAL MATCH (pv)-[:ACCEPTS_CARTRIDGE]->(fc:FilterCartridge)
                        OPTIONAL MATCH (pv)-[:ACCEPTS_FILTER]->(fcons:FilterConsumable)
                        OPTIONAL MATCH (pv)-[:IS_CATEGORY]->(cat:Category)
                        RETURN pv.name AS id, pv.family AS family,
                               pv.width_mm AS width_mm, pv.height_mm AS height_mm,
                               pv.depth_mm AS depth_mm, pv.airflow_m3h AS airflow_m3h,
                               pv.weight_kg AS weight_kg, pv.price AS price,
                               pv.available_options AS available_options,
                               pv.options_json AS options_json,
                               pv.available_materials AS available_materials,
                               pv.compatible_duct_diameters_mm AS compatible_duct_diameters_mm,
                               pv.cartridge_count AS cartridge_count,
                               pv.is_insulated AS is_insulated,
                               pv.special_features AS special_features,
                               pv.length_min_mm AS length_min_mm, pv.length_max_mm AS length_max_mm,
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
        Uses fulltext indexes for fast case-insensitive substring matching.

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

            # Escape special Lucene characters and prepare fuzzy search term
            search_term = query.replace("~", "\\~").replace("*", "\\*").replace("?", "\\?")
            # Use wildcards for substring matching
            wildcard_term = f"*{search_term}*"

            with driver.session(database=self.database) as session:
                # Search ProductVariants using fulltext index (was 1.5s per query, now ~50ms)
                try:
                    pv_result = session.run("""
                        CALL db.index.fulltext.queryNodes("product_variant_fulltext", $term)
                        YIELD node AS pv, score
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
                               pv.available_depths_mm AS available_depths_mm,
                               score
                        ORDER BY score DESC
                        LIMIT 5
                    """, term=wildcard_term)
                    results["variants"] = [dict(r) for r in pv_result]
                except Exception:
                    # Fallback to old query if fulltext index doesn't exist
                    pv_result = session.run("""
                        MATCH (pv:ProductVariant)
                        WHERE toLower(pv.name) CONTAINS toLower($term)
                           OR toLower(pv.family) CONTAINS toLower($term)
                        RETURN pv.name AS id, pv.family AS family,
                               pv.width_mm AS width_mm, pv.height_mm AS height_mm,
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

                # Search FilterCartridges using fulltext index
                try:
                    fc_result = session.run("""
                        CALL db.index.fulltext.queryNodes("filter_cartridge_fulltext", $term)
                        YIELD node AS fc, score
                        RETURN fc.name AS id,
                               fc.model_name AS model_name,
                               fc.weight_kg AS weight_kg,
                               fc.media_type AS media_type,
                               score
                        ORDER BY score DESC
                        LIMIT 5
                    """, term=wildcard_term)
                    results["cartridges"] = [dict(r) for r in fc_result]
                except Exception:
                    fc_result = session.run("""
                        MATCH (fc:FilterCartridge)
                        WHERE toLower(fc.model_name) CONTAINS toLower($term)
                           OR toLower(fc.name) CONTAINS toLower($term)
                        RETURN fc.name AS id, fc.model_name AS model_name,
                               fc.weight_kg AS weight_kg, fc.media_type AS media_type
                        LIMIT 5
                    """, term=query)
                    results["cartridges"] = [dict(r) for r in fc_result]

                # Search FilterConsumables using fulltext index
                try:
                    fcons_result = session.run("""
                        CALL db.index.fulltext.queryNodes("filter_consumable_fulltext", $term)
                        YIELD node AS f, score
                        RETURN f.name AS id,
                               f.part_number AS part_number,
                               f.model_name AS model_name,
                               f.filter_type AS filter_type,
                               f.weight_kg AS weight_kg,
                               score
                        ORDER BY score DESC
                        LIMIT 5
                    """, term=wildcard_term)
                    results["filters"] = [dict(r) for r in fcons_result]
                except Exception:
                    fcons_result = session.run("""
                        MATCH (f:FilterConsumable)
                        WHERE toLower(f.part_number) CONTAINS toLower($term)
                           OR toLower(f.model_name) CONTAINS toLower($term)
                           OR toLower(f.filter_type) CONTAINS toLower($term)
                        RETURN f.name AS id, f.part_number AS part_number,
                               f.model_name AS model_name, f.filter_type AS filter_type,
                               f.weight_kg AS weight_kg
                        LIMIT 5
                    """, term=query)
                    results["filters"] = [dict(r) for r in fcons_result]

                # Search MaterialSpecifications using fulltext index
                try:
                    mat_result = session.run("""
                        CALL db.index.fulltext.queryNodes("material_spec_fulltext", $term)
                        YIELD node AS m, score
                        RETURN m.code AS code,
                               m.full_name AS full_name,
                               m.corrosion_class AS corrosion_class,
                               m.description AS description,
                               score
                        ORDER BY score DESC
                        LIMIT 5
                    """, term=wildcard_term)
                    results["materials"] = [dict(r) for r in mat_result]
                except Exception:
                    mat_result = session.run("""
                        MATCH (m:MaterialSpecification)
                        WHERE toLower(m.code) CONTAINS toLower($term)
                           OR toLower(m.full_name) CONTAINS toLower($term)
                           OR toLower(m.name) CONTAINS toLower($term)
                           OR toLower(m.description) CONTAINS toLower($term)
                        RETURN m.code AS code, m.full_name AS full_name,
                               m.corrosion_class AS corrosion_class, m.description AS description
                        LIMIT 5
                    """, term=query)
                    results["materials"] = [dict(r) for r in mat_result]

                # Option matches already covered by product_variant_fulltext (options_json is indexed)
                # Just filter results that matched on options_json
                results["option_matches"] = [
                    {"variant_id": v["id"], "family": v["family"], "options_json": v["options_json"]}
                    for v in results["variants"]
                    if v.get("options_json") and query.lower() in v.get("options_json", "").lower()
                ]

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
                # Vector search for similar keywords (skip if index doesn't exist)
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

    # =========================================================================
    # GRAPH REASONING ENGINE - Layer 2/3 Query Methods
    # =========================================================================
    # These methods support the GraphReasoningEngine for graph-native rule evaluation

    def get_all_applications(self) -> list[dict]:
        """Get all Application nodes from the Domain layer.

        Returns:
            List of Application nodes with their properties, risks, and requirements

        Note: Results are cached for 5 minutes to reduce query overhead.
        """
        # Check cache first
        cached = _get_cached("all_applications")
        if cached is not None:
            return cached

        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (app:Application)
                    OPTIONAL MATCH (app)-[:HAS_RISK]->(risk:Risk)
                    OPTIONAL MATCH (app)-[:REQUIRES_RESISTANCE]->(req:Requirement)
                    WITH app,
                         collect(DISTINCT {id: risk.id, name: risk.name, severity: risk.severity, desc: risk.desc}) AS risks,
                         collect(DISTINCT {id: req.id, name: req.name, desc: req.desc}) AS requirements
                    RETURN app.id AS id,
                           app.name AS name,
                           app.keywords AS keywords,
                           [r IN risks WHERE r.id IS NOT NULL] AS risks,
                           [r IN requirements WHERE r.id IS NOT NULL] AS requirements
                    ORDER BY app.name
                """)
                return [dict(record) for record in result]

        result = self._execute_with_retry(_query)
        _set_cached("all_applications", result)
        return result

    def match_application_by_keywords(self, keywords: list[str]) -> Optional[dict]:
        """Find an Application node matching any of the provided keywords.

        Searches both the application name and keywords array.

        Args:
            keywords: List of keywords to match against

        Returns:
            First matching Application dict or None
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # Search for application where name or any keyword matches
                result = session.run("""
                    MATCH (app:Application)
                    WHERE toLower(app.name) IN $keywords
                       OR ANY(kw IN app.keywords WHERE toLower(kw) IN $keywords)
                    OPTIONAL MATCH (app)-[:HAS_RISK]->(risk:Risk)
                    OPTIONAL MATCH (app)-[:REQUIRES_RESISTANCE]->(req:Requirement)
                    WITH app,
                         collect(DISTINCT {id: risk.id, name: risk.name, severity: risk.severity}) AS risks,
                         collect(DISTINCT {id: req.id, name: req.name}) AS requirements
                    RETURN app.id AS id,
                           app.name AS name,
                           app.keywords AS keywords,
                           [r IN risks WHERE r.id IS NOT NULL] AS risks,
                           [r IN requirements WHERE r.id IS NOT NULL] AS requirements
                    LIMIT 1
                """, keywords=[k.lower() for k in keywords])
                record = result.single()
                return dict(record) if record else None

        return self._execute_with_retry(_query)

    def vector_search_applications(
        self,
        query_embedding: list[float],
        top_k: int = 3,
        min_score: float = 0.75
    ) -> list[dict]:
        """Perform vector similarity search on Application nodes.

        This is the fallback for hybrid search when keyword matching fails.
        Finds semantically similar applications (e.g., "Surgery Center" -> "Hospital").

        Args:
            query_embedding: The query embedding vector (3072 dimensions)
            top_k: Maximum number of results to return
            min_score: Minimum cosine similarity score (0.0-1.0)

        Returns:
            List of matching Application dicts with similarity scores
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    // Vector similarity search on Application embeddings
                    CALL db.index.vector.queryNodes('application_embeddings', $top_k, $embedding)
                    YIELD node AS app, score
                    WHERE score >= $min_score

                    // Get associated risks and requirements
                    OPTIONAL MATCH (app)-[:HAS_RISK]->(risk:Risk)
                    OPTIONAL MATCH (app)-[:REQUIRES_RESISTANCE]->(req:Requirement)

                    WITH app, score,
                         collect(DISTINCT {id: risk.id, name: risk.name, severity: risk.severity, desc: risk.desc}) AS risks,
                         collect(DISTINCT {id: req.id, name: req.name, desc: req.desc}) AS requirements

                    RETURN app.id AS id,
                           app.name AS name,
                           app.keywords AS keywords,
                           score AS similarity_score,
                           [r IN risks WHERE r.id IS NOT NULL] AS risks,
                           [r IN requirements WHERE r.id IS NOT NULL] AS requirements
                    ORDER BY score DESC
                """, embedding=query_embedding, top_k=top_k, min_score=min_score)
                return [dict(record) for record in result]

        try:
            return self._execute_with_retry(_query)
        except Exception as e:
            # Graceful degradation if vector index doesn't exist
            error_msg = str(e).lower()
            if "index" in error_msg or "vector" in error_msg:
                print(f"Warning: Vector search unavailable (index may not exist): {e}")
                return []
            raise

    def get_material_requirements(self, application_name: str) -> list[dict]:
        """Get material requirements for an application via REQUIRES_MATERIAL relationships.

        Traverses (Application)-[:REQUIRES_MATERIAL]->(Material) to find
        which materials are required for the specified application.

        Args:
            application_name: Name of the Application node

        Returns:
            List of required materials with their properties
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (app:Application)
                    WHERE app.name = $app_name OR app.id = $app_name
                    MATCH (app)-[r:REQUIRES_MATERIAL]->(mat:Material)
                    RETURN mat.code AS material_code,
                           mat.name AS material_name,
                           mat.corrosion_class AS corrosion_class,
                           r.reason AS reason
                    ORDER BY mat.corrosion_class DESC
                """, app_name=application_name)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def get_application_requirements(self, application_id: str) -> list[dict]:
        """Get requirements for an application via REQUIRES_RESISTANCE relationships.

        Args:
            application_id: ID of the Application node

        Returns:
            List of requirements (corrosion classes, regulations)

        Note: Results are cached for 5 minutes per application.
        """
        cache_key = f"app_requirements_{application_id}"
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (app:Application)
                    WHERE app.id = $app_id OR app.name = $app_id
                    OPTIONAL MATCH (app)-[:REQUIRES_RESISTANCE]->(req:Requirement)
                    OPTIONAL MATCH (app)-[:REQUIRES_COMPLIANCE]->(reg:Regulation)
                    WITH collect(DISTINCT {id: req.id, name: req.name, desc: req.desc, type: 'Requirement'}) AS reqs,
                         collect(DISTINCT {id: reg.id, name: reg.name, desc: reg.desc, type: 'Regulation'}) AS regs
                    RETURN [r IN reqs WHERE r.id IS NOT NULL] + [r IN regs WHERE r.id IS NOT NULL] AS requirements
                """, app_id=application_id)
                record = result.single()
                return record['requirements'] if record else []

        result = self._execute_with_retry(_query)
        _set_cached(cache_key, result)
        return result

    def get_materials_meeting_requirements(self, application_id: str) -> list[dict]:
        """Get materials that meet an application's requirements.

        Traverses (Application)-[:REQUIRES_RESISTANCE]->(Requirement)<-[:MEETS_REQUIREMENT]-(Material)

        Args:
            application_id: ID of the Application node

        Returns:
            List of suitable materials
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (app:Application)
                    WHERE app.id = $app_id OR app.name = $app_id
                    MATCH (app)-[:REQUIRES_RESISTANCE]->(req:Requirement)<-[:MEETS_REQUIREMENT]-(mat:Material)
                    RETURN DISTINCT
                           mat.id AS id,
                           mat.code AS code,
                           mat.name AS name,
                           mat.corrosion_class AS corrosion_class,
                           req.name AS requirement_name
                    ORDER BY mat.corrosion_class DESC
                """, app_id=application_id)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def get_application_generated_substances(self, application_id: str) -> list[dict]:
        """Get substances generated by an application via GENERATES relationships.

        Args:
            application_id: ID of the Application node

        Returns:
            List of generated substances
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (app:Application)
                    WHERE app.id = $app_id OR app.name = $app_id
                    MATCH (app)-[:GENERATES]->(sub:Substance)
                    RETURN sub.id AS id,
                           sub.name AS name
                """, app_id=application_id)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def get_application_risks(self, application_id: str) -> list[dict]:
        """Get risks associated with an application via HAS_RISK relationships.

        Args:
            application_id: ID of the Application node

        Returns:
            List of risks
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (app:Application)
                    WHERE app.id = $app_id OR app.name = $app_id
                    MATCH (app)-[:HAS_RISK]->(risk:Risk)
                    RETURN risk.id AS id,
                           risk.name AS name,
                           risk.severity AS severity,
                           risk.desc AS desc
                """, app_id=application_id)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def get_product_vulnerabilities(self, product_family: str) -> list[dict]:
        """Get vulnerabilities for a product family via VULNERABLE_TO and PRONE_TO relationships.

        Traverses ProductFamily to find what substances/risks the product is susceptible to.

        Args:
            product_family: Product family code (e.g., 'GDB', 'GDC')

        Returns:
            List of vulnerabilities with consequences and mitigations
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # Get vulnerabilities to substances and risks
                result = session.run("""
                    MATCH (pf:ProductFamily)
                    WHERE pf.id = 'FAM_' + $family OR pf.name CONTAINS $family
                    OPTIONAL MATCH (pf)-[r1:VULNERABLE_TO]->(target)
                    OPTIONAL MATCH (pf)-[r2:PRONE_TO]->(risk:Risk)
                    WITH pf,
                         collect(DISTINCT {
                             target_id: target.id,
                             target_name: target.name,
                             reason: r1.reason,
                             type: labels(target)[0]
                         }) AS vulnerabilities,
                         collect(DISTINCT {
                             risk_id: risk.id,
                             risk_name: risk.name,
                             severity: risk.severity,
                             desc: risk.desc
                         }) AS prone_risks
                    RETURN pf.name AS product_family,
                           [v IN vulnerabilities WHERE v.target_id IS NOT NULL] AS vulnerabilities,
                           [r IN prone_risks WHERE r.risk_id IS NOT NULL] AS prone_risks
                """, family=product_family)
                record = result.single()
                if not record:
                    return []

                # Combine vulnerabilities and prone_risks
                all_vulns = []
                for v in record['vulnerabilities']:
                    all_vulns.append({
                        'product_family': record['product_family'],
                        'target_id': v['target_id'],
                        'target_name': v['target_name'],
                        'reason': v['reason'],
                        'type': v['type']
                    })
                for r in record['prone_risks']:
                    all_vulns.append({
                        'product_family': record['product_family'],
                        'risk_id': r['risk_id'],
                        'risk_name': r['risk_name'],
                        'severity': r['severity'],
                        'target_name': r['risk_name'],
                        'reason': r['desc']
                    })
                return all_vulns

        return self._execute_with_retry(_query)

    def get_application_generated_risks(self, application_name: str) -> list[dict]:
        """Get risks generated by an application via GENERATES relationships.

        Traverses (Application)-[:GENERATES]->(Substance/Risk) to find what
        is generated by the specified application environment.

        Args:
            application_name: Name or ID of the Application node

        Returns:
            List of generated substances/risks
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (app:Application)
                    WHERE app.name = $app_name OR app.id = $app_name
                    OPTIONAL MATCH (app)-[:GENERATES]->(sub:Substance)
                    OPTIONAL MATCH (app)-[:HAS_RISK]->(risk:Risk)
                    WITH collect(DISTINCT {id: sub.id, name: sub.name, type: 'Substance'}) AS substances,
                         collect(DISTINCT {id: risk.id, name: risk.name, severity: risk.severity, type: 'Risk'}) AS risks
                    RETURN [s IN substances WHERE s.id IS NOT NULL] + [r IN risks WHERE r.id IS NOT NULL] AS generated
                """, app_name=application_name)
                record = result.single()
                return record['generated'] if record else []

        return self._execute_with_retry(_query)

    def get_risk_mitigations(self, risk_id: str) -> list[dict]:
        """Get solutions that mitigate a specific risk via MITIGATED_BY relationships.

        Traverses (Risk)-[:MITIGATED_BY]->(Solution) to find solutions
        that can address the specified risk.

        Args:
            risk_id: ID or name of the Risk node

        Returns:
            List of solutions with descriptions
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (risk:Risk)-[:MITIGATED_BY]->(sol:Solution)
                    WHERE risk.id = $risk_id OR risk.name = $risk_id
                    RETURN sol.id AS id,
                           sol.name AS name,
                           sol.desc AS description
                """, risk_id=risk_id)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def check_outdoor_suitability(self, product_family: str) -> Optional[dict]:
        """Check if a product is suitable for outdoor installation.

        Checks for VULNERABLE_TO condensation risk and SUITABLE_FOR outdoor env.

        Args:
            product_family: Product family code (e.g., 'GDB', 'GDC')

        Returns:
            Dict with suitability info or None
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pf:ProductFamily)
                    WHERE pf.id = 'FAM_' + $family OR pf.name CONTAINS $family
                    OPTIONAL MATCH (pf)-[:VULNERABLE_TO]->(cond_risk:Risk {id: 'RISK_COND'})
                    OPTIONAL MATCH (pf)-[:PROTECTS_AGAINST]->(cond_risk2:Risk {id: 'RISK_COND'})
                    OPTIONAL MATCH (pf)-[:SUITABLE_FOR]->(env:Environment {id: 'ENV_OUTDOOR'})
                    RETURN pf.name AS product_family,
                           cond_risk IS NOT NULL AS has_condensation_risk,
                           cond_risk2 IS NOT NULL AS protects_against_condensation,
                           env IS NOT NULL AS suitable_for_outdoor
                """, family=product_family)
                record = result.single()
                return dict(record) if record else None

        return self._execute_with_retry(_query)

    def get_variable_features(self, product_family: str) -> list[dict]:
        """Get variable features that require user selection for a product family.

        Queries the graph for features marked as 'is_variable: true' that
        require user input before a final product configuration can be made.

        This enables the "Variance Check Loop" - the system must ask about
        ALL variable features before giving a final answer.

        Args:
            product_family: Product family code (e.g., 'GDB', 'GDMI')

        Returns:
            List of variable features with their options and questions

        Note: Results are cached for 5 minutes per product family.
        """
        # Check cache first
        cache_key = f"variable_features_{product_family}"
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pf:ProductFamily)-[:HAS_VARIABLE_FEATURE]->(f:VariableFeature {is_variable: true})
                    WHERE pf.id = 'FAM_' + $family
                       OR pf.name CONTAINS $family
                       OR f.applies_to = $family

                    OPTIONAL MATCH (f)-[:SELECTION_DEPENDS_ON]->(d:Discriminator)
                    OPTIONAL MATCH (f)-[:HAS_OPTION]->(o:FeatureOption)

                    WITH f, d, collect({
                        id: o.id,
                        name: o.name,
                        value: o.value,
                        description: o.description,
                        is_default: o.is_default,
                        // Enhanced UX fields
                        display_label: o.display_label,
                        benefit: o.benefit,
                        use_case: o.use_case,
                        is_recommended: o.is_recommended
                    }) AS options

                    RETURN f.id AS feature_id,
                           COALESCE(f.feature_name, f.name) AS feature_name,
                           f.description AS feature_description,
                           COALESCE(f.question, d.question) AS question,
                           COALESCE(f.why_needed, d.why_needed) AS why_needed,
                           COALESCE(f.parameter_name, d.parameter_name) AS parameter_name,
                           [opt IN options WHERE opt.id IS NOT NULL] AS options,
                           COALESCE(f.auto_resolve, false) AS auto_resolve,
                           f.default_value AS default_value
                    ORDER BY f.feature_name
                """, family=product_family)
                return [dict(record) for record in result]

        try:
            result = self._execute_with_retry(_query)
            _set_cached(cache_key, result)
            return result
        except Exception as e:
            print(f"Warning: Could not get variable features: {e}")
            return []

    def get_connection_length_offset(self, family_id: str, connection_code: str) -> int:
        """Get housing length offset for a connection type.

        Flange connections add ~50mm to the base housing length.
        Returns the offset in mm (0 for PG, 50 for Flange).
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pf:ProductFamily {id: $fid})-[:HAS_VARIABLE_FEATURE]->
                          (f:VariableFeature {parameter_name: 'connection_type'})-[:HAS_OPTION]->
                          (o:FeatureOption {value: $code})
                    RETURN o.length_offset_mm AS offset
                """, fid=family_id, code=connection_code)
                record = result.single()
                return int(record["offset"]) if record and record["offset"] is not None else 0

        try:
            return self._execute_with_retry(_query)
        except Exception as e:
            print(f"Warning: Could not get connection length offset: {e}")
            return 0

    def get_available_materials(self, family_id: str) -> list:
        """Get all materials available for a product family.

        Returns list of dicts with 'id', 'name', 'code' for each linked Material.
        """
        cache_key = f"avail_mat_{family_id}"
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pf:ProductFamily {id: $fid})-[:AVAILABLE_IN_MATERIAL]->(m:Material)
                    RETURN m.id AS id, m.name AS name, COALESCE(m.code, m.id) AS code
                    ORDER BY m.name
                """, fid=family_id)
                return [dict(r) for r in result]

        try:
            materials = self._execute_with_retry(_query)
            _set_cached(cache_key, materials)
            return materials
        except Exception as e:
            print(f"Warning: Could not get available materials: {e}")
            return []

    def get_reference_airflow_for_dimensions(self, width_mm: int, height_mm: int, product_family: str = None) -> dict:
        """Get reference airflow from ProductVariant for given housing dimensions.

        v4.0: ProductVariant is the primary source (family-specific airflow).
        When product_family is provided, returns the CORRECT family-specific airflow.
        Falls back to DimensionModule when no ProductVariant match.

        Returns:
            Dict with reference_airflow_m3h and label, or empty dict if not found.
        """
        cache_key = f"ref_airflow_{product_family or 'any'}_{width_mm}x{height_mm}"
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # Primary: ProductVariant lookup (family-specific if provided)
                if product_family:
                    pf_id = product_family if product_family.startswith("FAM_") else f"FAM_{product_family.upper()}"
                    result = session.run("""
                        MATCH (pf:ProductFamily {id: $pf_id})-[:HAS_VARIANT]->(pv:ProductVariant)
                        WHERE (pv.width_mm = $w AND pv.height_mm = $h)
                           OR (pv.width_mm = $h AND pv.height_mm = $w)
                        RETURN pv.reference_airflow_m3h AS reference_airflow_m3h,
                               pv.label AS label,
                               pv.width_mm AS width_mm,
                               pv.height_mm AS height_mm
                        LIMIT 1
                    """, pf_id=pf_id, w=width_mm, h=height_mm)
                else:
                    result = session.run("""
                        MATCH (pv:ProductVariant)
                        WHERE ((pv.width_mm = $w AND pv.height_mm = $h)
                            OR (pv.width_mm = $h AND pv.height_mm = $w))
                          AND pv.reference_airflow_m3h IS NOT NULL
                        RETURN pv.reference_airflow_m3h AS reference_airflow_m3h,
                               pv.label AS label,
                               pv.width_mm AS width_mm,
                               pv.height_mm AS height_mm
                        ORDER BY pv.reference_airflow_m3h DESC
                        LIMIT 1
                    """, w=width_mm, h=height_mm)
                record = result.single()
                if record and record.get("reference_airflow_m3h"):
                    return dict(record)

                # Fallback: DimensionModule (legacy)
                result2 = session.run("""
                    MATCH (d:DimensionModule)
                    WHERE (d.width_mm = $w AND d.height_mm = $h)
                       OR (d.width_mm = $h AND d.height_mm = $w)
                    RETURN d.reference_airflow_m3h AS reference_airflow_m3h,
                           d.label AS label,
                           d.width_mm AS width_mm,
                           d.height_mm AS height_mm
                    LIMIT 1
                """, w=width_mm, h=height_mm)
                record2 = result2.single()
                return dict(record2) if record2 else {}

        try:
            result = self._execute_with_retry(_query)
            _set_cached(cache_key, result)
            return result
        except Exception as e:
            print(f"Warning: Could not get reference airflow: {e}")
            return {}

    def get_option_geometric_constraints(
        self,
        product_family: str,
        selected_options: list[str]
    ) -> list[dict]:
        """Get geometric constraints for selected options.

        Queries the graph for options that have min_required_housing_length
        property, which indicates they consume physical space in the housing.

        This enables the "Physical Constraint Validator" - ensuring that
        options like 'Polis' (which requires 900mm) cannot be fitted into
        a smaller housing.

        Args:
            product_family: Product family code (e.g., 'GDC')
            selected_options: List of option IDs or names to check

        Returns:
            List of option constraints with their geometric requirements
        """
        if not selected_options:
            return []

        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # Query options that have geometric constraints
                # Matches by option ID, name, or value (case-insensitive)
                result = session.run("""
                    MATCH (pf:ProductFamily)-[:HAS_VARIABLE_FEATURE]->(f:VariableFeature)
                          -[:HAS_OPTION]->(o:FeatureOption)
                    WHERE (pf.id = 'FAM_' + $family OR pf.name CONTAINS $family)
                      AND (
                          toLower(o.id) IN $options_lower
                          OR toLower(o.name) IN $options_lower
                          OR toLower(o.value) IN $options_lower
                      )
                      AND o.min_required_housing_length IS NOT NULL

                    RETURN DISTINCT o.id AS option_id,
                           COALESCE(o.name, o.value) AS option_name,
                           o.min_required_housing_length AS min_required_housing_length,
                           o.physics_logic AS physics_logic,
                           f.feature_name AS feature_name,
                           f.parameter_name AS parameter_name
                """,
                    family=product_family,
                    options_lower=[opt.lower() for opt in selected_options]
                )
                return [dict(record) for record in result]

        try:
            return self._execute_with_retry(_query)
        except Exception as e:
            print(f"Warning: Could not get option geometric constraints: {e}")
            return []

    def get_variant_weight(self, variant_name: str, housing_length: int = None) -> float | None:
        """Get the weight in kg for a specific product variant.

        v4.0: Handles three weight schemas:
        1. Single weight (GDP): weight_kg property
        2. Dual weights (GDB, GDMI, GDC): weight_kg_short / weight_kg_long
           Uses housing_length to pick the correct one.

        Args:
            variant_name: Variant name like 'GDB-600x600' or 'GDP-600x600'
            housing_length: Optional housing length in mm to select short/long weight

        Returns:
            Weight in kg, or None if not found
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (v:ProductVariant)
                    WHERE v.name = $name OR v.name CONTAINS $name
                    RETURN v.weight_kg AS weight_kg,
                           v.weight_kg_short AS weight_kg_short,
                           v.weight_kg_long AS weight_kg_long,
                           v.housing_length_mm AS housing_length_mm,
                           v.housing_length_short_mm AS housing_length_short_mm,
                           v.housing_length_long_mm AS housing_length_long_mm
                    LIMIT 1
                """, name=variant_name)
                record = result.single()
                if not record:
                    return None
                r = dict(record)
                # v4.1: Check dual weights FIRST (more precise than legacy weight_kg)
                # Legacy weight_kg is always the short weight and was set before
                # dual-weight support was added. Dual weights take priority.
                if r.get("weight_kg_short") is not None and r.get("weight_kg_long") is not None:
                    if housing_length and r.get("housing_length_long_mm"):
                        threshold = (r["housing_length_short_mm"] or 0) + (r["housing_length_long_mm"] or 0)
                        if threshold > 0:
                            midpoint = threshold / 2
                            selected = r["weight_kg_long"] if housing_length >= midpoint else r["weight_kg_short"]
                            print(f"⚖️ [WEIGHT] {variant_name}: len={housing_length} midpoint={midpoint} → {'long' if housing_length >= midpoint else 'short'}={selected}kg")
                            return selected
                    # No housing_length provided: return short weight as safe default
                    return r["weight_kg_short"]
                # Single-weight product (e.g., GDP) — no dual-weight data available
                if r.get("weight_kg") is not None:
                    return r["weight_kg"]
                return None

        try:
            return self._execute_with_retry(_query)
        except Exception as e:
            print(f"Warning: Could not get variant weight for {variant_name}: {e}")
            return None

    def get_default_length_variant(self, family_id: str) -> int | None:
        """Get the default (shortest) length variant for a product family.

        Returns the length_mm of the first length variant, or None if not found.
        Used as fallback when housing_length is not set from user input.
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pf:ProductFamily {id: $fid})-[:HAS_LENGTH_VARIANT]->(lv)
                    RETURN lv.length_mm AS length_mm, lv.is_default AS is_default
                    ORDER BY lv.is_default DESC, lv.length_mm ASC
                    LIMIT 1
                """, fid=family_id)
                record = result.single()
                if record and record["length_mm"]:
                    return int(record["length_mm"])
                return None

        try:
            return self._execute_with_retry(_query)
        except Exception:
            return None

    def get_product_family_code_format(self, family_id: str):
        """Get the code_format template and metadata for a product family.

        Returns dict with 'fmt' and 'default_frame_depth' (for GDP-style codes
        where the length field represents frame depth, not housing length).
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pf:ProductFamily {id: $fid})
                    RETURN pf.code_format AS fmt,
                           pf.default_frame_depth AS default_frame_depth
                """, fid=family_id)
                record = result.single()
                if not record:
                    return None
                return {
                    "fmt": record["fmt"],
                    "default_frame_depth": record["default_frame_depth"],
                }

        try:
            return self._execute_with_retry(_query)
        except Exception as e:
            print(f"Warning: Could not get code_format for {family_id}: {e}")
            return None

    def get_dimension_module_weight(self, width_mm: int, height_mm: int):
        """Get weight data from DimensionModule graph node for given dimensions."""
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (dm:DimensionModule)
                    WHERE dm.width_mm = $w AND dm.height_mm = $h
                    RETURN dm.unit_weight_kg AS unit_weight_kg,
                           dm.weight_per_mm_length AS weight_per_mm_length,
                           dm.reference_length_mm AS reference_length_mm
                    LIMIT 1
                """, w=width_mm, h=height_mm)
                record = result.single()
                if record:
                    return {
                        "unit_weight_kg": record["unit_weight_kg"],
                        "weight_per_mm_length": record["weight_per_mm_length"],
                        "reference_length_mm": record["reference_length_mm"],
                    }
                return None

        try:
            return self._execute_with_retry(_query)
        except Exception as e:
            print(f"Warning: Could not get DimensionModule weight for {width_mm}x{height_mm}: {e}")
            return None

    def get_clarification_params(self, product_family: str = None) -> list[dict]:
        """Get clarification parameters from the Playbook layer.

        Retrieves ClarificationParam nodes with their options, optionally
        filtered by product family.

        Args:
            product_family: Optional product family to filter applicable params

        Returns:
            List of clarification parameters sorted by priority
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                if product_family:
                    # Filter by applicable product family
                    result = session.run("""
                        MATCH (param:ClarificationParam)
                        WHERE 'all' IN param.applies_to OR $family IN param.applies_to
                        OPTIONAL MATCH (param)-[:HAS_OPTION]->(opt:ParamOption)
                        WITH param, collect({
                            value: opt.value,
                            description: opt.description,
                            leads_to: opt.leads_to,
                            implications: opt.implications,
                            housing_length: opt.housing_length,
                            is_default: opt.is_default
                        }) AS options
                        RETURN param.name AS name,
                               param.question AS question,
                               param.why_needed AS why_needed,
                               param.priority AS priority,
                               param.applies_to AS applies_to,
                               [opt IN options WHERE opt.value IS NOT NULL] AS options
                        ORDER BY param.priority
                    """, family=product_family)
                else:
                    # Get all params
                    result = session.run("""
                        MATCH (param:ClarificationParam)
                        OPTIONAL MATCH (param)-[:HAS_OPTION]->(opt:ParamOption)
                        WITH param, collect({
                            value: opt.value,
                            description: opt.description,
                            leads_to: opt.leads_to,
                            implications: opt.implications,
                            housing_length: opt.housing_length,
                            is_default: opt.is_default
                        }) AS options
                        RETURN param.name AS name,
                               param.question AS question,
                               param.why_needed AS why_needed,
                               param.priority AS priority,
                               param.applies_to AS applies_to,
                               [opt IN options WHERE opt.value IS NOT NULL] AS options
                        ORDER BY param.priority
                    """)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def get_required_parameters(self, product_family: str) -> list[dict]:
        """Get required parameters for a product family via REQUIRES_PARAMETER relationships.

        Traverses (ProductFamily)-[:REQUIRES_PARAMETER]->(Parameter)-[:ASKED_VIA]->(Question)

        Args:
            product_family: Product family code (e.g., 'GDB', 'GDC')

        Returns:
            List of parameters with their questions
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pf:ProductFamily)-[r:REQUIRES_PARAMETER]->(param:Parameter)
                    WHERE pf.id = 'FAM_' + $family OR pf.name CONTAINS $family
                    OPTIONAL MATCH (param)-[:ASKED_VIA]->(q:Question)
                    RETURN param.id AS param_id,
                           param.name AS param_name,
                           param.type AS param_type,
                           param.unit AS param_unit,
                           r.reason AS reason,
                           q.id AS question_id,
                           q.text AS question_text,
                           q.intent AS intent,
                           q.priority AS priority
                    ORDER BY q.priority
                """, family=product_family)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def get_contextual_clarifications(self, application_id: str, product_family: str = None) -> list[dict]:
        """Get contextual clarification rules triggered by application context.

        Traverses ClarificationRule nodes that are triggered by the application
        and optionally apply to the product family.

        Args:
            application_id: ID of the Application node
            product_family: Optional product family to filter rules

        Returns:
            List of parameters demanded by triggered rules
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                if product_family:
                    result = session.run("""
                        MATCH (rule:ClarificationRule)-[:TRIGGERED_BY_CONTEXT]->(app:Application)
                        WHERE app.id = $app_id OR app.name = $app_id
                        MATCH (rule)-[:APPLIES_TO_PRODUCT]->(pf:ProductFamily)
                        WHERE pf.id = 'FAM_' + $family OR pf.name CONTAINS $family
                        MATCH (rule)-[:DEMANDS_PARAMETER]->(param:Parameter)
                        OPTIONAL MATCH (param)-[:ASKED_VIA]->(q:Question)
                        RETURN DISTINCT
                               rule.id AS rule_id,
                               rule.name AS rule_name,
                               param.id AS param_id,
                               param.name AS param_name,
                               q.id AS question_id,
                               q.text AS question_text,
                               q.intent AS intent,
                               q.priority AS priority
                        ORDER BY q.priority
                    """, app_id=application_id, family=product_family)
                else:
                    result = session.run("""
                        MATCH (rule:ClarificationRule)-[:TRIGGERED_BY_CONTEXT]->(app:Application)
                        WHERE app.id = $app_id OR app.name = $app_id
                        MATCH (rule)-[:DEMANDS_PARAMETER]->(param:Parameter)
                        OPTIONAL MATCH (param)-[:ASKED_VIA]->(q:Question)
                        RETURN DISTINCT
                               rule.id AS rule_id,
                               rule.name AS rule_name,
                               param.id AS param_id,
                               param.name AS param_name,
                               q.id AS question_id,
                               q.text AS question_text,
                               q.intent AS intent,
                               q.priority AS priority
                        ORDER BY q.priority
                    """, app_id=application_id)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def get_risk_strategy(self, risk_id: str) -> Optional[dict]:
        """Get the strategy triggered by a specific risk.

        Traverses (Risk)-[:TRIGGERS_STRATEGY]->(Strategy)

        Args:
            risk_id: ID or name of the Risk node

        Returns:
            Strategy dict with action and instruction, or None
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (risk:Risk)-[:TRIGGERS_STRATEGY]->(strat:Strategy)
                    WHERE risk.id = $risk_id OR risk.name = $risk_id
                    RETURN strat.id AS id,
                           strat.name AS name,
                           strat.action AS action,
                           strat.instruction AS instruction
                """, risk_id=risk_id)
                record = result.single()
                return dict(record) if record else None

        return self._execute_with_retry(_query)

    def get_cross_sell_suggestions(self, product_family: str) -> list[dict]:
        """Get cross-sell suggestions for a product family.

        Traverses (ProductFamily)-[:SUGGESTS_CROSS_SELL]->(Option/Solution)

        Args:
            product_family: Product family code (e.g., 'GDB', 'GDC')

        Returns:
            List of suggested cross-sell items with reasons
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (pf:ProductFamily)-[r:SUGGESTS_CROSS_SELL]->(item)
                    WHERE pf.id = 'FAM_' + $family OR pf.name CONTAINS $family
                    RETURN item.id AS id,
                           item.name AS name,
                           item.type AS type,
                           item.desc AS description,
                           r.reason AS reason,
                           labels(item)[0] AS node_type
                """, family=product_family)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def check_material_suitability(self, application_name: str, material_code: str) -> dict:
        """Check if a material is suitable for an application.

        Directly queries the graph to see if the material meets the
        application's requirements.

        Args:
            application_name: Name of the Application node
            material_code: Material code to check (e.g., 'FZ', 'RF')

        Returns:
            Dict with is_suitable bool, required_materials list, and reason
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (app:Application {name: $app_name})
                    OPTIONAL MATCH (app)-[r:REQUIRES_MATERIAL]->(required_mat:Material)
                    WITH app, collect({
                        code: required_mat.code,
                        name: required_mat.full_name,
                        reason: r.reason
                    }) AS required_materials

                    // Check if the requested material is in the required list
                    WITH app, required_materials,
                         [mat IN required_materials WHERE mat.code IS NOT NULL] AS valid_materials,
                         ANY(mat IN required_materials WHERE mat.code = $material_code) AS is_suitable

                    RETURN app.name AS application,
                           app.criticality AS criticality,
                           app.concern AS concern,
                           valid_materials AS required_materials,
                           is_suitable,
                           CASE WHEN size(valid_materials) = 0 THEN true ELSE is_suitable END AS final_suitable
                """, app_name=application_name, material_code=material_code)
                record = result.single()
                if record:
                    return {
                        "application": record["application"],
                        "criticality": record["criticality"],
                        "concern": record["concern"],
                        "required_materials": record["required_materials"],
                        "is_suitable": record["final_suitable"],
                        "checked_material": material_code
                    }
                return {"is_suitable": True, "required_materials": []}

        return self._execute_with_retry(_query)

    def get_accessory_compatibility(self, accessory_code: str, product_family: str) -> dict:
        """Check if an accessory is compatible with a product family.

        Uses the allow-list approach: if there's no HAS_COMPATIBLE_ACCESSORY
        relationship, the combination is NOT allowed.

        Args:
            accessory_code: Accessory code or name (e.g., 'EXL', 'L', 'Polis')
            product_family: Product family code (e.g., 'GDB', 'GDC')

        Returns:
            Dict with is_compatible bool, reason, and alternative suggestions
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    // Find the accessory by id or name - prefer nodes with proper IDs
                    MATCH (acc:Accessory)
                    WHERE acc.id = 'ACC_' + toUpper($acc_code)
                       OR acc.name = $acc_code
                       OR toUpper(acc.name) = toUpper($acc_code)

                    // Prioritize accessory with proper ID
                    WITH acc
                    ORDER BY CASE WHEN acc.id IS NOT NULL THEN 0 ELSE 1 END
                    LIMIT 1

                    // Find the product family - prefer exact ID match
                    MATCH (pf:ProductFamily)
                    WHERE pf.id = 'FAM_' + toUpper($family)
                       OR pf.name CONTAINS $family

                    // Prioritize product family with exact ID match
                    WITH acc, pf
                    ORDER BY CASE WHEN pf.id = 'FAM_' + toUpper($family) THEN 0 ELSE 1 END
                    LIMIT 1

                    // Now check relationships for the selected pair
                    OPTIONAL MATCH (pf)-[compat:HAS_COMPATIBLE_ACCESSORY]->(acc)
                    OPTIONAL MATCH (pf)-[incompat:INCOMPATIBLE_WITH]->(acc)
                    OPTIONAL MATCH (pf)-[:HAS_COMPATIBLE_ACCESSORY]->(other_acc:Accessory)
                    OPTIONAL MATCH (pf)-[:USES_MOUNTING_SYSTEM]->(mount:MountingSystem)

                    RETURN acc.name AS accessory_name,
                           acc.full_name AS accessory_full_name,
                           acc.description AS accessory_description,
                           acc.category AS accessory_category,
                           pf.name AS product_family,
                           pf.id AS product_family_id,
                           compat IS NOT NULL AS is_explicitly_compatible,
                           compat.note AS compatibility_note,
                           incompat IS NOT NULL AS is_explicitly_incompatible,
                           incompat.reason AS incompatibility_reason,
                           collect(DISTINCT other_acc.name) AS compatible_accessories,
                           head(collect(DISTINCT mount.name)) AS uses_mounting_system
                """, acc_code=accessory_code, family=product_family)
                record = result.single()

                if not record or not record["accessory_name"]:
                    # Accessory not found in graph
                    return {
                        "accessory": accessory_code,
                        "product_family": product_family,
                        "is_compatible": None,  # Unknown - not in graph
                        "status": "UNKNOWN",
                        "reason": f"Accessory '{accessory_code}' not found in compatibility database"
                    }

                # STRICT ALLOW-LIST: Must have explicit compatibility OR not be incompatible
                is_explicitly_compatible = record["is_explicitly_compatible"]
                is_explicitly_incompatible = record["is_explicitly_incompatible"]

                if is_explicitly_incompatible:
                    # Blocked with reason
                    return {
                        "accessory": record["accessory_name"],
                        "accessory_full_name": record["accessory_full_name"],
                        "product_family": record["product_family"],
                        "is_compatible": False,
                        "status": "BLOCKED",
                        "reason": record["incompatibility_reason"],
                        "compatible_alternatives": record["compatible_accessories"],
                        "uses_mounting_system": record["uses_mounting_system"]
                    }
                elif is_explicitly_compatible:
                    # Allowed
                    return {
                        "accessory": record["accessory_name"],
                        "accessory_full_name": record["accessory_full_name"],
                        "product_family": record["product_family"],
                        "is_compatible": True,
                        "status": "ALLOWED",
                        "note": record["compatibility_note"]
                    }
                else:
                    # No relationship found - default to NOT ALLOWED (strict mode)
                    return {
                        "accessory": record["accessory_name"],
                        "accessory_full_name": record["accessory_full_name"],
                        "product_family": record["product_family"],
                        "is_compatible": False,
                        "status": "NOT_ALLOWED",
                        "reason": f"No compatibility relationship found. {record['accessory_name']} is not listed as compatible with {record['product_family']}.",
                        "compatible_alternatives": record["compatible_accessories"],
                        "uses_mounting_system": record["uses_mounting_system"]
                    }

        return self._execute_with_retry(_query)

    def get_geometric_constraints(self, option_name: str) -> Optional[dict]:
        """Get geometric constraints for an option.

        Args:
            option_name: Option name or alias

        Returns:
            Dict with constraint details or None
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (gc:GeometricConstraint)
                    WHERE gc.option = $option
                       OR $option IN gc.aliases
                    RETURN gc.option AS option,
                           gc.aliases AS aliases,
                           gc.min_length_mm AS min_length_mm,
                           gc.additional_length_mm AS additional_length_mm,
                           gc.message AS message
                    LIMIT 1
                """, option=option_name)
                record = result.single()
                return dict(record) if record else None

        return self._execute_with_retry(_query)

    def check_unmitigated_physics_risks(self, product_family: str, environment_id: str = None, environment_keywords: list[str] = None) -> list[dict]:
        """Check for unmitigated physics-based risks.

        This is the core of the "Mitigation Path Validator":
        If Environment CAUSES Risk, and Risk is MITIGATED_BY Feature,
        but Product does NOT have that Feature -> BLOCK.

        This moves physics logic FROM the LLM (unreliable) TO the Graph (authoritative).

        Args:
            product_family: Product family code (e.g., 'GDB', 'GDMI')
            environment_id: Optional specific environment ID (e.g., 'ENV_OUTDOOR')
            environment_keywords: Optional keywords to detect environment from query

        Returns:
            List of unmitigated risks with physics explanations and safe alternatives
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # Build environment match condition
                if environment_id:
                    env_condition = "env.id = $env_id"
                elif environment_keywords:
                    # Match environment by keywords
                    env_condition = "ANY(kw IN env.keywords WHERE ANY(qkw IN $keywords WHERE toLower(qkw) CONTAINS toLower(kw) OR toLower(kw) CONTAINS toLower(qkw)))"
                else:
                    return []

                result = session.run(f"""
                    // Find the environment context
                    MATCH (env:Environment)
                    WHERE {env_condition}

                    // Find risks caused by this environment
                    MATCH (env)-[causes:CAUSES]->(risk:Risk)

                    // Find the product family
                    MATCH (prod:ProductFamily)
                    WHERE prod.id = 'FAM_' + toUpper($product_family)
                       OR prod.name CONTAINS $product_family

                    // Check if product has mitigation via feature (HAS_FEATURE or INCLUDES_FEATURE)
                    OPTIONAL MATCH (prod)-[:HAS_FEATURE|INCLUDES_FEATURE]->(feat:Feature)<-[:MITIGATED_BY]-(risk)
                    OPTIONAL MATCH (prod)-[protects:PROTECTS_AGAINST]->(risk)

                    // Only return if NO mitigation exists (unmitigated risk)
                    WITH env, causes, risk, prod, feat, protects
                    WHERE feat IS NULL AND protects IS NULL

                    // Find the required mitigation feature
                    OPTIONAL MATCH (risk)-[:MITIGATED_BY]->(required_feat:Feature)

                    // Find products that DO have the mitigation (safe alternatives)
                    OPTIONAL MATCH (safe_prod:ProductFamily)-[:HAS_FEATURE|INCLUDES_FEATURE]->(required_feat)
                    WHERE safe_prod <> prod

                    RETURN env.id AS environment_id,
                           env.name AS environment_name,
                           risk.id AS risk_id,
                           risk.name AS risk_name,
                           risk.severity AS risk_severity,
                           risk.physics_explanation AS physics_explanation,
                           risk.consequence AS consequence,
                           risk.user_misconception AS user_misconception,
                           causes.certainty AS risk_certainty,
                           required_feat.name AS required_feature,
                           required_feat.physics_function AS mitigation_mechanism,
                           collect(DISTINCT safe_prod.name) AS safe_alternatives,
                           prod.name AS blocked_product
                """, product_family=product_family,
                     env_id=environment_id,
                     keywords=environment_keywords or [])

                return [dict(record) for record in result]

        try:
            return self._execute_with_retry(_query)
        except Exception as e:
            print(f"Warning: Physics risk check failed: {e}")
            return []

    def get_safe_alternative_for_risk(self, risk_id: str) -> list[dict]:
        """Get products that can mitigate a specific risk.

        Args:
            risk_id: Risk ID (e.g., 'RISK_COND')

        Returns:
            List of products with the required mitigation feature
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (risk:Risk {id: $risk_id})
                    MATCH (risk)-[:MITIGATED_BY]->(feat:Feature)
                    MATCH (prod:ProductFamily)-[:HAS_FEATURE]->(feat)
                    RETURN prod.id AS product_id,
                           prod.name AS product_name,
                           feat.name AS has_feature,
                           feat.physics_function AS mitigation_mechanism
                """, risk_id=risk_id)
                return [dict(record) for record in result]

        return self._execute_with_retry(_query)

    def detect_environment_from_keywords(self, keywords: list[str]) -> dict | None:
        """Detect environment context from query keywords.

        Args:
            keywords: List of keywords from the query

        Returns:
            Environment dict if found, None otherwise
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (env:Environment)
                    WHERE ANY(kw IN env.keywords
                              WHERE ANY(qkw IN $keywords
                                        WHERE toLower(qkw) CONTAINS toLower(kw)
                                           OR toLower(kw) CONTAINS toLower(qkw)))
                    RETURN env.id AS id,
                           env.name AS name,
                           env.keywords AS keywords,
                           env.description AS description
                    LIMIT 1
                """, keywords=keywords)
                record = result.single()
                return dict(record) if record else None

        return self._execute_with_retry(_query)

    def get_graph_reasoning_context(self, application_name: str, product_family: str, material_code: str = None) -> dict:
        """Get complete reasoning context from the graph in a single query.

        This is an optimized method that retrieves all relevant information
        for reasoning in one database round-trip.

        Args:
            application_name: Application/environment name
            product_family: Product family code
            material_code: Optional requested material

        Returns:
            Dict with application info, material requirements, vulnerabilities, and mitigations
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    // Get application details
                    OPTIONAL MATCH (app:Application {name: $app_name})

                    // Get material requirements for the application
                    OPTIONAL MATCH (app)-[rm:REQUIRES_MATERIAL]->(req_mat:Material)
                    WITH app, collect(DISTINCT {
                        code: req_mat.code,
                        name: req_mat.full_name,
                        corrosion_class: req_mat.corrosion_class,
                        reason: rm.reason
                    }) AS material_requirements

                    // Get risks generated by the application
                    OPTIONAL MATCH (app)-[gr:GENERATES]->(risk:Risk)
                    WITH app, material_requirements, collect(DISTINCT {
                        name: risk.name,
                        description: risk.description,
                        severity: risk.severity
                    }) AS generated_risks

                    // Get product vulnerabilities
                    OPTIONAL MATCH (pv:ProductVariant)-[vt:VULNERABLE_TO]->(vuln_risk:Risk)
                    WHERE pv.family = $family
                    WITH app, material_requirements, generated_risks, collect(DISTINCT {
                        risk: vuln_risk.name,
                        consequence: vt.consequence,
                        mitigation: vt.mitigation
                    }) AS vulnerabilities

                    // Get products that mitigate risks
                    OPTIONAL MATCH (mit_pv:ProductVariant)-[mit:MITIGATES]->(mit_risk:Risk)
                    WHERE mit_risk.name IN [r IN generated_risks | r.name]
                    WITH app, material_requirements, generated_risks, vulnerabilities,
                         collect(DISTINCT {
                             product_family: mit_pv.family,
                             risk: mit_risk.name,
                             mechanism: mit.mechanism
                         }) AS mitigations

                    // Check if requested material is suitable
                    WITH app, material_requirements, generated_risks, vulnerabilities, mitigations,
                         CASE WHEN $material IS NOT NULL
                              THEN ANY(m IN material_requirements WHERE m.code = $material)
                              ELSE null END AS material_is_suitable

                    RETURN {
                        application: {
                            name: app.name,
                            criticality: app.criticality,
                            concern: app.concern,
                            min_corrosion_class: app.min_corrosion_class
                        },
                        material_requirements: [m IN material_requirements WHERE m.code IS NOT NULL],
                        generated_risks: [r IN generated_risks WHERE r.name IS NOT NULL],
                        product_vulnerabilities: [v IN vulnerabilities WHERE v.risk IS NOT NULL],
                        available_mitigations: [m IN mitigations WHERE m.product_family IS NOT NULL],
                        requested_material: $material,
                        material_suitable: material_is_suitable
                    } AS context
                """, app_name=application_name, family=product_family, material=material_code)
                record = result.single()
                return record["context"] if record else {}

        return self._execute_with_retry(_query)

    def get_product_family_data_dump(self, product_family: str) -> dict:
        """THE BIG DATA DUMP: Fetch EVERYTHING related to a product family.

        This method retrieves all variants, materials, maintenance rules, and
        constraints for a product family in one comprehensive query. The result
        is meant to be injected directly into the LLM context as GRAPH_DATA.

        This approach moves intelligence FROM Python state management TO the LLM:
        - LLM has ALL the data it needs in context
        - No more guessing weights or codes
        - Ground truth for product selection

        Args:
            product_family: Product family code (e.g., 'GDB', 'GDMI', 'GDC', 'GDP')

        Returns:
            Dict with complete product family data:
            {
                "family": "GDB",
                "variants": [
                    {
                        "id": "GDB-300x600-550",
                        "width_mm": 300,
                        "height_mm": 600,
                        "length_mm": 550,
                        "weight_kg": 20,
                        "airflow_m3h": 2500,
                        "available_materials": ["FZ", "ZM", "RF", "SF"]
                    },
                    ...
                ],
                "materials": [
                    {"code": "FZ", "name": "Galvanized", "corrosion_class": "C3"},
                    {"code": "RF", "name": "Stainless Steel", "corrosion_class": "C5"},
                    ...
                ],
                "maintenance_rules": [
                    {"condition": "Hospital", "restriction": "No Zinc (FZ/ZM)", "required": ["RF", "SF"]},
                    ...
                ],
                "sizing_reference": {
                    "300x300": 850,
                    "300x600": 2500,
                    "600x600": 3400,
                    ...
                }
            }
        """
        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                # Query 1: Get all variants for this product family (v4.0: HAS_VARIANT path)
                pf_id = f"FAM_{product_family}" if not product_family.startswith("FAM_") else product_family
                variants_result = session.run("""
                    MATCH (pf:ProductFamily {id: $pf_id})-[:HAS_VARIANT]->(pv:ProductVariant)
                    RETURN pv.name AS id,
                           pv.product_family AS family,
                           pv.width_mm AS width_mm,
                           pv.height_mm AS height_mm,
                           pv.housing_length_mm AS length_mm,
                           pv.housing_length_short_mm AS length_short_mm,
                           pv.housing_length_long_mm AS length_long_mm,
                           COALESCE(pv.weight_kg, pv.weight_kg_short) AS weight_kg,
                           pv.weight_kg_short AS weight_kg_short,
                           pv.weight_kg_long AS weight_kg_long,
                           pv.reference_airflow_m3h AS airflow_m3h,
                           pv.cartridge_count AS cartridge_count
                    ORDER BY pv.width_mm, pv.height_mm
                """, pf_id=pf_id)
                variants = [dict(r) for r in variants_result]

                # Query 2: Get all materials
                materials_result = session.run("""
                    MATCH (ms:MaterialSpecification)
                    RETURN ms.code AS code,
                           ms.full_name AS name,
                           ms.corrosion_class AS corrosion_class,
                           ms.description AS description
                    ORDER BY ms.corrosion_class DESC
                """)
                materials = [dict(r) for r in materials_result]

                # Query 3: Get material restrictions by application/environment
                restrictions_result = session.run("""
                    MATCH (app:Application)-[:REQUIRES_MATERIAL]->(mat:Material)
                    RETURN app.name AS environment,
                           collect(DISTINCT mat.code) AS required_materials,
                           app.concern AS reason
                """)
                restrictions = [dict(r) for r in restrictions_result]

                # Query 4: Get product vulnerabilities
                vulnerabilities_result = session.run("""
                    MATCH (pv:ProductVariant)-[v:VULNERABLE_TO]->(risk:Risk)
                    WHERE pv.family = $family
                    RETURN pv.family AS product,
                           risk.name AS risk,
                           v.consequence AS consequence,
                           v.mitigation AS mitigation
                """, family=product_family)
                vulnerabilities = [dict(r) for r in vulnerabilities_result]

                # Query 5: Get insulation requirements (for outdoor/condensation risks)
                insulation_result = session.run("""
                    MATCH (env:Environment)-[:CAUSES]->(risk:Risk)-[:MITIGATED_BY]->(feat:Feature)
                    OPTIONAL MATCH (pf:ProductFamily)-[:HAS_FEATURE]->(feat)
                    RETURN env.name AS environment,
                           risk.name AS risk,
                           feat.name AS required_feature,
                           collect(DISTINCT pf.id) AS products_with_feature
                """)
                insulation_rules = [dict(r) for r in insulation_result]

                # Build sizing reference from variants (v4.0: uses reference_airflow_m3h)
                sizing_reference = {}
                for v in variants:
                    if v.get('width_mm') and v.get('height_mm'):
                        size_key = f"{v['width_mm']}x{v['height_mm']}"
                        if v.get('airflow_m3h') and size_key not in sizing_reference:
                            sizing_reference[size_key] = v['airflow_m3h']

                # Build weight lookup table (v4.0: supports both single and dual-length weights)
                weight_table = {}
                for v in variants:
                    if not (v.get('width_mm') and v.get('height_mm')):
                        continue
                    size = f"{v['width_mm']}x{v['height_mm']}"
                    # Single-length products (e.g., GDP with length_mm=250)
                    if v.get('weight_kg') and v.get('length_mm'):
                        weight_table[f"{size}x{v['length_mm']}"] = v['weight_kg']
                    # Dual-length products (e.g., GDB with short/long)
                    if v.get('weight_kg_short') and v.get('length_short_mm'):
                        weight_table[f"{size}x{v['length_short_mm']}"] = v['weight_kg_short']
                    if v.get('weight_kg_long') and v.get('length_long_mm'):
                        weight_table[f"{size}x{v['length_long_mm']}"] = v['weight_kg_long']

                # Query 6: Get ProductFamily metadata (corrosion, indoor_only, description)
                pf_result = session.run("""
                    MATCH (pf:ProductFamily {id: $pf_id})
                    RETURN pf.corrosion_class AS housing_corrosion_class,
                           pf.indoor_only AS indoor_only,
                           pf.outdoor_safe AS outdoor_safe,
                           pf.allowed_environments AS allowed_environments,
                           pf.description AS description,
                           pf.media_type AS media_type,
                           pf.filter_type AS filter_type,
                           pf.construction_type AS construction_type
                """, pf_id=pf_id)
                pf_meta = dict(pf_result.single()) if pf_result.peek() else {}

                return {
                    "family": product_family,
                    "description": pf_meta.get("description"),
                    "media_type": pf_meta.get("media_type"),
                    "filter_type": pf_meta.get("filter_type"),
                    "construction_type": pf_meta.get("construction_type"),
                    "housing_corrosion_class": pf_meta.get("housing_corrosion_class"),
                    "indoor_only": pf_meta.get("indoor_only", False),
                    "outdoor_safe": pf_meta.get("outdoor_safe", False),
                    "variants": variants,
                    "materials": materials,
                    "environment_restrictions": restrictions,
                    "product_vulnerabilities": vulnerabilities,
                    "insulation_rules": insulation_rules,
                    "sizing_reference_m3h": sizing_reference,
                    "weight_table_kg": weight_table,
                    "_meta": {
                        "total_variants": len(variants),
                        "total_materials": len(materials),
                        "source": "Neo4j Knowledge Graph v4.0"
                    }
                }

        return self._execute_with_retry(_query)

    def get_full_conversation_context(self, product_family: str, application_name: str = None) -> dict:
        """Build complete context for LLM-driven reasoning.

        Combines product data dump with application-specific constraints.
        This is the single source of truth for the LLM.

        Args:
            product_family: Product family code
            application_name: Optional detected application/environment

        Returns:
            Complete context dict for LLM injection
        """
        # Get the big data dump for the product family
        product_data = self.get_product_family_data_dump(product_family) if product_family else {}

        # If application is detected, get additional constraints
        app_context = {}
        if application_name:
            app_result = self.get_graph_reasoning_context(
                application_name=application_name,
                product_family=product_family or "GDB"
            )
            app_context = app_result if app_result else {}

        return {
            "product_catalog": product_data,
            "application_context": app_context,
            "_instructions": {
                "weights": "Use weight_table_kg for EXACT weights. Never estimate.",
                "materials": "Respect environment_restrictions. Hospital = RF/SF only.",
                "sizing": "Use sizing_reference_m3h for airflow-to-size mapping.",
                "corrosion": (
                    "Valid corrosion classes: C1, C2, C3, C4, C5, C5.1 ONLY. "
                    "There is NO class called C5-M. "
                    "housing_corrosion_class is the corrosion rating of the HOUSING itself. "
                    "Material corrosion_class is the rating of each material option. "
                    "Always mention both when discussing corrosion suitability."
                ),
                "indoor_only": (
                    "If indoor_only=true, the product is designed for indoor use only. "
                    "Explicitly warn if the user's environment is outdoor, rooftop, or marine."
                ),
            }
        }


    # =========================================================================
    # LAYER 4: SESSION GRAPH METHODS
    # =========================================================================

    def get_session_graph_manager(self):
        """Get a SessionGraphManager instance using this connection.

        Lazy import to avoid circular dependencies.
        """
        from logic.session_graph import SessionGraphManager
        self.connect()
        return SessionGraphManager(self)

    def init_session_schema(self):
        """Initialize Layer 4 session schema constraints and indexes."""
        schema_statements = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (ap:ActiveProject) REQUIRE ap.id IS UNIQUE",
            "CREATE INDEX session_last_active IF NOT EXISTS FOR (s:Session) ON (s.last_active)",
            "CREATE INDEX tagunit_session IF NOT EXISTS FOR (t:TagUnit) ON (t.session_id)",
            "CREATE INDEX activeproject_session IF NOT EXISTS FOR (ap:ActiveProject) ON (ap.session_id)",
            # Expert review
            "CREATE CONSTRAINT IF NOT EXISTS FOR (er:ExpertReview) REQUIRE er.id IS UNIQUE",
            "CREATE INDEX expert_review_session IF NOT EXISTS FOR (er:ExpertReview) ON (er.session_id)",
        ]
        driver = self.connect()
        with driver.session(database=self.database) as session:
            for stmt in schema_statements:
                try:
                    session.run(stmt)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"⚠ Session schema statement failed: {e}")
        print("✓ Layer 4 session schema initialized")

    # =========================================================================
    # EXPERT REVIEW QUERIES
    # =========================================================================

    def get_expert_conversations(self, limit: int = 50, offset: int = 0) -> dict:
        """List all conversations with turn counts and review status."""
        driver = self.connect()
        with driver.session(database=self.database) as session:
            # Count total
            total_result = session.run("""
                MATCH (p:ActiveProject)
                WHERE EXISTS { (p)-[:HAS_TURN]->(:ConversationTurn) }
                RETURN count(p) AS total
            """)
            total = total_result.single()["total"]

            # Paginated list
            result = session.run("""
                MATCH (p:ActiveProject)
                WHERE EXISTS { (p)-[:HAS_TURN]->(:ConversationTurn) }
                OPTIONAL MATCH (p)-[:HAS_TURN]->(ct:ConversationTurn)
                OPTIONAL MATCH (p)-[:HAS_REVIEW]->(er:ExpertReview)
                WITH p,
                     count(DISTINCT ct) AS turn_count,
                     max(ct.created_at) AS last_activity,
                     count(DISTINCT er) > 0 AS has_review,
                     head(collect(DISTINCT er.overall_score)) AS review_score
                RETURN p.session_id AS session_id,
                       p.name AS project_name,
                       p.detected_family AS detected_family,
                       p.locked_material AS locked_material,
                       turn_count,
                       last_activity,
                       has_review,
                       review_score
                ORDER BY last_activity DESC
                SKIP $offset LIMIT $limit
            """, limit=limit, offset=offset)
            conversations = [dict(r) for r in result]
            return {"conversations": conversations, "total": total}

    def get_conversation_detail(self, session_id: str) -> dict:
        """Get full conversation turns + expert reviews for a session."""
        driver = self.connect()
        with driver.session(database=self.database) as session:
            # Project metadata
            proj_result = session.run("""
                MATCH (p:ActiveProject {session_id: $sid})
                RETURN p.session_id AS session_id,
                       p.name AS project_name,
                       p.detected_family AS detected_family,
                       p.locked_material AS locked_material,
                       p.resolved_params AS resolved_params
            """, sid=session_id)
            proj = dict(proj_result.single()) if proj_result.peek() else {
                "session_id": session_id, "project_name": None,
                "detected_family": None, "locked_material": None, "resolved_params": None
            }

            # Conversation turns (include judge_results if saved)
            turns_result = session.run("""
                MATCH (p:ActiveProject {session_id: $sid})-[:HAS_TURN]->(ct:ConversationTurn)
                RETURN ct.id AS id, ct.role AS role, ct.message AS message,
                       ct.turn_number AS turn_number, ct.created_at AS created_at,
                       ct.judge_results AS judge_results
                ORDER BY ct.turn_number ASC
            """, sid=session_id)
            turns = [dict(r) for r in turns_result]

            # Expert reviews (include provider + turn_number for per-judge reviews)
            reviews_result = session.run("""
                MATCH (p:ActiveProject {session_id: $sid})-[:HAS_REVIEW]->(er:ExpertReview)
                RETURN er.id AS id, er.reviewer AS reviewer, er.comment AS comment,
                       er.overall_score AS overall_score,
                       er.dimension_scores AS dimension_scores,
                       er.provider AS provider,
                       er.turn_number AS turn_number,
                       er.created_at AS created_at
                ORDER BY er.created_at DESC
            """, sid=session_id)
            reviews = [dict(r) for r in reviews_result]

            return {**proj, "turns": turns, "reviews": reviews}

    def save_judge_results(self, session_id: str, turn_number: int,
                           judge_results: str) -> bool:
        """Save judge results JSON on an assistant ConversationTurn node."""
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:ActiveProject {session_id: $sid})-[:HAS_TURN]->(ct:ConversationTurn)
                WHERE ct.role = 'assistant' AND ct.turn_number = $tn
                SET ct.judge_results = $jr
                RETURN ct.id AS id
            """, sid=session_id, tn=turn_number, jr=judge_results)
            return result.single() is not None

    def submit_expert_review(self, session_id: str, reviewer: str,
                             comment: str, overall_score: str,
                             dimension_scores: str = None,
                             provider: str = None,
                             turn_number: int = None) -> dict:
        """Create an ExpertReview node linked to the conversation's ActiveProject.
        If provider is set, this is a per-judge review (e.g. 'gemini', 'openai', 'anthropic').
        """
        import time
        suffix = f"_{provider}" if provider else ""
        review_id = f"REVIEW_{session_id}_{reviewer}_{int(time.time())}{suffix}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (p:ActiveProject {session_id: $session_id})
                CREATE (p)-[:HAS_REVIEW]->(er:ExpertReview {
                    id: $review_id,
                    session_id: $session_id,
                    reviewer: $reviewer,
                    comment: $comment,
                    overall_score: $overall_score,
                    dimension_scores: $dimension_scores,
                    provider: $provider,
                    turn_number: $turn_number,
                    created_at: timestamp()
                })
                RETURN er {.*} AS review
            """, session_id=session_id, review_id=review_id,
                 reviewer=reviewer, comment=comment,
                 overall_score=overall_score,
                 dimension_scores=dimension_scores,
                 provider=provider, turn_number=turn_number)
            record = result.single()
            return dict(record["review"]) if record else {}

    def get_expert_reviews_summary(self) -> dict:
        """Get aggregate stats for expert reviews."""
        driver = self.connect()
        with driver.session(database=self.database) as session:
            stats_result = session.run("""
                MATCH (er:ExpertReview)
                WITH count(er) AS total,
                     count(CASE WHEN er.overall_score = 'thumbs_up' THEN 1 END) AS positive,
                     count(CASE WHEN er.overall_score = 'thumbs_down' THEN 1 END) AS negative
                RETURN total, positive, negative
            """)
            stats = dict(stats_result.single()) if stats_result.peek() else {
                "total": 0, "positive": 0, "negative": 0
            }

            recent_result = session.run("""
                MATCH (er:ExpertReview)
                OPTIONAL MATCH (p:ActiveProject {session_id: er.session_id})
                RETURN er.id AS id, er.session_id AS session_id,
                       er.reviewer AS reviewer, er.comment AS comment,
                       er.overall_score AS overall_score,
                       er.created_at AS created_at,
                       p.detected_family AS detected_family
                ORDER BY er.created_at DESC
                LIMIT 20
            """)
            recent = [dict(r) for r in recent_result]

            return {**stats, "recent": recent}

    # =========================================================================
    # TRAIT-BASED REASONING QUERIES (Layer 2.5: Trait Engine)
    # =========================================================================

    def get_stressors_by_keywords(self, keywords: list[str]) -> list[dict]:
        """Find EnvironmentalStressor nodes matching query keywords.

        Args:
            keywords: List of lowercase keywords from user query

        Returns:
            List of stressor dicts with id, name, description, matched_keyword
        """
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (s:EnvironmentalStressor)
                WHERE s.keywords IS NOT NULL
                WITH s, [kw IN s.keywords WHERE ANY(qkw IN $keywords WHERE
                    toLower(qkw) = toLower(kw)
                    OR (size(kw) >= 3 AND toLower(qkw) STARTS WITH toLower(kw))
                )] AS matched
                WHERE size(matched) > 0
                RETURN s.id AS id,
                       s.name AS name,
                       s.description AS description,
                       s.category AS category,
                       matched AS matched_keywords,
                       size(matched) AS match_count
                ORDER BY match_count DESC
            """, {"keywords": keywords})
            return [dict(record) for record in result]

    def get_stressors_for_application(self, app_id: str) -> list[dict]:
        """Get stressors linked to an application/environment via EXPOSES_TO.

        Traverses IS_A hierarchy so child environments inherit parent stressors.
        E.g., ENV_KITCHEN IS_A ENV_INDOOR → returns stressors from both.

        Args:
            app_id: Application or Environment node ID

        Returns:
            List of stressor dicts (deduplicated by stressor ID)
        """
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (ctx {id: $app_id})
                OPTIONAL MATCH (ctx)-[:IS_A*0..5]->(parent)
                WITH collect(DISTINCT ctx) + collect(DISTINCT parent) AS contexts
                UNWIND contexts AS c
                MATCH (c)-[:EXPOSES_TO]->(s:EnvironmentalStressor)
                RETURN DISTINCT s.id AS id,
                       s.name AS name,
                       s.description AS description,
                       s.category AS category,
                       c.name AS source_context,
                       labels(c)[0] AS source_type
            """, {"app_id": app_id})
            return [dict(record) for record in result]

    def resolve_environment_hierarchy(self, env_id: str) -> list[str]:
        """Resolve an environment ID to itself + all IS_A parents.

        E.g., ENV_KITCHEN → [ENV_KITCHEN, ENV_INDOOR]
        Used by constraint checking: if product allows ENV_INDOOR,
        it also allows ENV_KITCHEN (child environment).
        """
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (env:Environment {id: $env_id})
                OPTIONAL MATCH (env)-[:IS_A*0..5]->(parent:Environment)
                RETURN collect(DISTINCT env.id) + collect(DISTINCT parent.id) AS env_chain
            """, {"env_id": env_id})
            record = result.single()
            if record and record["env_chain"]:
                return list(dict.fromkeys(record["env_chain"]))
            return [env_id]

    def get_environment_keywords(self) -> dict[str, list[str]]:
        """Read environment keywords from graph.

        Replaces hardcoded env_keywords dict in engine.
        Each Environment node has a 'keywords' property.
        """
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (env:Environment)
                WHERE env.keywords IS NOT NULL
                RETURN env.id AS env_id, env.keywords AS keywords
            """)
            return {r["env_id"]: r["keywords"] for r in result}

    def get_causal_rules_for_stressors(self, stressor_ids: list[str]) -> list[dict]:
        """Get all causal rules (NEUTRALIZED_BY, DEMANDS_TRAIT) for given stressors.

        Args:
            stressor_ids: List of EnvironmentalStressor IDs

        Returns:
            List of rule dicts with rule_type, trait_id/name, stressor_id/name, severity, explanation
        """
        if not stressor_ids:
            return []
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (t:PhysicalTrait)-[r:NEUTRALIZED_BY]->(s:EnvironmentalStressor)
                WHERE s.id IN $stressor_ids
                RETURN 'NEUTRALIZED_BY' AS rule_type,
                       t.id AS trait_id, t.name AS trait_name,
                       s.id AS stressor_id, s.name AS stressor_name,
                       r.severity AS severity,
                       r.explanation AS explanation
                UNION ALL
                MATCH (s:EnvironmentalStressor)-[r:DEMANDS_TRAIT]->(t:PhysicalTrait)
                WHERE s.id IN $stressor_ids
                RETURN 'DEMANDS_TRAIT' AS rule_type,
                       t.id AS trait_id, t.name AS trait_name,
                       s.id AS stressor_id, s.name AS stressor_name,
                       r.severity AS severity,
                       r.explanation AS explanation
            """, {"stressor_ids": stressor_ids})
            return [dict(record) for record in result]

    def get_product_traits(self, product_family: str) -> list[dict]:
        """Get all PhysicalTraits for a product family (direct + via material).

        Args:
            product_family: Product family code (e.g., 'GDB') or full ID (e.g., 'FAM_GDB')

        Returns:
            List of trait dicts with id, name, source ('direct' or material code), primary flag
        """
        pf_id = product_family if product_family.startswith("FAM_") else f"FAM_{product_family.upper()}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pf:ProductFamily {id: $pf_id})-[r:HAS_TRAIT]->(t:PhysicalTrait)
                RETURN t.id AS id, t.name AS name, 'direct' AS source, r.primary AS is_primary
                UNION
                MATCH (pf:ProductFamily {id: $pf_id})-[:AVAILABLE_IN_MATERIAL]->(m:Material)-[:PROVIDES_TRAIT]->(t:PhysicalTrait)
                RETURN DISTINCT t.id AS id, t.name AS name, m.code AS source, false AS is_primary
            """, {"pf_id": pf_id})
            return [dict(record) for record in result]

    def get_all_product_families_with_traits(self) -> list[dict]:
        """Batch query: all product families with their trait sets.

        Returns:
            List of dicts with product_id, product_name, product_type,
            direct_trait_ids, material_trait_ids, all_trait_ids
        """
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pf:ProductFamily)
                OPTIONAL MATCH (pf)-[:HAS_TRAIT]->(dt:PhysicalTrait)
                OPTIONAL MATCH (pf)-[:AVAILABLE_IN_MATERIAL]->(m:Material)-[:PROVIDES_TRAIT]->(mt:PhysicalTrait)
                WITH pf,
                     collect(DISTINCT dt.id) AS direct_trait_ids,
                     collect(DISTINCT dt.name) AS direct_trait_names,
                     collect(DISTINCT mt.id) AS material_trait_ids,
                     collect(DISTINCT mt.name) AS material_trait_names
                RETURN pf.id AS product_id,
                       pf.name AS product_name,
                       pf.type AS product_type,
                       pf.selection_priority AS selection_priority,
                       direct_trait_ids,
                       direct_trait_names,
                       material_trait_ids,
                       material_trait_names,
                       direct_trait_ids + [x IN material_trait_ids WHERE NOT x IN direct_trait_ids] AS all_trait_ids
                ORDER BY pf.selection_priority ASC
            """)
            return [dict(record) for record in result]


    def get_goals_by_keywords(self, keywords: list[str]) -> list[dict]:
        """Find FunctionalGoal nodes matching query keywords.

        Args:
            keywords: List of lowercase keywords from user query

        Returns:
            List of goal dicts with id, name, description, required_trait_id, required_trait_name
        """
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (g:FunctionalGoal)-[:REQUIRES_TRAIT]->(t:PhysicalTrait)
                WHERE g.keywords IS NOT NULL
                WITH g, t, [kw IN g.keywords WHERE ANY(qkw IN $keywords WHERE toLower(qkw) = toLower(kw))] AS matched
                WHERE size(matched) > 0
                RETURN g.id AS id,
                       g.name AS name,
                       g.description AS description,
                       t.id AS required_trait_id,
                       t.name AS required_trait_name,
                       matched AS matched_keywords,
                       size(matched) AS match_count
                ORDER BY match_count DESC
            """, {"keywords": keywords})
            return [dict(record) for record in result]


    # =========================================================================
    # v2.0 — Logic Gates, Hard Constraints, Dependencies, Strategy, Capacity
    # =========================================================================

    def get_logic_gates_for_stressors(self, stressor_ids: list[str]) -> list[dict]:
        """Get LogicGate nodes that MONITOR any of the given stressors, with REQUIRES_DATA parameters.

        Args:
            stressor_ids: List of EnvironmentalStressor IDs

        Returns:
            List of gate dicts with gate_id, gate_name, condition_logic, physics_explanation,
            stressor_id, stressor_name, and params list [{param_id, name, property_key, priority, question, unit}]
        """
        if not stressor_ids:
            return []
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (g:LogicGate)-[:MONITORS]->(s:EnvironmentalStressor)
                WHERE s.id IN $stressor_ids
                OPTIONAL MATCH (g)-[:REQUIRES_DATA]->(p:Parameter)
                WITH g, s, collect({
                    param_id: p.id,
                    name: p.name,
                    property_key: p.property_key,
                    priority: p.priority,
                    question: p.question,
                    unit: p.unit
                }) AS params
                RETURN g.id AS gate_id,
                       g.name AS gate_name,
                       g.condition_logic AS condition_logic,
                       g.physics_explanation AS physics_explanation,
                       s.id AS stressor_id,
                       s.name AS stressor_name,
                       params
                ORDER BY g.id
            """, {"stressor_ids": stressor_ids})
            return [dict(record) for record in result]

    def get_gates_triggered_by_context(self, context_ids: list[str]) -> list[dict]:
        """Get LogicGate nodes triggered by Application/Environment contexts.

        Args:
            context_ids: List of Application or Environment IDs (e.g., ['ENV_OUTDOOR', 'APP_KITCHEN'])

        Returns:
            List of gate dicts with gate_id, gate_name, condition_logic, physics_explanation,
            stressor_id, stressor_name, context_id, and params list
        """
        if not context_ids:
            return []
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (ctx)-[:TRIGGERS_GATE]->(g:LogicGate)-[:MONITORS]->(s:EnvironmentalStressor)
                WHERE ctx.id IN $context_ids
                OPTIONAL MATCH (g)-[:REQUIRES_DATA]->(p:Parameter)
                WITH ctx, g, s, collect({
                    param_id: p.id,
                    name: p.name,
                    property_key: p.property_key,
                    priority: p.priority,
                    question: p.question,
                    unit: p.unit
                }) AS params
                RETURN g.id AS gate_id,
                       g.name AS gate_name,
                       g.condition_logic AS condition_logic,
                       g.physics_explanation AS physics_explanation,
                       s.id AS stressor_id,
                       s.name AS stressor_name,
                       ctx.id AS context_id,
                       params
                ORDER BY g.id
            """, {"context_ids": context_ids})
            return [dict(record) for record in result]

    def get_hard_constraints(self, item_id: str) -> list[dict]:
        """Get HardConstraint nodes for a product family.

        Args:
            item_id: ProductFamily ID (e.g., 'FAM_GDC') or short form ('GDC')

        Returns:
            List of constraint dicts with id, property_key, operator, value, error_msg
        """
        pf_id = item_id if item_id.startswith("FAM_") else f"FAM_{item_id.upper()}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pf:ProductFamily {id: $pf_id})-[:HAS_HARD_CONSTRAINT]->(hc:HardConstraint)
                RETURN hc.id AS id,
                       hc.property_key AS property_key,
                       hc.operator AS operator,
                       hc.value AS value,
                       hc.error_msg AS error_msg
            """, {"pf_id": pf_id})
            return [dict(record) for record in result]

    def get_installation_constraints(self, item_id: str) -> list[dict]:
        """Get InstallationConstraint nodes for a product family.

        Returns constraint dicts with all IC properties plus relevant
        ProductFamily properties (service_access_factor, allowed_environments, etc).
        """
        pf_id = item_id if item_id.startswith("FAM_") else f"FAM_{item_id.upper()}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pf:ProductFamily {id: $pf_id})-[:HAS_INSTALLATION_CONSTRAINT]->(ic:InstallationConstraint)
                RETURN ic.id AS id,
                       ic.constraint_type AS constraint_type,
                       ic.dimension_key AS dimension_key,
                       ic.factor_property AS factor_property,
                       ic.comparison_key AS comparison_key,
                       ic.list_property AS list_property,
                       ic.input_key AS input_key,
                       ic.cross_property AS cross_property,
                       ic.material_context_key AS material_context_key,
                       ic.context_match_key AS context_match_key,
                       ic.cross_rel_type AS cross_rel_type,
                       ic.cross_node_match_property AS cross_node_match_property,
                       ic.operator AS operator,
                       ic.severity AS severity,
                       ic.error_msg AS error_msg,
                       pf.service_access_factor AS service_access_factor,
                       pf.service_access_type AS service_access_type,
                       pf.service_warning AS service_warning,
                       pf.allowed_environments AS allowed_environments,
                       pf.construction_type AS construction_type,
                       ic.valid_set AS valid_set
            """, {"pf_id": pf_id})
            return [dict(record) for record in result]

    def get_material_property(self, item_id: str, material_code: str, property_name: str):
        """Get a single property from a Material node linked to a ProductFamily.

        Returns the property value or None if not found.
        """
        pf_id = item_id if item_id.startswith("FAM_") else f"FAM_{item_id.upper()}"
        mat_id = material_code if material_code.startswith("MAT_") else f"MAT_{material_code.upper()}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pf:ProductFamily {id: $pf_id})-[:AVAILABLE_IN_MATERIAL]->(m:Material {id: $mat_id})
                RETURN m[$property_name] AS value
            """, {"pf_id": pf_id, "mat_id": mat_id, "property_name": property_name})
            record = result.single()
            return record["value"] if record else None

    def get_related_node_property(self, pf_id: str, rel_type: str,
                                   match_prop: str, match_val,
                                   target_prop: str):
        """Look up a property on a node related to ProductFamily via specified relationship.

        Generic: works for any node type (VariantLength, SizeProperty, etc.).
        Property names come from graph IC metadata (trusted, not user input).
        """
        pf_id = pf_id if pf_id.startswith("FAM_") else f"FAM_{pf_id.upper()}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run(f"""
                MATCH (pf:ProductFamily {{id: $pf_id}})-[:{rel_type}]->(node)
                WHERE node.{match_prop} = $match_val
                RETURN node.{target_prop} AS value
                LIMIT 1
            """, {"pf_id": pf_id, "match_val": match_val})
            record = result.single()
            return record["value"] if record else None

    def find_compatible_variants(self, pf_id: str, rel_type: str,
                                  match_prop: str, threshold_prop: str,
                                  min_threshold: float):
        """Find related nodes where threshold_prop >= min_threshold.

        Used by installation constraint evaluator to suggest compatible
        variant alternatives (e.g. longer housing that fits a given depth).
        """
        pf_id = pf_id if pf_id.startswith("FAM_") else f"FAM_{pf_id.upper()}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run(f"""
                MATCH (pf:ProductFamily {{id: $pf_id}})-[:{rel_type}]->(node)
                WHERE node.{threshold_prop} >= $min_threshold
                RETURN node.{match_prop} AS variant_value,
                       node.{threshold_prop} AS threshold
                ORDER BY node.{match_prop} ASC
            """, {"pf_id": pf_id, "min_threshold": min_threshold})
            return [dict(r) for r in result]

    def get_application_properties(self, app_id: str) -> dict:
        """Get properties from an Application node (e.g. typical_chlorine_ppm).

        Returns dict of application properties or empty dict if not found.
        """
        full_id = app_id if app_id.startswith("APP_") else f"APP_{app_id.upper()}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (a:Application {id: $app_id})
                RETURN a.typical_chlorine_ppm AS typical_chlorine_ppm
            """, {"app_id": full_id})
            record = result.single()
            return dict(record) if record else {}

    # =========================================================================
    # v3.3: Alternative product search for installation constraint violations
    # =========================================================================

    def find_alternatives_for_space_constraint(
        self,
        blocked_pf_id: str,
        dimension_key: str,
        available_space: float,
        dim_value: float,
        required_trait_ids: list[str] | None = None,
    ) -> list[dict]:
        """Find product families that fit within available space (COMPUTED_FORMULA).

        For each candidate, computes required = dim_value * (1 + service_access_factor).
        Returns only those where required <= available_space and the product has
        a DimensionModule matching the requested dimension.
        v3.5: Filters by required traits when provided (trait qualification).
        Ordered by selection_priority ASC (preferred first).
        """
        pf_id = blocked_pf_id if blocked_pf_id.startswith("FAM_") else f"FAM_{blocked_pf_id.upper()}"
        # Build dimension filter property name (safe: dimension_key from graph, not user)
        dm_prop = f"{dimension_key}_mm"
        trait_ids = required_trait_ids or []
        trait_count = len(trait_ids)
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run(f"""
                MATCH (pf:ProductFamily)
                WHERE pf.id <> $blocked_pf_id
                  AND pf.service_access_factor IS NOT NULL
                WITH pf, $dim_value * (1.0 + pf.service_access_factor) AS required_space
                WHERE required_space <= $available_space
                OPTIONAL MATCH (pf)-[:HAS_VARIANT]->(pv:ProductVariant)
                WHERE pv.{dm_prop} = toInteger($dim_value)
                WITH pf, required_space, count(pv) AS matching_sizes
                WHERE matching_sizes > 0
                // v3.5: Trait qualification — only return alternatives with required traits
                WITH pf, required_space
                OPTIONAL MATCH (pf)-[:HAS_TRAIT]->(t:PhysicalTrait)
                WHERE t.id IN $trait_ids
                WITH pf, required_space, count(t) AS matched_traits
                WHERE $trait_count = 0 OR matched_traits >= $trait_count
                RETURN pf.id AS product_id,
                       pf.name AS product_name,
                       pf.type AS product_type,
                       pf.selection_priority AS selection_priority,
                       pf.service_access_factor AS service_access_factor,
                       pf.service_access_type AS service_access_type,
                       required_space AS required_space_mm
                ORDER BY pf.selection_priority ASC
            """, {
                "blocked_pf_id": pf_id,
                "dim_value": dim_value,
                "available_space": available_space,
                "trait_ids": trait_ids,
                "trait_count": trait_count,
            })
            return [dict(record) for record in result]

    def find_alternatives_for_environment_constraint(
        self,
        blocked_pf_id: str,
        required_environment: str | None = None,
        required_trait_ids: list[str] | None = None,
        required_environments: list[str] | None = None,
    ) -> list[dict]:
        """Find product families whose allowed_environments include the target (SET_MEMBERSHIP).

        v3.6: Accepts either a single required_environment or a list (IS_A chain).
        When chain provided, matches if ANY env in chain is in allowed_environments.
        v3.5: Filters by required traits when provided (trait qualification).
        Ordered by selection_priority ASC.
        """
        pf_id = blocked_pf_id if blocked_pf_id.startswith("FAM_") else f"FAM_{blocked_pf_id.upper()}"
        trait_ids = required_trait_ids or []
        trait_count = len(trait_ids)
        # v3.6: Support env chain (IS_A hierarchy)
        env_chain = required_environments or ([required_environment.strip()] if required_environment else [])
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pf:ProductFamily)
                WHERE pf.id <> $blocked_pf_id
                  AND pf.allowed_environments IS NOT NULL
                  AND ANY(env IN $env_chain WHERE env IN pf.allowed_environments)
                // v3.5: Trait qualification
                WITH pf
                OPTIONAL MATCH (pf)-[:HAS_TRAIT]->(t:PhysicalTrait)
                WHERE t.id IN $trait_ids
                WITH pf, count(t) AS matched_traits
                WHERE $trait_count = 0 OR matched_traits >= $trait_count
                RETURN pf.id AS product_id,
                       pf.name AS product_name,
                       pf.type AS product_type,
                       pf.selection_priority AS selection_priority,
                       pf.allowed_environments AS allowed_environments
                ORDER BY pf.selection_priority ASC
            """, {
                "blocked_pf_id": pf_id,
                "env_chain": env_chain,
                "trait_ids": trait_ids,
                "trait_count": trait_count,
            })
            return [dict(record) for record in result]

    def find_material_alternatives_for_threshold(
        self,
        pf_id: str,
        cross_property: str,
        required_value: float,
    ) -> list[dict]:
        """Find materials on the SAME product that meet a threshold (CROSS_NODE_THRESHOLD).

        Returns materials where the cross_property value >= required_value.
        Ordered by threshold value DESC (best first).
        """
        full_pf_id = pf_id if pf_id.startswith("FAM_") else f"FAM_{pf_id.upper()}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run(f"""
                MATCH (pf:ProductFamily {{id: $pf_id}})-[:AVAILABLE_IN_MATERIAL]->(m:Material)
                WHERE m.{cross_property} IS NOT NULL
                  AND m.{cross_property} >= $required_value
                RETURN m.id AS material_id,
                       m.code AS material_code,
                       m.name AS material_name,
                       m.{cross_property} AS threshold_value
                ORDER BY m.{cross_property} DESC
            """, {
                "pf_id": full_pf_id,
                "required_value": required_value,
            })
            return [dict(record) for record in result]

    def find_other_products_for_material_threshold(
        self,
        blocked_pf_id: str,
        cross_property: str,
        required_value: float,
        required_trait_ids: list[str] | None = None,
    ) -> list[dict]:
        """Find OTHER product families that have materials meeting a threshold.

        Prong 2 of CROSS_NODE_THRESHOLD: when the blocked product has no material
        meeting the threshold, search other product families.
        Returns products with at least one qualifying material.
        v3.5: Filters by required traits when provided (trait qualification).
        Ordered by selection_priority ASC.
        """
        pf_id = blocked_pf_id if blocked_pf_id.startswith("FAM_") else f"FAM_{blocked_pf_id.upper()}"
        trait_ids = required_trait_ids or []
        trait_count = len(trait_ids)
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run(f"""
                MATCH (pf:ProductFamily)-[:AVAILABLE_IN_MATERIAL]->(m:Material)
                WHERE pf.id <> $blocked_pf_id
                  AND m.{cross_property} IS NOT NULL
                  AND m.{cross_property} >= $required_value
                WITH pf, collect({{
                    code: m.code,
                    name: m.name,
                    threshold: m.{cross_property}
                }}) AS qualifying_materials
                WHERE size(qualifying_materials) > 0
                // v3.5: Trait qualification
                OPTIONAL MATCH (pf)-[:HAS_TRAIT]->(t:PhysicalTrait)
                WHERE t.id IN $trait_ids
                WITH pf, qualifying_materials, count(t) AS matched_traits
                WHERE $trait_count = 0 OR matched_traits >= $trait_count
                RETURN pf.id AS product_id,
                       pf.name AS product_name,
                       pf.type AS product_type,
                       pf.selection_priority AS selection_priority,
                       qualifying_materials
                ORDER BY pf.selection_priority ASC
            """, {
                "blocked_pf_id": pf_id,
                "required_value": required_value,
                "trait_ids": trait_ids,
                "trait_count": trait_count,
            })
            return [dict(record) for record in result]

    def find_products_with_higher_capacity(
        self,
        blocked_pf_id: str,
        module_descriptor: str,
        min_output_rating: float,
        required_trait_ids: list[str] | None = None,
    ) -> list[dict]:
        """Find product families with higher CapacityRule output_rating for the same module size.

        Used by v3.4 Capacity Alternatives: when modules_needed > 1, find products
        that can handle the airflow in fewer modules.
        Returns products whose CapacityRule output_rating > min_output_rating.
        v3.5: Filters by required traits when provided (trait qualification).
        Ordered by selection_priority ASC (preferred first).
        """
        pf_id = blocked_pf_id if blocked_pf_id.startswith("FAM_") else f"FAM_{blocked_pf_id.upper()}"
        trait_ids = required_trait_ids or []
        trait_count = len(trait_ids)
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pf:ProductFamily)-[:HAS_CAPACITY]->(cr:CapacityRule)
                WHERE pf.id <> $blocked_pf_id
                  AND cr.module_descriptor = $module_descriptor
                  AND cr.output_rating > $min_output_rating
                // v3.5: Trait qualification
                WITH pf, cr
                OPTIONAL MATCH (pf)-[:HAS_TRAIT]->(t:PhysicalTrait)
                WHERE t.id IN $trait_ids
                WITH pf, cr, count(t) AS matched_traits
                WHERE $trait_count = 0 OR matched_traits >= $trait_count
                RETURN pf.id AS product_id,
                       pf.name AS product_name,
                       pf.selection_priority AS selection_priority,
                       cr.output_rating AS output_rating,
                       cr.description AS description
                ORDER BY pf.selection_priority ASC
            """, {
                "blocked_pf_id": pf_id,
                "module_descriptor": module_descriptor,
                "min_output_rating": min_output_rating,
                "trait_ids": trait_ids,
                "trait_count": trait_count,
            })
            return [dict(record) for record in result]

    def get_dependency_rules_for_stressors(self, stressor_ids: list[str]) -> list[dict]:
        """Get DependencyRule nodes triggered by given stressors.

        Args:
            stressor_ids: List of EnvironmentalStressor IDs

        Returns:
            List of rule dicts with id, dependency_type, description,
            upstream_trait_id/name, downstream_trait_id/name, stressor_id
        """
        if not stressor_ids:
            return []
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (dr:DependencyRule)-[:TRIGGERED_BY_STRESSOR]->(s:EnvironmentalStressor)
                WHERE s.id IN $stressor_ids
                MATCH (dr)-[:UPSTREAM_REQUIRES_TRAIT]->(ut:PhysicalTrait)
                MATCH (dr)-[:DOWNSTREAM_PROVIDES_TRAIT]->(dt:PhysicalTrait)
                RETURN dr.id AS id,
                       dr.dependency_type AS dependency_type,
                       dr.description AS description,
                       ut.id AS upstream_trait_id,
                       ut.name AS upstream_trait_name,
                       dt.id AS downstream_trait_id,
                       dt.name AS downstream_trait_name,
                       s.id AS stressor_id,
                       s.name AS stressor_name
            """, {"stressor_ids": stressor_ids})
            return [dict(record) for record in result]

    def get_optimization_strategy(self, item_id: str) -> dict | None:
        """Get optimization Strategy for a product family.

        Args:
            item_id: ProductFamily ID (e.g., 'FAM_GDC') or short form ('GDC')

        Returns:
            Strategy dict with id, name, sort_property, sort_order, description — or None
        """
        pf_id = item_id if item_id.startswith("FAM_") else f"FAM_{item_id.upper()}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pf:ProductFamily {id: $pf_id})-[:OPTIMIZATION_STRATEGY]->(s:Strategy)
                RETURN s.id AS id,
                       s.name AS name,
                       s.sort_property AS sort_property,
                       s.sort_order AS sort_order,
                       s.description AS description,
                       s.primary_axis AS primary_axis,
                       s.secondary_axis AS secondary_axis,
                       s.expansion_unit AS expansion_unit
                LIMIT 1
            """, {"pf_id": pf_id})
            record = result.single()
            return dict(record) if record else None

    def get_size_determined_properties(
        self, module_id: str, product_family_id: str
    ) -> list[dict]:
        """Get properties auto-determined by a size selection.

        v4.0: Checks ProductVariant first (for cartridge_count stored directly),
        then falls back to DimensionModule → SizeProperty path.

        Returns:
            List of dicts with key, value, display_name
        """
        pf_id = (
            product_family_id
            if product_family_id.startswith("FAM_")
            else f"FAM_{product_family_id.upper()}"
        )
        driver = self.connect()
        with driver.session(database=self.database) as session:
            # v4.0: Check ProductVariant directly for cartridge_count
            if module_id.startswith("PV_"):
                pv_result = session.run("""
                    MATCH (pv:ProductVariant {id: $module_id})
                    WHERE pv.cartridge_count IS NOT NULL
                    RETURN 'capacity_units' AS key,
                           pv.cartridge_count AS value,
                           'cartridges' AS display_name
                """, {"module_id": module_id})
                pv_props = [dict(r) for r in pv_result]
                if pv_props:
                    return pv_props

            # Legacy: DimensionModule → SizeProperty path
            result = session.run("""
                MATCH (dm:DimensionModule {id: $module_id})-[:DETERMINES_PROPERTY]->(sp:SizeProperty)
                WHERE sp.for_family = $pf_id OR sp.for_family IS NULL
                RETURN sp.key AS key,
                       sp.value AS value,
                       sp.display_name AS display_name
            """, {"module_id": module_id, "pf_id": pf_id})
            return [dict(record) for record in result]

    def get_capacity_rules(self, item_id: str) -> list[dict]:
        """Get CapacityRule nodes for a product family.

        Args:
            item_id: ProductFamily ID (e.g., 'FAM_GDC') or short form ('GDC')

        Returns:
            List of capacity rule dicts with id, module_descriptor, input_requirement,
            output_rating, assumption, description
        """
        pf_id = item_id if item_id.startswith("FAM_") else f"FAM_{item_id.upper()}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pf:ProductFamily {id: $pf_id})-[:HAS_CAPACITY]->(cr:CapacityRule)
                RETURN cr.id AS id,
                       cr.module_descriptor AS module_descriptor,
                       cr.input_requirement AS input_requirement,
                       cr.output_rating AS output_rating,
                       cr.assumption AS assumption,
                       cr.description AS description,
                       cr.capacity_per_component AS capacity_per_component,
                       cr.component_count_key AS component_count_key
            """, {"pf_id": pf_id})
            return [dict(record) for record in result]


    def get_available_dimension_modules(self, item_id: str) -> list[dict]:
        """Get all ProductVariant nodes available for a product family.

        v4.0: Queries ProductFamily -[:HAS_VARIANT]-> ProductVariant.
        Each family has its own correct airflow values from the PDF catalog,
        eliminating the GDB data contamination from shared DimensionModules.

        Args:
            item_id: ProductFamily ID (e.g., 'FAM_GDP') or short form ('GDP')

        Returns:
            List of dicts with id, width_mm, height_mm, reference_airflow_m3h, label
        """
        pf_id = item_id if item_id.startswith("FAM_") else f"FAM_{item_id.upper()}"
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (pf:ProductFamily {id: $pf_id})-[:HAS_VARIANT]->(pv:ProductVariant)
                RETURN pv.id AS id,
                       pv.width_mm AS width_mm,
                       pv.height_mm AS height_mm,
                       pv.reference_airflow_m3h AS reference_airflow_m3h,
                       pv.label AS label
                ORDER BY pv.reference_airflow_m3h DESC
            """, {"pf_id": pf_id})
            return [dict(record) for record in result]

    def validate_spatial_feasibility(
        self,
        pf_ids: list[str],
        airflow: float,
        max_width: int = 0,
        max_height: int = 0,
        explicit_width: int = 0,
        explicit_height: int = 0,
    ) -> list[dict]:
        """Batch-validate spatial feasibility for candidate product families.

        v3.5c: Given a list of candidate product family IDs, airflow requirement,
        and spatial constraints, return ONLY families whose optimal module
        arrangement physically fits. Uses UNWIND for batch processing.

        Parameters use 0 as "no constraint" sentinel.

        Returns:
            List of dicts with product_family_id, modules_needed,
            airflow_per_module, module_width, module_height, max_modules_fitting.
            Only families that PASS the spatial check are returned.
        """
        if not pf_ids or airflow <= 0:
            return []

        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                UNWIND $pf_ids AS pf_id
                MATCH (pf:ProductFamily {id: pf_id})-[:HAS_VARIANT]->(pv:ProductVariant)
                WHERE ($explicit_width = 0 OR pv.width_mm = $explicit_width)
                  AND ($explicit_height = 0 OR pv.height_mm = $explicit_height)
                  AND ($max_width = 0 OR pv.width_mm <= $max_width)
                  AND ($max_height = 0 OR pv.height_mm <= $max_height)

                WITH pf, pv, pv.reference_airflow_m3h AS effective_airflow

                ORDER BY effective_airflow DESC
                WITH pf, collect({w: pv.width_mm, h: pv.height_mm, af: effective_airflow})[0] AS best
                WHERE best.af IS NOT NULL AND best.af > 0

                WITH pf, best,
                     toInteger(ceil(toFloat($airflow) / best.af)) AS modules_needed

                WITH pf, best, modules_needed,
                     CASE WHEN $max_width > 0
                          THEN toInteger(floor(toFloat($max_width) / best.w))
                          ELSE modules_needed END AS max_horizontal,
                     CASE WHEN $max_height > 0
                          THEN toInteger(floor(toFloat($max_height) / best.h))
                          ELSE modules_needed END AS max_vertical

                WHERE modules_needed <= max_horizontal * max_vertical

                RETURN pf.id AS product_family_id,
                       modules_needed,
                       best.af AS airflow_per_module,
                       best.w AS module_width,
                       best.h AS module_height,
                       max_horizontal * max_vertical AS max_modules_fitting
                ORDER BY modules_needed ASC
            """, {
                "pf_ids": pf_ids,
                "airflow": airflow,
                "max_width": max_width,
                "max_height": max_height,
                "explicit_width": explicit_width,
                "explicit_height": explicit_height,
            })
            return [dict(record) for record in result]

    def get_all_accessory_codes(self) -> list[dict]:
        """Get all known accessory codes from the graph.

        Returns:
            List of dicts with code (from ID) and name for each Accessory node.
        """
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (a:Accessory)
                RETURN a.id AS id,
                       replace(a.id, 'ACC_', '') AS code,
                       a.name AS name
                ORDER BY a.id
            """)
            return [dict(record) for record in result]


    # ========================================
    # Knowledge Refinery: Graph Rules as Candidates
    # ========================================

    def get_graph_rules_as_candidates(self) -> list[dict]:
        """Get all graph rule nodes formatted as knowledge candidates for the Refinery UI.

        Queries across 6 rule types using UNION ALL:
        - Causal Rules (NEUTRALIZED_BY, DEMANDS_TRAIT)
        - Logic Gates
        - Hard Constraints
        - Dependency Rules
        - Capacity Rules

        Returns:
            List of candidate-shaped dicts matching the KnowledgeCandidate interface.
        """
        cache_key = "graph_rules_as_candidates"
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

        def _query():
            driver = self.connect()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    // Sub-query 1: Failure Modes (NEUTRALIZED_BY)
                    MATCH (t:PhysicalTrait)-[r:NEUTRALIZED_BY]->(s:EnvironmentalStressor)
                    OPTIONAL MATCH (pf:ProductFamily)-[:HAS_TRAIT]->(t)
                    WITH t, r, s, collect(DISTINCT pf.name) AS families
                    RETURN s.id + '_NEUTRALIZES_' + t.id AS id,
                           t.name + ' failure from ' + s.name AS raw_name,
                           'Failure Mode' AS type,
                           COALESCE(r.explanation, s.name + ' neutralizes ' + t.name) AS inference_logic,
                           'Severity: ' + COALESCE(r.severity, 'UNKNOWN') + ' | ' + s.name + ' neutralizes ' + t.name AS citation,
                           'pending' AS status, '' AS created_at,
                           families AS projects, [s.name] AS events, null AS verified_as

                    UNION ALL

                    // Sub-query 2: Engineering Requirements (DEMANDS_TRAIT)
                    MATCH (s:EnvironmentalStressor)-[r:DEMANDS_TRAIT]->(t:PhysicalTrait)
                    OPTIONAL MATCH (pf:ProductFamily)-[:HAS_TRAIT]->(t)
                    WITH t, r, s, collect(DISTINCT pf.name) AS families
                    RETURN s.id + '_DEMANDS_' + t.id AS id,
                           t.name + ' required against ' + s.name AS raw_name,
                           'Engineering Requirement' AS type,
                           COALESCE(r.explanation, s.name + ' demands ' + t.name) AS inference_logic,
                           'Severity: ' + COALESCE(r.severity, 'UNKNOWN') + ' | ' + s.name + ' demands ' + t.name AS citation,
                           'pending' AS status, '' AS created_at,
                           families AS projects, [s.name] AS events, null AS verified_as

                    UNION ALL

                    // Sub-query 3: Validation Checks (Logic Gates)
                    MATCH (g:LogicGate)-[:MONITORS]->(s:EnvironmentalStressor)
                    OPTIONAL MATCH (g)-[:REQUIRES_DATA]->(p:Parameter)
                    WITH g, s, collect(DISTINCT p.name) AS param_names
                    RETURN g.id AS id, g.name AS raw_name, 'Validation Check' AS type,
                           COALESCE(g.physics_explanation, g.name) AS inference_logic,
                           COALESCE(g.condition_logic, '') AS citation,
                           'pending' AS status, '' AS created_at,
                           [s.name] AS projects, param_names AS events, null AS verified_as

                    UNION ALL

                    // Sub-query 4: Physical Limits (Hard Constraints)
                    MATCH (pf:ProductFamily)-[:HAS_HARD_CONSTRAINT]->(hc:HardConstraint)
                    RETURN hc.id AS id,
                           pf.name + ' — ' + COALESCE(hc.error_msg, hc.property_key + ' ' + hc.operator + ' ' + toString(hc.value)) AS raw_name,
                           'Physical Limit' AS type,
                           COALESCE(hc.error_msg, 'Constraint: ' + hc.property_key + ' ' + hc.operator + ' ' + toString(hc.value)) AS inference_logic,
                           hc.property_key + ' ' + hc.operator + ' ' + toString(hc.value) AS citation,
                           'pending' AS status, '' AS created_at,
                           [pf.name] AS projects, [hc.property_key] AS events, null AS verified_as

                    UNION ALL

                    // Sub-query 5: Assembly Requirements (Dependency Rules)
                    MATCH (dr:DependencyRule)-[:TRIGGERED_BY_STRESSOR]->(s:EnvironmentalStressor)
                    MATCH (dr)-[:UPSTREAM_REQUIRES_TRAIT]->(ut:PhysicalTrait)
                    MATCH (dr)-[:DOWNSTREAM_PROVIDES_TRAIT]->(dt:PhysicalTrait)
                    RETURN dr.id AS id,
                           ut.name + ' → ' + dt.name + ' (multi-stage)' AS raw_name,
                           'Assembly Requirement' AS type,
                           COALESCE(dr.description, ut.name + ' must protect ' + dt.name) AS inference_logic,
                           'Triggered by: ' + s.name + ' | Type: ' + COALESCE(dr.dependency_type, 'MANDATES_PROTECTION') AS citation,
                           'pending' AS status, '' AS created_at,
                           [s.name] AS projects, [ut.name, dt.name] AS events, null AS verified_as

                    UNION ALL

                    // Sub-query 6: Performance Ratings (Capacity Rules)
                    MATCH (pf:ProductFamily)-[:HAS_CAPACITY]->(cr:CapacityRule)
                    RETURN cr.id AS id,
                           pf.name + ' Capacity (' + COALESCE(cr.module_descriptor, 'default') + ')' AS raw_name,
                           'Performance Rating' AS type,
                           COALESCE(cr.description, '') + CASE WHEN cr.assumption IS NOT NULL THEN ' | ' + cr.assumption ELSE '' END AS inference_logic,
                           'Output: ' + COALESCE(toString(cr.output_rating), '?') + ' ' + COALESCE(cr.input_requirement, '?') AS citation,
                           'pending' AS status, '' AS created_at,
                           [pf.name] AS projects, [COALESCE(cr.input_requirement, 'unknown')] AS events, null AS verified_as
                """)
                return [dict(record) for record in result]

        result = self._execute_with_retry(_query)
        _set_cached(cache_key, result)
        return result


db = Neo4jConnection()
