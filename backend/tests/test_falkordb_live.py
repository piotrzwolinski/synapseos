"""FalkorDB live smoke tests — validates the migration target works.

These tests connect to a real FalkorDB instance (skip without FALKORDB_HOST).
They exercise the exact patterns that change during migration:
1. Connect → write node → read back → verify types → cleanup
2. State roundtrip: write session state → read → verify shape
3. Cypher compatibility: MERGE, OPTIONAL MATCH, COALESCE, UNWIND, collect()

Set env vars to run:
    FALKORDB_HOST=localhost FALKORDB_PORT=6379 pytest tests/test_falkordb_live.py -v
"""

import os
import json
import time
import pytest

# Skip entire module if no FalkorDB connection
pytestmark = pytest.mark.skipif(
    not os.getenv("FALKORDB_HOST"),
    reason="FALKORDB_HOST not set — skipping live FalkorDB smoke tests"
)

GRAPH_NAME = "__test_migration_smoke__"


@pytest.fixture(scope="module")
def falkor_graph():
    """Get a FalkorDB graph connection for smoke testing."""
    from falkordb import FalkorDB

    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    password = os.getenv("FALKORDB_PASSWORD", None)

    db = FalkorDB(host=host, port=port, password=password)
    graph = db.select_graph(GRAPH_NAME)

    yield graph

    # Cleanup: delete the test graph
    try:
        graph.query("MATCH (n) DETACH DELETE n")
    except Exception:
        pass


@pytest.fixture(scope="module")
def helpers():
    """Import the conversion helpers."""
    import sys
    from pathlib import Path
    BACKEND_DIR = Path(__file__).resolve().parent.parent
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from db_result_helpers import result_to_dicts, result_single, result_value
    return result_to_dicts, result_single, result_value


# =============================================================================
# Basic CRUD smoke tests
# =============================================================================

