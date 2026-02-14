"""Session Graph Manager - Layer 4: Persistent Session State in Neo4j.

This module manages active engineering sessions directly in the graph database,
making the system stateful in the graph and stateless in Python.

Architecture:
    (Session)-[:WORKING_ON]->(ActiveProject)-[:HAS_UNIT]->(TagUnit)
                                |               |           |
                                |               +-[:HAS_TURN]->(ConversationTurn)
                                +-[:USES_MATERIAL]->(Material)         [Layer 1]
                                +-[:TARGETS_FAMILY]->(ProductFamily)   [Layer 1]
                                                    +-[:SIZED_AS]->(DimensionModule) [Layer 1]

All writes use MERGE for idempotency. Duplicate messages never create duplicate nodes.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger("session_graph")


# Dimension mapping: filter dimension -> housing dimension
DIMENSION_MAP = {
    287: 300, 305: 300, 300: 300,
    592: 600, 610: 600, 600: 600,
    495: 500, 500: 500,
    900: 900, 1200: 1200,
}


def _map_filter_to_housing(dim: int) -> int:
    """Map filter dimension to standard housing size."""
    return DIMENSION_MAP.get(dim, dim)


def _derive_housing_length(filter_depth: int, product_family: str = "GDB") -> int:
    """Derive housing length from filter depth using engineering rules."""
    if product_family == "GDMI":
        return 600 if filter_depth <= 450 else 850
    elif product_family == "GDC":
        return 750 if filter_depth <= 450 else 900
    else:  # GDB default
        return 550 if filter_depth <= 292 else 750


def _normalize_orientation(width: int, height: int) -> tuple[int, int]:
    """HVAC rule: larger dimension is always HEIGHT (vertical)."""
    if width > height:
        return height, width
    return width, height


class SessionGraphManager:
    """Manages session state as Layer 4 nodes in the Neo4j graph.

    Thread-safe: each method runs its own transaction via the db connection.
    """

    def __init__(self, db_connection):
        """Initialize with an existing Neo4jConnection instance."""
        self.db = db_connection

    def _run_query(self, cypher: str, params: dict = None) -> list:
        """Execute a Cypher query using the db connection's driver."""
        try:
            with self.db.driver.session(database=self.db.database) as session:
                result = session.run(cypher, params or {})
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"Session graph query failed: {e}")
            raise

    def _run_write(self, cypher: str, params: dict = None) -> None:
        """Execute a write transaction."""
        try:
            with self.db.driver.session(database=self.db.database) as session:
                session.run(cypher, params or {})
        except Exception as e:
            logger.error(f"Session graph write failed: {e}")
            raise

    # =========================================================================
    # SESSION LIFECYCLE
    # =========================================================================

    def ensure_session(self, session_id: str, user_id: str = "default") -> None:
        """Create or update a Session node."""
        self._run_write("""
            MERGE (s:Session {id: $session_id})
            SET s.user_id = $user_id,
                s.last_active = timestamp(),
                s.created_at = COALESCE(s.created_at, timestamp())
        """, {"session_id": session_id, "user_id": user_id})

    def clear_session(self, session_id: str) -> None:
        """Delete all Layer 4 nodes for a session (Session, ActiveProject, TagUnit, ConversationTurn)."""
        self._run_write("""
            MATCH (s:Session {id: $session_id})
            OPTIONAL MATCH (s)-[:WORKING_ON]->(p:ActiveProject)
            OPTIONAL MATCH (p)-[:HAS_UNIT]->(t:TagUnit)
            OPTIONAL MATCH (p)-[:HAS_TURN]->(ct:ConversationTurn)
            DETACH DELETE ct, t, p, s
        """, {"session_id": session_id})
        logger.info(f"Cleared session graph for {session_id}")

    def cleanup_stale_sessions(self, max_age_ms: int = 7200000) -> int:
        """Remove sessions older than max_age_ms (default 2 hours)."""
        cutoff = int(time.time() * 1000) - max_age_ms
        result = self._run_query("""
            MATCH (s:Session)
            WHERE s.last_active < $cutoff
            OPTIONAL MATCH (s)-[:WORKING_ON]->(p:ActiveProject)
            OPTIONAL MATCH (p)-[:HAS_UNIT]->(t:TagUnit)
            OPTIONAL MATCH (p)-[:HAS_TURN]->(ct:ConversationTurn)
            WITH s, p, t, ct, s.id AS sid
            DETACH DELETE ct, t, p, s
            RETURN count(DISTINCT sid) AS cleaned
        """, {"cutoff": cutoff})
        cleaned = result[0]["cleaned"] if result else 0
        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} stale session(s) from graph")
        return cleaned

    # =========================================================================
    # PROJECT MANAGEMENT
    # =========================================================================

    def set_project(self, session_id: str, project_name: str,
                    customer: str = None) -> None:
        """Create or update an ActiveProject under the session."""
        project_id = f"APRJ_{session_id}"
        self._run_write("""
            MERGE (s:Session {id: $session_id})
            SET s.last_active = timestamp()
            MERGE (s)-[:WORKING_ON]->(p:ActiveProject {id: $project_id})
            SET p.name = $project_name,
                p.session_id = $session_id
            WITH p
            WHERE $customer IS NOT NULL
            SET p.customer = $customer
        """, {
            "session_id": session_id,
            "project_id": project_id,
            "project_name": project_name,
            "customer": customer,
        })

    def lock_material(self, session_id: str, material_code: str) -> None:
        """Lock material on the ActiveProject and link to Layer 1 Material node."""
        project_id = f"APRJ_{session_id}"
        self._run_write("""
            MERGE (s:Session {id: $session_id})
            SET s.last_active = timestamp()
            MERGE (s)-[:WORKING_ON]->(p:ActiveProject {id: $project_id})
            SET p.locked_material = $material_code,
                p.session_id = $session_id
            WITH p
            OPTIONAL MATCH (p)-[old:USES_MATERIAL]->()
            DELETE old
            WITH p
            OPTIONAL MATCH (m:Material {code: $material_code})
            FOREACH (_ IN CASE WHEN m IS NOT NULL THEN [1] ELSE [] END |
                MERGE (p)-[:USES_MATERIAL]->(m)
            )
        """, {
            "session_id": session_id,
            "project_id": project_id,
            "material_code": material_code.upper(),
        })

    def set_detected_family(self, session_id: str, family: str) -> None:
        """Set detected product family on the ActiveProject and link to Layer 1."""
        project_id = f"APRJ_{session_id}"
        family_id = f"FAM_{family.upper()}"
        self._run_write("""
            MERGE (s:Session {id: $session_id})
            SET s.last_active = timestamp()
            MERGE (s)-[:WORKING_ON]->(p:ActiveProject {id: $project_id})
            SET p.detected_family = $family,
                p.session_id = $session_id
            WITH p
            OPTIONAL MATCH (p)-[old:TARGETS_FAMILY]->()
            DELETE old
            WITH p
            OPTIONAL MATCH (pf:ProductFamily {id: $family_id})
            FOREACH (_ IN CASE WHEN pf IS NOT NULL THEN [1] ELSE [] END |
                MERGE (p)-[:TARGETS_FAMILY]->(pf)
            )
        """, {
            "session_id": session_id,
            "project_id": project_id,
            "family": family.upper(),
            "family_id": family_id,
        })

    def set_pending_clarification(self, session_id: str, param_name: str = None) -> None:
        """Track what parameter the system is currently asking about.

        Set to None to clear when no clarification is pending.
        """
        project_id = f"APRJ_{session_id}"
        self._run_write("""
            MERGE (s:Session {id: $session_id})
            SET s.last_active = timestamp()
            MERGE (s)-[:WORKING_ON]->(p:ActiveProject {id: $project_id})
            SET p.pending_clarification = $param_name,
                p.session_id = $session_id
        """, {
            "session_id": session_id,
            "project_id": project_id,
            "param_name": param_name,
        })

    def set_accessories(self, session_id: str, accessories: list) -> None:
        """Persist accessories list on the ActiveProject node."""
        project_id = f"APRJ_{session_id}"
        self._run_write("""
            MERGE (s:Session {id: $session_id})
            SET s.last_active = timestamp()
            MERGE (s)-[:WORKING_ON]->(p:ActiveProject {id: $project_id})
            SET p.accessories = $accessories,
                p.session_id = $session_id
        """, {
            "session_id": session_id,
            "project_id": project_id,
            "accessories": accessories,
        })

    def set_assembly_group(self, session_id: str, assembly_group: dict) -> None:
        """Persist assembly group metadata (multi-stage system) on the ActiveProject node."""
        import json
        project_id = f"APRJ_{session_id}"
        self._run_write("""
            MERGE (s:Session {id: $session_id})
            SET s.last_active = timestamp()
            MERGE (s)-[:WORKING_ON]->(p:ActiveProject {id: $project_id})
            SET p.assembly_group = $assembly_json,
                p.session_id = $session_id
        """, {
            "session_id": session_id,
            "project_id": project_id,
            "assembly_json": json.dumps(assembly_group),
        })

    def set_resolved_params(self, session_id: str, resolved_params: dict) -> None:
        """Persist generic resolved parameters (gate answers, etc.) on the ActiveProject node."""
        import json
        project_id = f"APRJ_{session_id}"
        self._run_write("""
            MERGE (s:Session {id: $session_id})
            SET s.last_active = timestamp()
            MERGE (s)-[:WORKING_ON]->(p:ActiveProject {id: $project_id})
            SET p.resolved_params = $params_json,
                p.session_id = $session_id
        """, {
            "session_id": session_id,
            "project_id": project_id,
            "params_json": json.dumps(resolved_params),
        })

    def set_vetoed_families(self, session_id: str, vetoed_families: list[str]) -> None:
        """Persist vetoed product families on the ActiveProject node.

        These are product families that the engine has vetoed due to
        environment/trait incompatibility. Persisted across turns so
        continuation turns don't forget the veto decision.
        """
        import json
        project_id = f"APRJ_{session_id}"
        self._run_write("""
            MERGE (s:Session {id: $session_id})
            SET s.last_active = timestamp()
            MERGE (s)-[:WORKING_ON]->(p:ActiveProject {id: $project_id})
            SET p.vetoed_families = $vetoed_json,
                p.session_id = $session_id
        """, {
            "session_id": session_id,
            "project_id": project_id,
            "vetoed_json": json.dumps(vetoed_families),
        })

    # =========================================================================
    # CONVERSATION HISTORY (v3.0 — Semantic Scribe context)
    # =========================================================================

    def store_turn(self, session_id: str, role: str, message: str,
                   turn_number: int) -> None:
        """Store a conversation turn as a (:ConversationTurn) node in Layer 4.

        Args:
            session_id: Session identifier
            role: "user" or "assistant"
            message: Raw message text (truncated to 2000 chars)
            turn_number: Sequential turn counter
        """
        project_id = f"APRJ_{session_id}"
        turn_id = f"TURN_{session_id}_{turn_number}_{role}"
        self._run_write("""
            MERGE (s:Session {id: $session_id})
            SET s.last_active = timestamp()
            MERGE (s)-[:WORKING_ON]->(p:ActiveProject {id: $project_id})
            SET p.session_id = $session_id
            MERGE (p)-[:HAS_TURN]->(ct:ConversationTurn {id: $turn_id})
            SET ct.role = $role,
                ct.message = $message,
                ct.turn_number = $turn_number,
                ct.created_at = COALESCE(ct.created_at, timestamp())
        """, {
            "session_id": session_id,
            "project_id": project_id,
            "turn_id": turn_id,
            "role": role,
            "message": message[:2000],
            "turn_number": turn_number,
        })

    def get_recent_turns(self, session_id: str, n: int = 3) -> list[dict]:
        """Retrieve the last N conversation turns for a session.

        Returns list of dicts: [{"role": "user", "message": "...", "turn_number": N}]
        Ordered chronologically (oldest first) for prompt context.
        """
        project_id = f"APRJ_{session_id}"
        result = self._run_query("""
            MATCH (p:ActiveProject {id: $project_id})-[:HAS_TURN]->(ct:ConversationTurn)
            RETURN ct.role AS role, ct.message AS message, ct.turn_number AS turn_number
            ORDER BY ct.turn_number DESC
            LIMIT $n
        """, {"project_id": project_id, "n": n})
        # Reverse to chronological order (oldest first)
        return list(reversed(result))

    # =========================================================================
    # TAG UNIT MANAGEMENT
    # =========================================================================

    def upsert_tag(self, session_id: str, tag_id: str,
                   filter_width: int = None, filter_height: int = None,
                   filter_depth: int = None, airflow_m3h: int = None,
                   product_family: str = None, product_code: str = None,
                   weight_kg: float = None, quantity: int = None,
                   source_message: int = None,
                   assembly_group_id: str = None) -> dict:
        """Create or update a TagUnit under the session's ActiveProject.

        Automatically computes derived values:
        - Housing dimensions from filter dimensions
        - Housing length from filter depth
        - Orientation normalization (larger = height)

        When assembly_group_id is set, Cypher auto-propagates shared properties
        (dimensions, capacity) to sibling TagUnits in the same assembly group.
        This is the Graph enforcing Digital Twin consistency.

        Returns the tag's current state as a dict.
        """
        project_id = f"APRJ_{session_id}"
        tag_node_id = f"TAG_{session_id}_{tag_id}"

        # Compute derived values
        housing_width = _map_filter_to_housing(filter_width) if filter_width else None
        housing_height = _map_filter_to_housing(filter_height) if filter_height else None

        # v3.8: Do NOT normalize orientation — preserve user-specified WxH order
        # to match catalog convention (Bredd × Höjd). Normalization was swapping
        # dimensions (e.g., 1800x900 → 900x1800) causing wrong weight/DimensionModule lookup.

        family = product_family or "GDB"
        housing_length = None
        if filter_depth:
            housing_length = _derive_housing_length(filter_depth, family)

        # Build SET clause dynamically (only update non-null fields)
        set_parts = ["t.tag_id = $tag_id", "t.session_id = $session_id"]
        params = {
            "session_id": session_id,
            "project_id": project_id,
            "tag_node_id": tag_node_id,
            "tag_id": tag_id,
        }

        field_map = {
            "filter_width": filter_width,
            "filter_height": filter_height,
            "filter_depth": filter_depth,
            "housing_width": housing_width,
            "housing_height": housing_height,
            "housing_length": housing_length,
            "airflow_m3h": airflow_m3h,
            "product_family": product_family,
            "product_code": product_code,
            "weight_kg": weight_kg,
            "quantity": quantity,
            "source_message": source_message,
            "assembly_group_id": assembly_group_id,
        }

        for key, value in field_map.items():
            if value is not None:
                set_parts.append(f"t.{key} = ${key}")
                params[key] = value

        set_clause = ", ".join(set_parts)

        # Determine completeness
        completeness_check = """
        WITH t
        SET t.is_complete = (
            t.housing_width IS NOT NULL AND
            t.housing_height IS NOT NULL AND
            t.housing_length IS NOT NULL
        )
        """

        # Graph-level sibling sync: when a TagUnit belongs to an assembly group,
        # auto-propagate shared properties to siblings (same duct = same dimensions).
        # COALESCE keeps sibling's own value if it has one, otherwise inherits.
        # housing_length is NOT synced — each stage has its own (from graph auto-resolve).
        sibling_sync = ""
        if assembly_group_id:
            sibling_sync = """
            WITH t
            OPTIONAL MATCH (pp:ActiveProject)-[:HAS_UNIT]->(sibling:TagUnit)
            WHERE sibling.assembly_group_id = t.assembly_group_id
              AND sibling.id <> t.id
            SET sibling.housing_width = COALESCE(sibling.housing_width, t.housing_width),
                sibling.housing_height = COALESCE(sibling.housing_height, t.housing_height),
                sibling.filter_width = COALESCE(sibling.filter_width, t.filter_width),
                sibling.filter_height = COALESCE(sibling.filter_height, t.filter_height),
                sibling.airflow_m3h = COALESCE(sibling.airflow_m3h, t.airflow_m3h)
            """

        cypher = f"""
            MERGE (s:Session {{id: $session_id}})
            SET s.last_active = timestamp()
            MERGE (s)-[:WORKING_ON]->(p:ActiveProject {{id: $project_id}})
            SET p.session_id = $session_id
            MERGE (p)-[:HAS_UNIT]->(t:TagUnit {{id: $tag_node_id}})
            SET {set_clause}
            {completeness_check}
            {sibling_sync}
            RETURN t {{.*}} AS tag
        """

        result = self._run_query(cypher, params)

        # Link to DimensionModule in Layer 1
        if housing_width and housing_height:
            dim_id = f"DIM_{housing_width}x{housing_height}"
            self._run_write("""
                MATCH (t:TagUnit {id: $tag_node_id})
                OPTIONAL MATCH (t)-[old:SIZED_AS]->()
                DELETE old
                WITH t
                OPTIONAL MATCH (d:DimensionModule {id: $dim_id})
                FOREACH (_ IN CASE WHEN d IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (t)-[:SIZED_AS]->(d)
                )
            """, {"tag_node_id": tag_node_id, "dim_id": dim_id})

        return result[0]["tag"] if result else {}

    # =========================================================================
    # STATE RETRIEVAL
    # =========================================================================

    def get_project_state(self, session_id: str) -> dict:
        """Get complete session state as a structured dict.

        Returns:
            {
                "session_id": "...",
                "project": {"name": "...", "customer": "...", "locked_material": "...", "detected_family": "..."},
                "tags": [{"tag_id": "5684", "filter_width": 305, ...}, ...],
                "tag_count": 2
            }
        """
        result = self._run_query("""
            MATCH (s:Session {id: $session_id})
            OPTIONAL MATCH (s)-[:WORKING_ON]->(p:ActiveProject)
            OPTIONAL MATCH (p)-[:HAS_UNIT]->(t:TagUnit)
            WITH s, p, collect(t {.*}) AS tags
            RETURN s.id AS session_id,
                   p {.name, .customer, .locked_material, .detected_family, .pending_clarification, .accessories, .assembly_group, .resolved_params, .vetoed_families} AS project,
                   tags,
                   size(tags) AS tag_count
        """, {"session_id": session_id})

        if not result:
            return {
                "session_id": session_id,
                "project": None,
                "tags": [],
                "tag_count": 0,
            }

        row = result[0]
        return {
            "session_id": row["session_id"],
            "project": row["project"],
            "tags": row["tags"] or [],
            "tag_count": row["tag_count"] or 0,
        }

    def get_tag_count(self, session_id: str) -> int:
        """Count TagUnit nodes for this session (for multi-item protection)."""
        result = self._run_query("""
            MATCH (s:Session {id: $session_id})-[:WORKING_ON]->(p:ActiveProject)-[:HAS_UNIT]->(t:TagUnit)
            RETURN count(t) AS cnt
        """, {"session_id": session_id})
        return result[0]["cnt"] if result else 0

    def get_project_state_for_prompt(self, session_id: str) -> str:
        """Format session state as an LLM prompt injection string.

        This generates a VERY EXPLICIT context that the LLM cannot ignore,
        similar to TechnicalState.to_prompt_context() but sourced from the graph.
        """
        state = self.get_project_state(session_id)

        if not state["project"] and not state["tags"]:
            return ""

        lines = []
        lines.append("## PROJECT_GRAPH_STATE (ABSOLUTE TRUTH FROM DATABASE)")
        lines.append("")
        lines.append("**The following data is persisted in the graph database. It is IMMUTABLE.**")
        lines.append("**Use this data exactly. Do NOT ask for information already provided.**")
        lines.append("")

        project = state.get("project")
        if project:
            lines.append("### LOCKED PARAMETERS")
            if project.get("name"):
                lines.append(f"- **Project:** {project['name']}")
            if project.get("customer"):
                lines.append(f"- **Customer:** {project['customer']}")
            if project.get("locked_material"):
                lines.append(f"- **Material:** {project['locked_material']} (LOCKED - use in ALL product codes)")
            if project.get("detected_family"):
                lines.append(f"- **Product Family:** {project['detected_family']}")
            lines.append("")

        tags = state.get("tags", [])
        if tags:
            lines.append(f"### TAG SPECIFICATIONS ({len(tags)} unit(s) - EXACTLY this many, no more)")
            lines.append("")

            for tag in sorted(tags, key=lambda t: t.get("tag_id", "")):
                tag_id = tag.get("tag_id", "unknown")
                lines.append(f"**Tag {tag_id}:**")

                if tag.get("filter_width") and tag.get("filter_height"):
                    depth_str = f"x{tag['filter_depth']}mm" if tag.get("filter_depth") else ""
                    lines.append(f"  - Filter: {tag['filter_width']}x{tag['filter_height']}{depth_str}")

                if tag.get("housing_width") and tag.get("housing_height"):
                    lines.append(f"  - Housing Size: {tag['housing_width']}x{tag['housing_height']}mm")

                if tag.get("housing_length"):
                    lines.append(f"  - Housing Length: {tag['housing_length']}mm (auto-derived)")

                if tag.get("airflow_m3h"):
                    lines.append(f"  - Airflow: {tag['airflow_m3h']} m3/h")

                if tag.get("product_code"):
                    lines.append(f"  - Product Code: {tag['product_code']}")

                if tag.get("weight_kg"):
                    lines.append(f"  - Weight: {tag['weight_kg']} kg")

                status = "COMPLETE" if tag.get("is_complete") else "INCOMPLETE"
                lines.append(f"  - Status: {status}")
                lines.append("")

            # Multi-item protection
            lines.append(f"**CRITICAL: This project has EXACTLY {len(tags)} unit(s).**")
            lines.append("Do NOT create, invent, or reference any additional units.")
            lines.append("")

        lines.append("### PROHIBITIONS")
        lines.append("1. NEVER ask for data shown above")
        lines.append("2. NEVER revert locked material")
        lines.append("3. NEVER invent additional tags/items beyond those listed")
        lines.append("4. ALWAYS use locked material suffix in product codes")
        lines.append("")

        return "\n".join(lines)

    def get_reasoning_path(self, session_id: str) -> list[dict]:
        """Return per-tag audit trail for LLM context.

        Returns a list of reasoning path entries like:
        [{"tag_id": "5684", "path": "Material locked to RF -> Sized to 300x600 -> Length 550mm"}]
        """
        tags = self.get_project_state(session_id).get("tags", [])
        paths = []

        for tag in sorted(tags, key=lambda t: t.get("tag_id", "")):
            tag_id = tag.get("tag_id", "unknown")
            steps = []

            project_state = self.get_project_state(session_id)
            project = project_state.get("project", {})

            if project and project.get("locked_material"):
                steps.append(f"Material locked to {project['locked_material']}")

            if tag.get("filter_width") and tag.get("filter_height"):
                steps.append(f"Filter {tag['filter_width']}x{tag['filter_height']}mm")

            if tag.get("housing_width") and tag.get("housing_height"):
                steps.append(f"Sized to {tag['housing_width']}x{tag['housing_height']}")

            if tag.get("housing_length"):
                steps.append(f"Length {tag['housing_length']}mm")

            if tag.get("weight_kg"):
                steps.append(f"Weight {tag['weight_kg']}kg")

            if tag.get("product_code"):
                steps.append(f"Code: {tag['product_code']}")

            paths.append({
                "tag_id": tag_id,
                "path": " -> ".join(steps) if steps else "No data yet",
            })

        return paths

    # =========================================================================
    # GRAPH VISUALIZATION DATA
    # =========================================================================

    def get_session_graph_data(self, session_id: str) -> dict:
        """Return session graph as nodes + relationships for ForceGraph2D visualization.

        Includes Layer 4 nodes (Session, ActiveProject, TagUnit) and
        linked Layer 1 nodes (Material, ProductFamily, DimensionModule).
        """
        result = self._run_query("""
            MATCH (s:Session {id: $session_id})
            OPTIONAL MATCH (s)-[r1:WORKING_ON]->(p:ActiveProject)
            OPTIONAL MATCH (p)-[r2:HAS_UNIT]->(t:TagUnit)
            OPTIONAL MATCH (p)-[r3:USES_MATERIAL]->(m:Material)
            OPTIONAL MATCH (p)-[r4:TARGETS_FAMILY]->(pf:ProductFamily)
            OPTIONAL MATCH (t)-[r5:SIZED_AS]->(d:DimensionModule)
            WITH s, p, t, m, pf, d,
                 collect(DISTINCT {
                    id: elementId(s),
                    labels: labels(s),
                    name: 'Session: ' + s.id,
                    properties: s {.id, .user_id, .last_active}
                 }) AS session_nodes,
                 CASE WHEN p IS NOT NULL THEN [{
                    id: elementId(p),
                    labels: labels(p),
                    name: coalesce(p.name, 'Unnamed Project'),
                    properties: p {.name, .customer, .locked_material, .detected_family}
                 }] ELSE [] END AS project_nodes,
                 CASE WHEN t IS NOT NULL THEN [{
                    id: elementId(t),
                    labels: labels(t),
                    name: 'Tag ' + coalesce(t.tag_id, '?'),
                    properties: t {.*}
                 }] ELSE [] END AS tag_nodes,
                 CASE WHEN m IS NOT NULL THEN [{
                    id: elementId(m),
                    labels: labels(m),
                    name: m.code + ' (' + m.name + ')',
                    properties: m {.code, .name, .corrosion_class}
                 }] ELSE [] END AS mat_nodes,
                 CASE WHEN pf IS NOT NULL THEN [{
                    id: elementId(pf),
                    labels: labels(pf),
                    name: pf.name,
                    properties: pf {.name, .type}
                 }] ELSE [] END AS family_nodes,
                 CASE WHEN d IS NOT NULL THEN [{
                    id: elementId(d),
                    labels: labels(d),
                    name: d.label,
                    properties: d {.width_mm, .height_mm, .reference_airflow_m3h, .label}
                 }] ELSE [] END AS dim_nodes
            RETURN session_nodes, project_nodes, tag_nodes, mat_nodes, family_nodes, dim_nodes
        """, {"session_id": session_id})

        # Fallback: simpler approach using multiple queries
        nodes = []
        relationships = []
        seen_ids = set()

        # Query all session subgraph nodes and relationships
        graph_result = self._run_query("""
            MATCH (s:Session {id: $session_id})
            OPTIONAL MATCH path1 = (s)-[r1:WORKING_ON]->(p:ActiveProject)
            OPTIONAL MATCH path2 = (p)-[r2:HAS_UNIT]->(t:TagUnit)
            OPTIONAL MATCH path3 = (p)-[r3:USES_MATERIAL]->(m:Material)
            OPTIONAL MATCH path4 = (p)-[r4:TARGETS_FAMILY]->(pf:ProductFamily)
            OPTIONAL MATCH path5 = (t)-[r5:SIZED_AS]->(d:DimensionModule)
            WITH s, p, t, m, pf, d, r1, r2, r3, r4, r5
            RETURN
                elementId(s) AS s_id, labels(s) AS s_labels, s {.id, .user_id} AS s_props,
                elementId(p) AS p_id, labels(p) AS p_labels, p {.name, .customer, .locked_material, .detected_family} AS p_props,
                elementId(t) AS t_id, labels(t) AS t_labels, t {.*} AS t_props,
                elementId(m) AS m_id, labels(m) AS m_labels, m {.code, .name, .corrosion_class} AS m_props,
                elementId(pf) AS pf_id, labels(pf) AS pf_labels, pf {.name, .type} AS pf_props,
                elementId(d) AS d_id, labels(d) AS d_labels, d {.label, .width_mm, .height_mm} AS d_props,
                elementId(r1) AS r1_id, type(r1) AS r1_type,
                elementId(r2) AS r2_id, type(r2) AS r2_type,
                elementId(r3) AS r3_id, type(r3) AS r3_type,
                elementId(r4) AS r4_id, type(r4) AS r4_type,
                elementId(r5) AS r5_id, type(r5) AS r5_type
        """, {"session_id": session_id})

        for row in graph_result:
            # Session node
            if row.get("s_id") and row["s_id"] not in seen_ids:
                nodes.append({
                    "id": row["s_id"],
                    "labels": row["s_labels"] or ["Session"],
                    "name": f"Session",
                    "properties": row["s_props"] or {},
                })
                seen_ids.add(row["s_id"])

            # ActiveProject node
            if row.get("p_id") and row["p_id"] not in seen_ids:
                props = row["p_props"] or {}
                nodes.append({
                    "id": row["p_id"],
                    "labels": row["p_labels"] or ["ActiveProject"],
                    "name": props.get("name", "Unnamed Project"),
                    "properties": props,
                })
                seen_ids.add(row["p_id"])

            # WORKING_ON relationship
            if row.get("r1_id") and row["r1_id"] not in seen_ids:
                relationships.append({
                    "id": row["r1_id"],
                    "type": row["r1_type"],
                    "source": row["s_id"],
                    "target": row["p_id"],
                    "properties": {},
                })
                seen_ids.add(row["r1_id"])

            # TagUnit node
            if row.get("t_id") and row["t_id"] not in seen_ids:
                props = row["t_props"] or {}
                tag_name = f"Tag {props.get('tag_id', '?')}"
                nodes.append({
                    "id": row["t_id"],
                    "labels": row["t_labels"] or ["TagUnit"],
                    "name": tag_name,
                    "properties": props,
                })
                seen_ids.add(row["t_id"])

            # HAS_UNIT relationship
            if row.get("r2_id") and row["r2_id"] not in seen_ids:
                relationships.append({
                    "id": row["r2_id"],
                    "type": row["r2_type"],
                    "source": row["p_id"],
                    "target": row["t_id"],
                    "properties": {},
                })
                seen_ids.add(row["r2_id"])

            # Material node
            if row.get("m_id") and row["m_id"] not in seen_ids:
                props = row["m_props"] or {}
                nodes.append({
                    "id": row["m_id"],
                    "labels": row["m_labels"] or ["Material"],
                    "name": f"{props.get('code', '?')} ({props.get('name', '')})",
                    "properties": props,
                })
                seen_ids.add(row["m_id"])

            # USES_MATERIAL relationship
            if row.get("r3_id") and row["r3_id"] not in seen_ids:
                relationships.append({
                    "id": row["r3_id"],
                    "type": row["r3_type"],
                    "source": row["p_id"],
                    "target": row["m_id"],
                    "properties": {},
                })
                seen_ids.add(row["r3_id"])

            # ProductFamily node
            if row.get("pf_id") and row["pf_id"] not in seen_ids:
                props = row["pf_props"] or {}
                nodes.append({
                    "id": row["pf_id"],
                    "labels": row["pf_labels"] or ["ProductFamily"],
                    "name": props.get("name", "?"),
                    "properties": props,
                })
                seen_ids.add(row["pf_id"])

            # TARGETS_FAMILY relationship
            if row.get("r4_id") and row["r4_id"] not in seen_ids:
                relationships.append({
                    "id": row["r4_id"],
                    "type": row["r4_type"],
                    "source": row["p_id"],
                    "target": row["pf_id"],
                    "properties": {},
                })
                seen_ids.add(row["r4_id"])

            # DimensionModule node
            if row.get("d_id") and row["d_id"] not in seen_ids:
                props = row["d_props"] or {}
                nodes.append({
                    "id": row["d_id"],
                    "labels": row["d_labels"] or ["DimensionModule"],
                    "name": props.get("label", "?"),
                    "properties": props,
                })
                seen_ids.add(row["d_id"])

            # SIZED_AS relationship
            if row.get("r5_id") and row["r5_id"] not in seen_ids:
                relationships.append({
                    "id": row["r5_id"],
                    "type": row["r5_type"],
                    "source": row["t_id"],
                    "target": row["d_id"],
                    "properties": {},
                })
                seen_ids.add(row["r5_id"])

        return {
            "nodes": nodes,
            "relationships": relationships,
        }
