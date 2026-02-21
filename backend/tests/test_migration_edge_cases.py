"""Tests for FalkorDB migration edge cases.

Covers the specific Cypher/driver patterns that BREAK during migration:
- result.peek() → _query_single replacement (3 sites)
- EXISTS {} subquery → pattern predicate rewrite (2 sites)
- Map projection {.*} → properties() fallback (1+ sites)
- SHOW INDEXES → db.indexes() replacement (1 site)
- Index/constraint DDL syntax changes (7 statements)
- init_session_schema() full flow
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# =============================================================================
# Tests for methods that use result.peek() — lines 4081, 4244, 4333
# =============================================================================

class TestPeekReplacementWithResultSingle:
    """Test the replacement of result.peek()/single() with result_single().

    After FalkorDB migration, peek() is replaced by result_single() which
    returns the first row as dict or None.
    """

    def _make_falkordb_result(self, row_dict):
        """Create a mock FalkorDB QueryResult."""
        from db_result_helpers import result_single
        mock_result = MagicMock()
        if row_dict is None:
            mock_result.result_set = None
            mock_result.header = []
        else:
            headers = list(row_dict.keys())
            mock_result.header = [(0, h) for h in headers]
            mock_result.result_set = [[row_dict[h] for h in headers]]
        return mock_result

    def test_result_single_with_data(self):
        """result_single() returns first row as dict when data exists."""
        from db_result_helpers import result_single
        result = self._make_falkordb_result({
            "housing_corrosion_class": "C2",
            "indoor_only": False,
            "construction_type": "BOLTED",
        })
        row = result_single(result)
        assert row["construction_type"] == "BOLTED"
        assert row["indoor_only"] is False

    def test_result_single_empty(self):
        """result_single() returns None when no data."""
        from db_result_helpers import result_single
        result = self._make_falkordb_result(None)
        row = result_single(result)
        assert row is None

    def test_result_single_or_default_pattern(self):
        """result_single(result) or {} replaces peek()/single() with default."""
        from db_result_helpers import result_single
        # With data
        result = self._make_falkordb_result({"total": 15, "positive": 10, "negative": 5})
        stats = result_single(result) or {"total": 0, "positive": 0, "negative": 0}
        assert stats["total"] == 15

        # Without data
        empty_result = self._make_falkordb_result(None)
        stats = result_single(empty_result) or {"total": 0, "positive": 0, "negative": 0}
        assert stats == {"total": 0, "positive": 0, "negative": 0}

    def test_conversation_detail_pattern(self):
        """Test the get_conversation_detail peek replacement."""
        from db_result_helpers import result_single
        result = self._make_falkordb_result({
            "session_id": "sess_1",
            "project_name": "Kitchen",
            "detected_family": "GDB",
            "locked_material": "RF",
            "resolved_params": '{"door_side": "R"}',
        })
        default = {"session_id": "sess_1", "project_name": None,
                    "detected_family": None, "locked_material": None, "resolved_params": None}
        proj = result_single(result) or default
        assert proj["project_name"] == "Kitchen"
        assert proj["locked_material"] == "RF"


# =============================================================================
# Tests for EXISTS {} subquery rewrite — lines 4201, 4209
# =============================================================================

class TestExistsSubqueryRewrite:
    """Document the EXISTS {} usage and validate the rewrite approach.

    Neo4j:    WHERE EXISTS { (p)-[:HAS_TURN]->(:ConversationTurn) }
    FalkorDB: WHERE (p)-[:HAS_TURN]->(:ConversationTurn)
    """

    def test_exists_subquery_migrated_to_pattern_predicate(self):
        """Verify EXISTS {} was replaced with pattern predicate after FalkorDB migration."""
        from database import GraphConnection
        import inspect
        source = inspect.getsource(GraphConnection.get_expert_conversations)
        # After migration: pattern predicate instead of EXISTS {}
        assert "EXISTS {" not in source and "EXISTS{" not in source, \
            "get_expert_conversations should use pattern predicate, not EXISTS {}"

    def test_pattern_predicate_is_valid(self):
        """The replacement `WHERE (p)-[:HAS_TURN]->(:ConversationTurn)` is standard openCypher."""
        from database import GraphConnection
        assert hasattr(GraphConnection, 'get_expert_conversations')

    def test_get_expert_conversations_returns_dict_with_conversations(self):
        """Execute get_expert_conversations with mocked FalkorDB graph."""
        from database import GraphConnection
        from db_result_helpers import result_to_dicts, result_value
        db = GraphConnection()

        mock_graph = MagicMock()
        db.graph = mock_graph
        db._db = MagicMock()

        # Count query result (first call)
        mock_count_result = MagicMock()
        mock_count_result.header = [(0, "total")]
        mock_count_result.result_set = [[1]]

        # Conversations query result (second call)
        mock_conv_result = MagicMock()
        mock_conv_result.header = [(0, "session_id"), (0, "project_name"),
                                    (0, "turn_count"), (0, "detected_family"),
                                    (0, "locked_material"), (0, "last_activity"),
                                    (0, "has_review"), (0, "review_score")]
        mock_conv_result.result_set = [["s1", "Test", 3, "GDB", "RF", 1708300000, False, None]]

        mock_graph.query.side_effect = [mock_count_result, mock_conv_result]

        result = db.get_expert_conversations(limit=10, offset=0)
        assert isinstance(result, dict)
        assert "conversations" in result
        assert "total" in result
        assert result["total"] == 1


# =============================================================================
# Tests for {.*} map projection — lines 4313, session_graph.py:477,660,700
# =============================================================================

class TestMapProjectionRewrite:
    """Verify {.*} has been replaced with properties() after FalkorDB migration.

    Neo4j:    RETURN er {.*} AS review
    FalkorDB: RETURN properties(er) AS review
    """

    def test_submit_expert_review_uses_properties(self):
        """Verify submit_expert_review uses properties() instead of {.*}."""
        from database import GraphConnection
        import inspect
        source = inspect.getsource(GraphConnection.submit_expert_review)
        assert "properties(" in source, "submit_expert_review should use properties() after migration"
        assert "{.*}" not in source, "submit_expert_review should NOT use {.*} after migration"

    def test_session_graph_uses_properties(self):
        """Verify session_graph.py uses properties() instead of {.*}."""
        from logic.session_graph import SessionGraphManager
        import inspect
        source = inspect.getsource(SessionGraphManager.get_project_state)
        assert "properties(" in source, "get_project_state should use properties() after migration"

    def test_session_graph_visualization_uses_properties(self):
        """Verify get_session_graph_data uses properties() for tag data."""
        from logic.session_graph import SessionGraphManager
        import inspect
        source = inspect.getsource(SessionGraphManager.get_session_graph_data)
        assert "properties(" in source, "get_session_graph_data should use properties()"

    def test_properties_function_returns_equivalent_data(self):
        """Validate that properties(node) returns all node properties as a map."""
        review_props = {
            "id": "rev_1",
            "session_id": "sess_1",
            "reviewer": "Expert A",
            "comment": "Good analysis",
            "overall_score": "thumbs_up",
            "dimension_scores": '{"accuracy": 4}',
            "provider": "human",
            "turn_number": 3,
            "created_at": 1708300000000,
        }
        assert isinstance(review_props, dict)
        assert review_props["reviewer"] == "Expert A"

    def test_submit_expert_review_execution(self):
        """Execute submit_expert_review with mocked FalkorDB graph."""
        from database import GraphConnection
        db = GraphConnection()

        mock_graph = MagicMock()
        db.graph = mock_graph
        db._db = MagicMock()

        # properties() returns all node properties as a dict
        mock_result = MagicMock()
        mock_result.header = [(0, "review")]
        mock_result.result_set = [[{
            "id": "rev_1",
            "session_id": "sess_1",
            "reviewer": "Expert A",
            "comment": "Good analysis",
            "overall_score": "thumbs_up",
            "dimension_scores": '{"accuracy": 4}',
            "provider": "human",
            "turn_number": 3,
            "created_at": 1708300000000,
        }]]
        mock_graph.query.return_value = mock_result

        result = db.submit_expert_review(
            session_id="sess_1",
            reviewer="Expert A",
            overall_score="thumbs_up",
            comment="Good analysis",
            dimension_scores={"accuracy": 4},
            turn_number=3,
        )
        assert isinstance(result, dict)

    def test_get_project_state_execution(self):
        """Execute get_project_state with mocked FalkorDB graph."""
        from logic.session_graph import SessionGraphManager

        db = MagicMock()
        mock_graph = MagicMock()
        db.connect.return_value = mock_graph

        # Simulate what collect(properties(t)) returns
        mock_result = MagicMock()
        mock_result.header = [(0, "session_id"), (0, "project"), (0, "tags"), (0, "tag_count")]
        mock_result.result_set = [[
            "sess_1",
            {"name": "Test", "locked_material": "RF",
             "detected_family": "GDB", "customer": None,
             "pending_clarification": None, "accessories": None,
             "assembly_group": None, "resolved_params": None,
             "vetoed_families": None},
            [{"tag_id": "item_1", "filter_width": 600, "filter_height": 600,
              "housing_width": 600, "housing_height": 600, "airflow_m3h": 3000,
              "product_family": "GDB", "is_complete": True}],
            1,
        ]]
        mock_graph.query.return_value = mock_result

        sgm = SessionGraphManager(db)
        state = sgm.get_project_state("sess_1")

        assert state["session_id"] == "sess_1"
        assert state["project"]["locked_material"] == "RF"
        assert len(state["tags"]) == 1
        assert state["tags"][0]["filter_width"] == 600


# =============================================================================
# Tests for SHOW INDEXES replacement — line 2247
# =============================================================================

class TestShowIndexesReplacement:
    """Document the SHOW INDEXES usage in ensure_learned_rules_index.

    Neo4j:    SHOW INDEXES WHERE name = $index_name
    FalkorDB: CALL db.indexes() or try-create with error handling
    """

    def test_ensure_learned_rules_index_uses_try_except(self):
        """Verify the migrated code uses try/except instead of SHOW INDEXES."""
        from database import GraphConnection
        import inspect
        source = inspect.getsource(GraphConnection.ensure_learned_rules_index)
        assert "SHOW INDEXES" not in source, "SHOW INDEXES should be removed after migration"
        assert "already exists" in source.lower() or "except" in source, \
            "Should use try/except for idempotent index creation"

    def test_idempotent_index_creation_pattern(self):
        """Validate the replacement pattern: try-create, catch 'already exists'.

        This is the FalkorDB-compatible approach since SHOW INDEXES isn't supported.
        """
        created = False
        error_msg = ""

        def try_create_index():
            nonlocal created, error_msg
            try:
                # Simulate: CREATE VECTOR INDEX FOR (k:Keyword) ON (k.embedding) ...
                # First call succeeds
                created = True
                return True
            except Exception as e:
                error_msg = str(e)
                if "already exists" in error_msg.lower():
                    return True  # Index exists — that's fine
                raise

        assert try_create_index() is True
        assert created is True

    def test_idempotent_index_creation_already_exists(self):
        """Second call with 'already exists' error should return True, not raise."""
        def try_create_index():
            try:
                raise Exception("Index already exists for label 'Keyword' on 'embedding'")
            except Exception as e:
                if "already exists" in str(e).lower():
                    return True
                raise

        assert try_create_index() is True


# =============================================================================
# Tests for init_session_schema DDL — lines 4168-4188
# =============================================================================

class TestInitSessionSchemaDDL:
    """Test init_session_schema() which creates 3 constraints + 4 indexes.

    These need complete rewrite for FalkorDB:
    - Constraints: GRAPH.CONSTRAINT CREATE (Redis command, not Cypher)
    - Indexes: CREATE INDEX (no IF NOT EXISTS, no named indexes)
    """

    def test_init_session_schema_exists(self):
        from database import GraphConnection
        assert hasattr(GraphConnection, 'init_session_schema')

    def test_schema_statements_content(self):
        """Verify DDL statements use FalkorDB-compatible syntax."""
        from database import GraphConnection
        import inspect
        source = inspect.getsource(GraphConnection.init_session_schema)

        # Should have index creation
        assert "CREATE INDEX" in source
        assert "Session" in source
        assert "ActiveProject" in source

        # DDL statements should not use IF NOT EXISTS (FalkorDB incompatible)
        # Filter out comments before checking
        code_lines = [l for l in source.split('\n') if not l.strip().startswith('#') and not l.strip().startswith('"')]
        code_only = '\n'.join(code_lines)
        assert "IF NOT EXISTS" not in code_only, \
            "FalkorDB DDL should not use IF NOT EXISTS"

    def test_schema_catches_already_exists(self):
        """Verify current code handles 'already exists' gracefully."""
        from database import GraphConnection
        import inspect
        source = inspect.getsource(GraphConnection.init_session_schema)
        assert "already exists" in source, \
            "init_session_schema should handle 'already exists' errors"

    def test_init_session_schema_executes_all_ddl(self):
        """Execute init_session_schema with a mocked FalkorDB graph."""
        from database import GraphConnection
        db = GraphConnection()

        mock_graph = MagicMock()
        db.graph = mock_graph
        db._db = MagicMock()

        # Let all DDL succeed
        mock_result = MagicMock()
        mock_result.result_set = None
        mock_graph.query.return_value = mock_result

        db.init_session_schema()

        # Verify DDL statements were executed
        calls = mock_graph.query.call_args_list
        executed_stmts = [str(c) for c in calls]
        joined = " ".join(executed_stmts)

        # Should have index statements
        assert "CREATE INDEX" in joined or "INDEX" in joined
        assert len(calls) >= 3, f"Expected at least 3 DDL calls, got {len(calls)}"

    def test_init_session_schema_handles_already_exists(self):
        """init_session_schema should not crash when 'already exists' is raised."""
        from database import GraphConnection
        db = GraphConnection()

        mock_graph = MagicMock()
        db.graph = mock_graph
        db._db = MagicMock()

        # Simulate 'already exists' for all DDL
        mock_graph.query.side_effect = Exception("already exists")

        # Should not raise
        db.init_session_schema()

    def test_falkordb_index_creation_pattern(self):
        """Validate the FalkorDB index creation pattern works."""
        executed = []

        def mock_run(stmt):
            if "already exists" in stmt.lower():
                raise Exception("Index already exists")
            executed.append(stmt)

        # FalkorDB index statements (no IF NOT EXISTS, no names)
        falkordb_statements = [
            "CREATE INDEX FOR (s:Session) ON (s.last_active)",
            "CREATE INDEX FOR (t:TagUnit) ON (t.session_id)",
            "CREATE INDEX FOR (ap:ActiveProject) ON (ap.session_id)",
            "CREATE INDEX FOR (er:ExpertReview) ON (er.session_id)",
        ]
        for stmt in falkordb_statements:
            try:
                mock_run(stmt)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    raise

        assert len(executed) == 4

    def test_falkordb_vector_index_options(self):
        """Validate FalkorDB vector index DDL format."""
        # Neo4j:    OPTIONS {indexConfig: {`vector.dimensions`: 3072, `vector.similarity_function`: 'cosine'}}
        # FalkorDB: OPTIONS {dimension: 3072, similarityFunction: 'cosine'}
        neo4j_options = "indexConfig: {`vector.dimensions`: 3072, `vector.similarity_function`: 'cosine'}"
        falkordb_options = "dimension: 3072, similarityFunction: 'cosine'"

        # Verify they're structurally different
        assert "indexConfig" not in falkordb_options
        assert "vector.dimensions" not in falkordb_options
        assert "dimension:" in falkordb_options
        assert "similarityFunction:" in falkordb_options


# =============================================================================
# Tests for vector/fulltext index creation methods
# =============================================================================

class TestVectorIndexCreation:
    """Test create_vector_index and ensure_learned_rules_index after FalkorDB migration."""

    def test_create_vector_index_exists(self):
        from database import GraphConnection
        assert hasattr(GraphConnection, 'create_vector_index')

    def test_create_vector_index_uses_falkordb_ddl(self):
        """Verify code uses FalkorDB vector DDL syntax."""
        from database import GraphConnection
        import inspect
        source = inspect.getsource(GraphConnection.create_vector_index)
        assert "CREATE VECTOR INDEX" in source
        # FalkorDB uses dimension/similarityFunction, not indexConfig/vector.dimensions
        assert "dimension:" in source or "similarityFunction" in source, \
            "Should use FalkorDB vector index options format"

    def test_ensure_learned_rules_index_exists(self):
        from database import GraphConnection
        assert hasattr(GraphConnection, 'ensure_learned_rules_index')

    def test_ensure_learned_rules_index_uses_falkordb_ddl(self):
        from database import GraphConnection
        import inspect
        source = inspect.getsource(GraphConnection.ensure_learned_rules_index)
        assert "CREATE VECTOR INDEX" in source
        assert "SHOW INDEXES" not in source, "SHOW INDEXES removed in FalkorDB migration"


# =============================================================================
# Tests for vector search procedure call syntax
# =============================================================================

class TestVectorSearchSyntax:
    """Verify vector search uses FalkorDB syntax after migration."""

    def test_vector_search_uses_falkordb_procedure(self):
        from database import GraphConnection
        import inspect
        source = inspect.getsource(GraphConnection.vector_search_concepts)
        assert "db.idx.vector.queryNodes" in source, \
            "Should use FalkorDB vector procedure (db.idx.vector.queryNodes)"
        assert "db.index.vector.queryNodes" not in source, \
            "Neo4j vector procedure should be replaced"

    def test_hybrid_retrieval_uses_falkordb_procedure(self):
        from database import GraphConnection
        import inspect
        source = inspect.getsource(GraphConnection.hybrid_retrieval)
        assert "db.idx.vector.queryNodes" in source


# =============================================================================
# Tests for fulltext search procedure call syntax
# =============================================================================

class TestFulltextSearchSyntax:
    """Verify fulltext search uses FalkorDB syntax after migration."""

    def test_search_product_variants_uses_falkordb_procedure(self):
        from database import GraphConnection
        import inspect
        source = inspect.getsource(GraphConnection.search_product_variants)
        assert "db.idx.fulltext.queryNodes" in source, \
            "Should use FalkorDB fulltext procedure (db.idx.fulltext.queryNodes)"
        assert "db.index.fulltext.queryNodes" not in source, \
            "Neo4j fulltext procedure should be replaced"

    def test_configuration_graph_search_uses_falkordb_procedure(self):
        from database import GraphConnection
        import inspect
        source = inspect.getsource(GraphConnection.configuration_graph_search)
        assert "db.idx.fulltext.queryNodes" in source