class TestBasicCRUD:
    """Verify basic create/read/delete works with FalkorDB."""

    def test_create_and_read_node(self, falkor_graph, helpers):
        result_to_dicts, result_single, _ = helpers

        # Create
        falkor_graph.query(
            "CREATE (s:TestNode {name: $name, value: $value})",
            params={"name": "smoke_test", "value": 42}
        )

        # Read back
        result = falkor_graph.query(
            "MATCH (s:TestNode {name: $name}) RETURN s.name AS name, s.value AS value",
            params={"name": "smoke_test"}
        )
        rows = result_to_dicts(result)
        assert len(rows) == 1
        assert rows[0]["name"] == "smoke_test"
        assert rows[0]["value"] == 42
        assert isinstance(rows[0]["value"], int)

    def test_merge_node(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        # MERGE — idempotent create
        falkor_graph.query(
            "MERGE (s:TestNode {name: $name}) SET s.value = $value",
            params={"name": "merge_test", "value": 100}
        )
        falkor_graph.query(
            "MERGE (s:TestNode {name: $name}) SET s.value = $value",
            params={"name": "merge_test", "value": 200}
        )

        result = falkor_graph.query(
            "MATCH (s:TestNode {name: $name}) RETURN s.value AS value",
            params={"name": "merge_test"}
        )
        rows = result_to_dicts(result)
        assert len(rows) == 1
        assert rows[0]["value"] == 200  # updated, not duplicated

    def test_null_values(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        falkor_graph.query(
            "CREATE (s:TestNode {name: $name})",
            params={"name": "null_test"}
        )

        result = falkor_graph.query(
            "MATCH (s:TestNode {name: $name}) RETURN s.name AS name, s.missing_prop AS missing",
            params={"name": "null_test"}
        )
        rows = result_to_dicts(result)
        assert rows[0]["missing"] is None

    def test_boolean_types(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        falkor_graph.query(
            "CREATE (s:TestNode {name: 'bool_test', active: true, deleted: false})"
        )
        result = falkor_graph.query(
            "MATCH (s:TestNode {name: 'bool_test'}) RETURN s.active AS active, s.deleted AS deleted"
        )
        rows = result_to_dicts(result)
        assert rows[0]["active"] is True
        assert rows[0]["deleted"] is False

    def test_float_types(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        falkor_graph.query(
            "CREATE (s:TestNode {name: 'float_test', score: 0.95, airflow: 3400.0})"
        )
        result = falkor_graph.query(
            "MATCH (s:TestNode {name: 'float_test'}) RETURN s.score AS score, s.airflow AS airflow"
        )
        rows = result_to_dicts(result)
        assert isinstance(rows[0]["score"], float)
        assert rows[0]["score"] == pytest.approx(0.95)

    def test_list_properties(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        falkor_graph.query(
            "CREATE (s:TestNode {name: 'list_test', keywords: ['kitchen', 'grease', 'cooking']})"
        )
        result = falkor_graph.query(
            "MATCH (s:TestNode {name: 'list_test'}) RETURN s.keywords AS keywords"
        )
        rows = result_to_dicts(result)
        assert isinstance(rows[0]["keywords"], list)
        assert "kitchen" in rows[0]["keywords"]


# =============================================================================
# Cypher compatibility — patterns used in database.py
# =============================================================================

class TestCypherCompatibility:
    """Verify FalkorDB supports Cypher patterns used in database.py."""

    def test_optional_match(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        falkor_graph.query("CREATE (a:Alpha {name: 'a1'})")

        result = falkor_graph.query("""
            MATCH (a:Alpha {name: 'a1'})
            OPTIONAL MATCH (a)-[:LINKED]->(b:Beta)
            RETURN a.name AS alpha, b.name AS beta
        """)
        rows = result_to_dicts(result)
        assert rows[0]["alpha"] == "a1"
        assert rows[0]["beta"] is None

    def test_coalesce(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        falkor_graph.query("CREATE (n:CoalesceTest {name: 'ct1'})")

        result = falkor_graph.query("""
            MATCH (n:CoalesceTest {name: 'ct1'})
            RETURN COALESCE(n.missing, 'default') AS val
        """)
        rows = result_to_dicts(result)
        assert rows[0]["val"] == "default"

    def test_unwind(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        result = falkor_graph.query("""
            UNWIND $items AS item
            RETURN item AS val
        """, params={"items": [10, 20, 30]})
        rows = result_to_dicts(result)
        assert len(rows) == 3
        assert [r["val"] for r in rows] == [10, 20, 30]

    def test_collect(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        falkor_graph.query("""
            CREATE (p:Parent {name: 'p1'})
            CREATE (p)-[:HAS]->(:Child {name: 'c1'})
            CREATE (p)-[:HAS]->(:Child {name: 'c2'})
        """)

        result = falkor_graph.query("""
            MATCH (p:Parent {name: 'p1'})-[:HAS]->(c:Child)
            RETURN p.name AS parent, collect(c.name) AS children
        """)
        rows = result_to_dicts(result)
        assert rows[0]["parent"] == "p1"
        assert set(rows[0]["children"]) == {"c1", "c2"}

    def test_merge_on_create_set(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        # First call: creates with ON CREATE SET
        falkor_graph.query("""
            MERGE (n:MergeTest {name: $name})
            ON CREATE SET n.created = true, n.counter = 1
            ON MATCH SET n.counter = n.counter + 1
        """, params={"name": "merge_oc_test"})

        # Second call: matches with ON MATCH SET
        falkor_graph.query("""
            MERGE (n:MergeTest {name: $name})
            ON CREATE SET n.created = true, n.counter = 1
            ON MATCH SET n.counter = n.counter + 1
        """, params={"name": "merge_oc_test"})

        result = falkor_graph.query(
            "MATCH (n:MergeTest {name: $name}) RETURN n.counter AS counter",
            params={"name": "merge_oc_test"}
        )
        rows = result_to_dicts(result)
        assert rows[0]["counter"] == 2

    def test_foreach(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        falkor_graph.query("""
            CREATE (p:ForeachParent {name: 'fp1'})
            WITH p
            FOREACH (x IN range(1, 3) |
                CREATE (p)-[:HAS_CHILD]->(:ForeachChild {num: x})
            )
        """)

        result = falkor_graph.query("""
            MATCH (p:ForeachParent {name: 'fp1'})-[:HAS_CHILD]->(c:ForeachChild)
            RETURN count(c) AS count
        """)
        rows = result_to_dicts(result)
        assert rows[0]["count"] == 3

    def test_timestamp_function(self, falkor_graph, helpers):
        result_to_dicts, _, _ = helpers

        result = falkor_graph.query("RETURN timestamp() AS ts")
        rows = result_to_dicts(result)
        assert isinstance(rows[0]["ts"], (int, float))
        assert rows[0]["ts"] > 0


# =============================================================================
# Session state roundtrip — mimics SessionGraphManager
# =============================================================================

class TestSessionStateRoundtrip:
    """Verify the exact Layer 4 patterns work in FalkorDB."""

    def test_session_create_and_read(self, falkor_graph, helpers):
        result_to_dicts, result_single, _ = helpers

        # Mimics ensure_session
        falkor_graph.query("""
            MERGE (s:Session {session_id: $sid})
            ON CREATE SET s.created_at = timestamp(), s.last_active = timestamp()
            ON MATCH SET s.last_active = timestamp()
        """, params={"sid": "smoke_sess_1"})

        # Mimics get_project_state
        result = falkor_graph.query("""
            MATCH (s:Session {session_id: $sid})
            OPTIONAL MATCH (s)-[:HAS_PROJECT]->(p:ActiveProject)
            OPTIONAL MATCH (s)-[:HAS_TAG]->(t:TagUnit)
            RETURN s.session_id AS session_id,
                   p AS project,
                   collect(t) AS tags,
                   count(t) AS tag_count
        """, params={"sid": "smoke_sess_1"})
        row = result_single(result)
        assert row is not None
        assert row["session_id"] == "smoke_sess_1"
        assert row["tag_count"] == 0

    def test_tag_upsert_roundtrip(self, falkor_graph, helpers):
        result_to_dicts, result_single, _ = helpers

        # Create session
        falkor_graph.query("""
            MERGE (s:Session {session_id: $sid})
        """, params={"sid": "smoke_sess_2"})

        # Mimics upsert_tag
        falkor_graph.query("""
            MATCH (s:Session {session_id: $sid})
            MERGE (s)-[:HAS_TAG]->(t:TagUnit {tag_id: $tid})
            SET t.filter_width = $width,
                t.filter_height = $height,
                t.airflow_m3h = $airflow,
                t.session_id = $sid
        """, params={
            "sid": "smoke_sess_2", "tid": "item_1",
            "width": 600, "height": 600, "airflow": 3000,
        })

        # Read back
        result = falkor_graph.query("""
            MATCH (s:Session {session_id: $sid})-[:HAS_TAG]->(t:TagUnit)
            RETURN t.tag_id AS tag_id, t.filter_width AS width,
                   t.filter_height AS height, t.airflow_m3h AS airflow
        """, params={"sid": "smoke_sess_2"})
        rows = result_to_dicts(result)
        assert len(rows) == 1
        assert rows[0]["tag_id"] == "item_1"
        assert rows[0]["width"] == 600
        assert isinstance(rows[0]["width"], int)
        assert rows[0]["airflow"] == 3000

    def test_resolved_params_json_roundtrip(self, falkor_graph, helpers):
        _, result_single, _ = helpers

        params_json = json.dumps({"connection_type": "PG", "door_side": "R"})

        # Write
        falkor_graph.query("""
            MERGE (s:Session {session_id: $sid})
            MERGE (s)-[:HAS_PROJECT]->(p:ActiveProject {session_id: $sid})
            SET p.resolved_params = $rp
        """, params={"sid": "smoke_sess_3", "rp": params_json})

        # Read back
        result = falkor_graph.query("""
            MATCH (s:Session {session_id: $sid})-[:HAS_PROJECT]->(p:ActiveProject)
            RETURN p.resolved_params AS resolved_params
        """, params={"sid": "smoke_sess_3"})
        row = result_single(result)
        assert row is not None
        parsed = json.loads(row["resolved_params"])
        assert parsed["connection_type"] == "PG"
        assert parsed["door_side"] == "R"


# =============================================================================
# Index creation smoke test
# =============================================================================

class TestIndexCreation:
    """Verify FalkorDB index creation patterns work."""

    def test_create_range_index(self, falkor_graph):
        try:
            falkor_graph.query(
                "CREATE INDEX FOR (s:Session) ON (s.session_id)"
            )
        except Exception as e:
            if "already exists" not in str(e).lower():
                raise

    def test_create_index_idempotent(self, falkor_graph):
        """Second create should fail gracefully."""
        try:
            falkor_graph.query(
                "CREATE INDEX FOR (s:Session) ON (s.session_id)"
            )
        except Exception as e:
            assert "already exists" in str(e).lower()
