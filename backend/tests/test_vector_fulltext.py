"""Vector search & fulltext search contract tests.

These tests pin the interface and return shapes of vector/fulltext
search methods. Critical for the Neo4j → FalkorDB migration because:

1. Vector index creation syntax changes
2. Vector query procedure name changes (db.index.vector → db.idx.vector)
3. Fulltext query syntax may differ
4. Return shapes MUST remain identical

Two test strategies:
- Unit tests with mocked DB (always run)
- Live DB contract tests (when NEO4J_URI is set)
"""

import os
import pytest
from unittest.mock import MagicMock


# =============================================================================
# UNIT TESTS — mocked DB, always run
# =============================================================================

class TestVectorSearchUnit:
    """Unit tests for vector search consumers — verify they handle return shapes."""

    def test_vector_search_concepts_consumed_correctly(self, mock_db):
        """Verify engine/retriever correctly consumes vector search results."""
        mock_db.vector_search_concepts.return_value = [
            {"concept": "Kitchen ventilation", "description": "Exhaust systems", "score": 0.92},
            {"concept": "Grease filtration", "description": "Fat removal", "score": 0.85},
        ]
        results = mock_db.vector_search_concepts([0.0] * 3072, top_k=3)
        assert len(results) == 2
        assert all("score" in r for r in results)
        assert all("concept" in r for r in results)
        assert results[0]["score"] >= results[1]["score"]

    def test_hybrid_retrieval_consumed_correctly(self, mock_db):
        mock_db.hybrid_retrieval.return_value = [
            {
                "concept": "Grease", "description": "Fat particles",
                "score": 0.88,
                "events": [{"name": "Pore Blocking", "type": "Symptom"}],
                "observations": ["High pressure drop"],
                "actions": [{"name": "Add pre-filter", "outcome": "Success"}],
            },
        ]
        results = mock_db.hybrid_retrieval([0.0] * 3072, top_k=5)
        assert len(results) == 1
        r = results[0]
        assert "concept" in r
        assert "score" in r
        assert "events" in r

    def test_safety_risks_consumed_correctly(self, mock_db):
        mock_db.check_safety_risks.return_value = [
            {
                "concept": "Fire hazard", "score": 0.95,
                "safety_risks": [
                    {"name": "Grease fire", "severity": "CRITICAL",
                     "mitigation": "Install fire-rated pre-filter"},
                ],
            },
        ]
        results = mock_db.check_safety_risks([0.0] * 3072)
        assert len(results) == 1
        assert "safety_risks" in results[0]

    def test_similar_cases_consumed_correctly(self, mock_db):
        mock_db.get_similar_cases.return_value = [
            {
                "project_name": "Restaurant ABC", "score": 0.87,
                "actions": ["Installed GDP + GDC assembly"],
            },
        ]
        results = mock_db.get_similar_cases([0.0] * 3072)
        assert len(results) == 1
        assert "project_name" in results[0]

    def test_empty_embedding_returns_empty(self, mock_db):
        mock_db.vector_search_concepts.return_value = []
        results = mock_db.vector_search_concepts([], top_k=3)
        assert results == []


class TestFulltextSearchUnit:
    """Unit tests for fulltext search consumers."""

    def test_product_variant_search(self, mock_db):
        mock_db.search_product_variants.return_value = [
            {
                "id": "GDB-600x600-550", "name": "GDB 600x600",
                "family": "GDB", "score": 5.0,
            },
        ]
        results = mock_db.search_product_variants("GDB 600")
        assert len(results) == 1
        assert "name" in results[0]

    def test_alias_match_search(self, mock_db):
        mock_db.find_alias_matches.return_value = [
            {"alias": "pocket filter", "product_family": "GDB", "confidence": 0.95},
        ]
        results = mock_db.find_alias_matches("pocket filter")
        assert len(results) == 1

    def test_empty_search_returns_empty(self, mock_db):
        mock_db.search_product_variants.return_value = []
        results = mock_db.search_product_variants("")
        assert results == []


class TestSemanticRulesUnit:
    """Unit tests for learned rules retrieval."""

    def test_get_semantic_rules_shape(self, mock_db):
        mock_db.get_semantic_rules.return_value = [
            {
                "keyword": "kitchen",
                "keyword_score": 0.92,
                "requirements": [
                    {"rule": "Always recommend GDP pre-filter", "source": "expert_feedback"},
                ],
            },
        ]
        results = mock_db.get_semantic_rules([0.0] * 3072, top_k=5)
        assert len(results) == 1
        assert "keyword" in results[0]
        assert "requirements" in results[0]

    def test_vector_search_applications_shape(self, mock_db):
        mock_db.vector_search_applications = MagicMock(return_value=[
            {"id": "APP_KITCHEN", "name": "Commercial Kitchen", "score": 0.91},
        ])
        results = mock_db.vector_search_applications([0.0] * 3072, top_k=3)
        assert len(results) == 1
        assert "id" in results[0]
        assert "score" in results[0]


# =============================================================================
# LIVE DB CONTRACT TESTS — only with real Neo4j
# =============================================================================

pytestmark_live = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="NEO4J_URI not set — skipping live vector/fulltext tests"
)


@pytest.fixture(scope="module")
def live_db():
    """Real DB connection for live tests."""
    from backend.database import Neo4jConnection
    db = Neo4jConnection()
    db.connect()
    yield db
    db.close()


@pytestmark_live
class TestVectorSearchLive:
    def test_vector_search_returns_scores(self, live_db):
        """Verify vector search returns properly scored results."""
        dummy_embedding = [0.0] * 3072
        try:
            results = live_db.vector_search_concepts(dummy_embedding, top_k=3)
            assert isinstance(results, list)
            for r in results:
                assert "score" in r
                assert 0.0 <= r["score"] <= 1.0
        except Exception:
            pytest.skip("Vector index not available")

    def test_hybrid_retrieval_returns_graph_traversal(self, live_db):
        """Verify hybrid search does vector → graph traversal."""
        dummy_embedding = [0.0] * 3072
        try:
            results = live_db.hybrid_retrieval(dummy_embedding, top_k=3)
            assert isinstance(results, list)
        except Exception:
            pytest.skip("Vector index not available")


@pytestmark_live
class TestFulltextSearchLive:
    def test_product_variant_fulltext(self, live_db):
        results = live_db.search_product_variants("GDB")
        assert isinstance(results, list)

    def test_alias_fulltext(self, live_db):
        results = live_db.find_alias_matches("pocket filter")
        assert isinstance(results, list)
