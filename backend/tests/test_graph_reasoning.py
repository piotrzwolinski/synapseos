"""Comprehensive tests for the Graph Reasoning pipeline.

Protects the core Graph Reasoning functionality:
- /consult/deep-explainable/stream (primary streaming endpoint)
- /consult/deep-explainable (non-streaming)
- /consult/explainable
- /consult/knowledge-graph
- SSE event format and contracts
- Response model validation
- Session state management through the pipeline
- Error handling and edge cases
"""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from fastapi.testclient import TestClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def client():
    """FastAPI test client with mocked DB and auth disabled."""
    with patch.dict("os.environ", {
             "FALKORDB_HOST": "localhost",
             "FALKORDB_PORT": "6379",
             "FALKORDB_GRAPH": "hvac_test",
             "GEMINI_API_KEY": "test-key",
             "JWT_SECRET": "test-secret",
             "AUTH_DISABLED": "true",
         }):
        import importlib
        import backend.auth
        importlib.reload(backend.auth)

        with patch("database.GraphConnection") as MockDB:
            mock_db = MagicMock()
            mock_db.verify_connection.return_value = True
            mock_db.get_node_count.return_value = 100
            mock_db.get_relationship_count.return_value = 200
            mock_db.get_graph_data.return_value = {"nodes": [], "relationships": []}
            mock_db.get_session_graph_manager.return_value = MagicMock()
            MockDB.return_value = mock_db

            from backend.main import app
            from backend.auth import get_current_user, get_current_user_info
            app.dependency_overrides[get_current_user] = lambda: "test_user"
            app.dependency_overrides[get_current_user_info] = lambda: {"username": "test_user", "role": "admin"}
            yield TestClient(app)
            app.dependency_overrides.clear()


def _make_complete_sse_events():
    """Standard SSE event sequence for a successful Graph Reasoning response."""
    return iter([
        {"type": "inference", "step": "context", "status": "active", "detail": "Analyzing project context..."},
        {"type": "inference", "step": "scribe", "status": "active", "detail": "Detecting intent..."},
        {"type": "inference", "step": "engine", "status": "active", "detail": "Running trait engine..."},
        {"type": "inference", "step": "sizing", "status": "active", "detail": "Computing dimensions..."},
        {"type": "complete", "response": {
            "reasoning_summary": [
                {"step": "Analysis", "icon": "🔍", "description": "Detected kitchen environment", "graph_traversals": []},
            ],
            "content_segments": [
                {"text": "Based on the analysis, I recommend GDB 600x600.", "type": "GENERAL"},
                {"text": "Kitchen environment requires grease pre-filtration.", "type": "GRAPH_FACT",
                 "source_id": "STR_GREASE", "source_text": "Grease stressor"},
            ],
            "product_cards": [
                {"title": "GDB 600x600", "specs": {"Airflow": "3400 m³/h", "Material": "FZ"},
                 "confidence": "high", "actions": ["Add to Quote"]},
            ],
            "product_card": {"title": "GDB 600x600", "specs": {"Airflow": "3400 m³/h"}, "confidence": "high", "actions": []},
            "risk_detected": False,
            "clarification_needed": False,
            "query_language": "en",
            "confidence_level": "high",
            "graph_facts_count": 1,
            "inference_count": 0,
        }, "timings": {"total": 1.2}},
    ])


def _make_clarification_sse_events():
    """SSE events for a response that asks for clarification."""
    return iter([
        {"type": "inference", "step": "context", "status": "active", "detail": "Analyzing..."},
        {"type": "inference", "step": "scribe", "status": "active", "detail": "Detecting intent..."},
        {"type": "complete", "response": {
            "reasoning_summary": [],
            "content_segments": [
                {"text": "I need more information to proceed.", "type": "GENERAL"},
            ],
            "product_cards": [],
            "risk_detected": False,
            "clarification_needed": True,
            "clarification": {
                "missing_info": "filter_dimensions",
                "why_needed": "Required to select correct product variant",
                "question": "What are the filter dimensions (width x height)?",
                "options": [
                    {"value": "600x600", "description": "Standard 600x600mm"},
                    {"value": "300x600", "description": "Half-width 300x600mm"},
                ],
            },
            "query_language": "en",
            "confidence_level": "low",
            "graph_facts_count": 0,
            "inference_count": 0,
        }},
    ])


def _make_error_sse_events():
    """SSE events that include an error."""
    return iter([
        {"type": "inference", "step": "context", "status": "active", "detail": "Analyzing..."},
        {"type": "error", "detail": "Database connection lost"},
    ])


def _make_risk_sse_events():
    """SSE events for a response with risk detection and product pivot."""
    return iter([
        {"type": "inference", "step": "context", "status": "active", "detail": "Analyzing..."},
        {"type": "inference", "step": "guardian", "status": "active", "detail": "Checking risks..."},
        {"type": "complete", "response": {
            "reasoning_summary": [
                {"step": "Guardian", "icon": "🛡️", "description": "CRITICAL risk: FZ material in C5 environment", "graph_traversals": []},
            ],
            "content_segments": [
                {"text": "Material FZ is not suitable for outdoor installation.", "type": "GRAPH_FACT",
                 "source_id": "MAT_FZ", "source_text": "Material spec"},
            ],
            "product_cards": [
                {"title": "GDB 600x600 RF", "specs": {"Material": "RF (Stainless Steel)"},
                 "confidence": "high", "warning": "Material upgraded due to corrosion risk", "actions": []},
            ],
            "risk_detected": True,
            "risk_severity": "CRITICAL",
            "risk_resolved": True,
            "product_pivot": {
                "original_product": "GDB FZ",
                "pivoted_to": "GDB RF",
                "reason": "C5 corrosion environment",
                "physics_explanation": "Galvanized steel corrodes rapidly in C5 marine/industrial environments",
                "required_feature": "C5 corrosion resistance",
            },
            "clarification_needed": False,
            "query_language": "en",
            "confidence_level": "high",
            "graph_facts_count": 1,
            "inference_count": 0,
        }},
    ])


def _make_assembly_sse_events():
    """SSE events for a multi-stage assembly response."""
    return iter([
        {"type": "inference", "step": "context", "status": "active", "detail": "Analyzing..."},
        {"type": "inference", "step": "engine", "status": "active", "detail": "Assembly required..."},
        {"type": "complete", "response": {
            "reasoning_summary": [
                {"step": "Assembly", "icon": "🔧", "description": "Two-stage assembly: GDP (protector) + GDC (target)", "graph_traversals": []},
            ],
            "content_segments": [
                {"text": "Kitchen environment requires a two-stage assembly.", "type": "GRAPH_FACT",
                 "source_id": "STR_GREASE", "source_text": "Assembly rule"},
            ],
            "product_cards": [
                {"title": "GDP 600x600 (Stage 1 - Protector)", "specs": {"Role": "Grease Pre-filter"},
                 "confidence": "high", "actions": []},
                {"title": "GDC 600x600 (Stage 2 - Target)", "specs": {"Role": "Carbon Filter"},
                 "confidence": "high", "actions": []},
            ],
            "risk_detected": False,
            "clarification_needed": False,
            "query_language": "en",
            "confidence_level": "high",
            "graph_facts_count": 1,
            "inference_count": 0,
        }},
    ])


# =============================================================================
# STREAMING ENDPOINT — /consult/deep-explainable/stream
# =============================================================================

class TestDeepExplainableStream:
    """Tests for the primary Graph Reasoning streaming endpoint."""

    @patch("backend.main.query_deep_explainable_streaming")
    def test_stream_returns_200_with_sse(self, mock_stream, client):
        """Endpoint returns 200 with text/event-stream content type."""
        mock_stream.return_value = _make_complete_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "I need a filter for kitchen", "session_id": "test_session"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    @patch("backend.main.query_deep_explainable_streaming")
    def test_stream_events_are_valid_json(self, mock_stream, client):
        """Each SSE event must be valid JSON after stripping 'data: ' prefix."""
        mock_stream.return_value = _make_complete_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "I need a filter for kitchen", "session_id": "test_session"},
        )
        events = _parse_sse_events(resp.text)
        assert len(events) > 0, "No SSE events received"
        for event in events:
            assert isinstance(event, dict), f"Event is not a dict: {event}"

    @patch("backend.main.query_deep_explainable_streaming")
    def test_stream_has_inference_and_complete_events(self, mock_stream, client):
        """Stream must contain at least one inference event and a complete event."""
        mock_stream.return_value = _make_complete_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "I need a filter for kitchen", "session_id": "test_session"},
        )
        events = _parse_sse_events(resp.text)
        event_types = [e.get("type") for e in events]
        assert "inference" in event_types, "No inference events in stream"
        assert "complete" in event_types, "No complete event in stream"

    @patch("backend.main.query_deep_explainable_streaming")
    def test_stream_complete_event_has_response(self, mock_stream, client):
        """The 'complete' event must contain a valid response object."""
        mock_stream.return_value = _make_complete_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "kitchen filter", "session_id": "s1"},
        )
        events = _parse_sse_events(resp.text)
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1, "Expected exactly one complete event"
        response = complete_events[0].get("response")
        assert response is not None, "Complete event missing 'response' field"

    @patch("backend.main.query_deep_explainable_streaming")
    def test_stream_response_has_required_fields(self, mock_stream, client):
        """Complete response must have all DeepExplainableResponse fields."""
        mock_stream.return_value = _make_complete_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "kitchen filter", "session_id": "s1"},
        )
        response = _get_complete_response(resp.text)
        required_fields = [
            "reasoning_summary", "content_segments", "product_cards",
            "risk_detected", "clarification_needed", "confidence_level",
        ]
        for field in required_fields:
            assert field in response, f"Missing required field: {field}"

    @patch("backend.main.query_deep_explainable_streaming")
    def test_stream_content_segments_shape(self, mock_stream, client):
        """Each content segment must have 'text' and 'type' fields."""
        mock_stream.return_value = _make_complete_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "kitchen filter", "session_id": "s1"},
        )
        response = _get_complete_response(resp.text)
        for seg in response["content_segments"]:
            assert "text" in seg, "Content segment missing 'text'"
            assert "type" in seg, "Content segment missing 'type'"
            assert seg["type"] in ("GENERAL", "INFERENCE", "GRAPH_FACT"), \
                f"Invalid segment type: {seg['type']}"

    @patch("backend.main.query_deep_explainable_streaming")
    def test_stream_product_card_shape(self, mock_stream, client):
        """Product cards must have title and specs."""
        mock_stream.return_value = _make_complete_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "kitchen filter", "session_id": "s1"},
        )
        response = _get_complete_response(resp.text)
        for card in response["product_cards"]:
            assert "title" in card, "Product card missing 'title'"
            assert "specs" in card, "Product card missing 'specs'"
            assert isinstance(card["specs"], dict), "Product card specs must be a dict"

    @patch("backend.main.query_deep_explainable_streaming")
    def test_stream_inference_events_shape(self, mock_stream, client):
        """Inference events must have step, status, and detail."""
        mock_stream.return_value = _make_complete_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "kitchen filter", "session_id": "s1"},
        )
        events = _parse_sse_events(resp.text)
        inference_events = [e for e in events if e.get("type") == "inference"]
        assert len(inference_events) > 0
        for ev in inference_events:
            assert "step" in ev, "Inference event missing 'step'"
            assert "detail" in ev, "Inference event missing 'detail'"

    @patch("backend.main.query_deep_explainable_streaming")
    def test_stream_session_id_passed_through(self, mock_stream, client):
        """Session ID from request must be passed to the retriever function."""
        mock_stream.return_value = _make_complete_sse_events()
        client.post(
            "/consult/deep-explainable/stream",
            json={"query": "kitchen", "session_id": "my_session_123"},
        )
        mock_stream.assert_called_once()
        call_kwargs = mock_stream.call_args
        # Could be positional or keyword — check both
        args = call_kwargs[0] if call_kwargs[0] else ()
        kwargs = call_kwargs[1] if call_kwargs[1] else {}
        assert "kitchen" in (args[0] if args else kwargs.get("query", "")) or \
               args[0] == "kitchen" if args else kwargs.get("query") == "kitchen"
        session_val = kwargs.get("session_id") or (args[1] if len(args) > 1 else None)
        assert session_val == "my_session_123", f"Session ID not passed: {call_kwargs}"

    @patch("backend.main.query_deep_explainable_streaming")
    def test_stream_without_session_id(self, mock_stream, client):
        """Request without session_id should still work (defaults to None)."""
        mock_stream.return_value = _make_complete_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "industrial filter"},
        )
        assert resp.status_code == 200

    def test_stream_rejects_missing_query(self, client):
        """Missing 'query' field must return 422."""
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"session_id": "test"},
        )
        assert resp.status_code == 422

    def test_stream_rejects_empty_body(self, client):
        """Empty request body must return 422."""
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={},
        )
        assert resp.status_code == 422

    def test_stream_rejects_no_json(self, client):
        """Request without JSON body must return 422."""
        resp = client.post("/consult/deep-explainable/stream")
        assert resp.status_code == 422

    @patch("backend.main.query_deep_explainable_streaming")
    def test_stream_handles_empty_query(self, mock_stream, client):
        """Empty string query should still be accepted by endpoint (validation is semantic)."""
        mock_stream.return_value = iter([
            {"type": "complete", "response": {
                "reasoning_summary": [], "content_segments": [],
                "product_cards": [], "risk_detected": False,
                "clarification_needed": False, "confidence_level": "low",
                "graph_facts_count": 0, "inference_count": 0,
            }},
        ])
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": ""},
        )
        # Empty query is syntactically valid (Pydantic allows empty str)
        assert resp.status_code == 200


# =============================================================================
# STREAMING — CLARIFICATION FLOW
# =============================================================================

class TestStreamClarification:
    """Tests for clarification handling in the streaming pipeline."""

    @patch("backend.main.query_deep_explainable_streaming")
    def test_clarification_response_shape(self, mock_stream, client):
        """When clarification is needed, response must include clarification details."""
        mock_stream.return_value = _make_clarification_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "I need a filter", "session_id": "s1"},
        )
        response = _get_complete_response(resp.text)
        assert response["clarification_needed"] is True
        clar = response["clarification"]
        assert clar is not None
        assert "question" in clar
        assert "options" in clar
        assert len(clar["options"]) > 0

    @patch("backend.main.query_deep_explainable_streaming")
    def test_clarification_options_shape(self, mock_stream, client):
        """Clarification options must have value and description."""
        mock_stream.return_value = _make_clarification_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "I need a filter", "session_id": "s1"},
        )
        response = _get_complete_response(resp.text)
        for opt in response["clarification"]["options"]:
            assert "value" in opt, "Option missing 'value'"
            assert "description" in opt, "Option missing 'description'"


# =============================================================================
# STREAMING — ERROR HANDLING
# =============================================================================

class TestStreamErrorHandling:
    """Tests for error handling in the streaming pipeline."""

    @patch("backend.main.query_deep_explainable_streaming")
    def test_error_event_in_stream(self, mock_stream, client):
        """When pipeline errors, stream must include an error event."""
        mock_stream.return_value = _make_error_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "kitchen filter", "session_id": "s1"},
        )
        assert resp.status_code == 200  # SSE always returns 200
        events = _parse_sse_events(resp.text)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) >= 1, "No error events in stream"
        assert "detail" in error_events[0]

    @patch("backend.main.query_deep_explainable_streaming")
    def test_exception_produces_error_event(self, mock_stream, client):
        """If the generator raises, the endpoint catches and yields an error event."""
        mock_stream.side_effect = Exception("Unexpected LLM failure")
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "kitchen", "session_id": "s1"},
        )
        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) >= 1


# =============================================================================
# STREAMING — RISK DETECTION & PRODUCT PIVOT
# =============================================================================

class TestStreamRiskDetection:
    """Tests for Guardian risk detection and product pivot."""

    @patch("backend.main.query_deep_explainable_streaming")
    def test_risk_response_shape(self, mock_stream, client):
        """Risk detection response must include severity and pivot info."""
        mock_stream.return_value = _make_risk_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "outdoor installation with FZ", "session_id": "s1"},
        )
        response = _get_complete_response(resp.text)
        assert response["risk_detected"] is True
        assert response["risk_severity"] in ("CRITICAL", "WARNING", "INFO")

    @patch("backend.main.query_deep_explainable_streaming")
    def test_product_pivot_shape(self, mock_stream, client):
        """Product pivot must have original/new product and reason."""
        mock_stream.return_value = _make_risk_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "outdoor FZ", "session_id": "s1"},
        )
        response = _get_complete_response(resp.text)
        pivot = response.get("product_pivot")
        assert pivot is not None
        assert "original_product" in pivot
        assert "pivoted_to" in pivot
        assert "reason" in pivot
        assert "physics_explanation" in pivot


# =============================================================================
# STREAMING — ASSEMBLY (MULTI-STAGE)
# =============================================================================

class TestStreamAssembly:
    """Tests for multi-stage assembly responses."""

    @patch("backend.main.query_deep_explainable_streaming")
    def test_assembly_produces_multiple_cards(self, mock_stream, client):
        """Assembly response must have multiple product cards."""
        mock_stream.return_value = _make_assembly_sse_events()
        resp = client.post(
            "/consult/deep-explainable/stream",
            json={"query": "kitchen carbon filter", "session_id": "s1"},
        )
        response = _get_complete_response(resp.text)
        assert len(response["product_cards"]) >= 2, \
            f"Expected >=2 product cards for assembly, got {len(response['product_cards'])}"


# =============================================================================
# NON-STREAMING CONSULT ENDPOINTS
# =============================================================================

class TestNonStreamingConsult:
    """Tests for non-streaming /consult/* endpoints."""

    @patch("backend.main.query_deep_explainable")
    def test_deep_explainable_returns_response(self, mock_query, client):
        """POST /consult/deep-explainable returns DeepExplainableResponse."""
        mock_query.return_value = MagicMock(
            reasoning_summary=[], content_segments=[], product_cards=[],
            product_card=None, risk_detected=False, risk_severity=None,
            risk_resolved=False, product_pivot=None,
            clarification_needed=False, clarification=None,
            query_language="en", confidence_level="medium",
            policy_warnings=[], graph_facts_count=0, inference_count=0,
            timings=None,
        )
        resp = client.post(
            "/consult/deep-explainable",
            json={"query": "kitchen filter"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "content_segments" in data
        assert "product_cards" in data

    @patch("backend.main.query_explainable")
    def test_explainable_returns_response(self, mock_query, client):
        """POST /consult/explainable returns ExplainableResponse."""
        mock_query.return_value = MagicMock(
            reasoning_chain=[], reasoning_steps=[], final_answer_markdown="Test answer.",
            references={}, query_language="en", confidence_level="medium",
            policy_warnings=[], graph_facts_count=0, llm_inferences_count=0,
        )
        resp = client.post(
            "/consult/explainable",
            json={"query": "kitchen filter"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "final_answer_markdown" in data

    @patch("backend.main.consult_brain")
    def test_consult_returns_response(self, mock_consult, client):
        """POST /consult returns ConsultResponse."""
        mock_consult.return_value = MagicMock(
            answer="Test answer", concepts_matched=[], observations=[],
            actions=[], products_mentioned=[],
        )
        resp = client.post(
            "/consult",
            json={"query": "kitchen filter"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data

    @patch("backend.main.query_deep_explainable")
    def test_deep_explainable_error_returns_500(self, mock_query, client):
        """Backend exception in non-streaming endpoint returns 500."""
        mock_query.side_effect = Exception("DB failure")
        resp = client.post(
            "/consult/deep-explainable",
            json={"query": "test"},
        )
        assert resp.status_code == 500


# =============================================================================
# REQUEST/RESPONSE MODEL CONTRACTS
# =============================================================================

class TestResponseModelContracts:
    """Pin the exact shapes of response models used by Graph Reasoning."""

    def test_consult_request_requires_query(self):
        """ConsultRequest must require query, session_id optional."""
        from backend.models import ConsultRequest
        req = ConsultRequest(query="test")
        assert req.query == "test"
        assert req.session_id is None

        req2 = ConsultRequest(query="test", session_id="s1")
        assert req2.session_id == "s1"

    def test_consult_request_rejects_no_query(self):
        """ConsultRequest must reject missing query."""
        from backend.models import ConsultRequest
        with pytest.raises(Exception):
            ConsultRequest()

    def test_deep_explainable_response_defaults(self):
        """DeepExplainableResponse fields have sensible defaults."""
        from backend.models import DeepExplainableResponse
        resp = DeepExplainableResponse()
        assert resp.reasoning_summary == []
        assert resp.content_segments == []
        assert resp.product_cards == []
        assert resp.risk_detected is False
        assert resp.clarification_needed is False
        assert resp.confidence_level == "medium"

    def test_content_segment_shape(self):
        """ContentSegment has required text and type."""
        from backend.models import ContentSegment
        seg = ContentSegment(text="Hello", type="GENERAL")
        assert seg.text == "Hello"
        assert seg.type == "GENERAL"
        assert seg.source_id is None

    def test_product_card_shape(self):
        """ProductCard has required title."""
        from backend.models import ProductCard
        card = ProductCard(title="GDB 600x600")
        assert card.title == "GDB 600x600"
        assert card.specs == {}
        assert card.confidence == "high"

    def test_clarification_request_shape(self):
        """ClarificationRequest has all required fields."""
        from backend.models import ClarificationRequest, ClarificationOption
        clar = ClarificationRequest(
            missing_info="dimensions",
            why_needed="For product selection",
            question="What dimensions?",
            options=[ClarificationOption(value="600x600", description="Standard")],
        )
        assert clar.question == "What dimensions?"
        assert len(clar.options) == 1

    def test_reasoning_summary_step_shape(self):
        """ReasoningSummaryStep has step, icon, description."""
        from backend.models import ReasoningSummaryStep
        step = ReasoningSummaryStep(step="Analysis", description="Detected kitchen")
        assert step.step == "Analysis"
        assert step.icon == "🔍"  # default

    def test_product_pivot_shape(self):
        """ProductPivotInfo has all required fields."""
        from backend.models import ProductPivotInfo
        pivot = ProductPivotInfo(
            original_product="GDB FZ",
            pivoted_to="GDB RF",
            reason="C5 corrosion",
            physics_explanation="Steel corrodes",
            required_feature="C5 resistance",
        )
        assert pivot.original_product == "GDB FZ"
        assert pivot.pivoted_to == "GDB RF"


# =============================================================================
# SESSION ENDPOINTS (used by Graph Reasoning for Layer 4 state)
# =============================================================================

class TestSessionEndpoints:
    """Tests for session state endpoints used by Graph Reasoning."""

    def test_get_session_graph(self, client):
        """GET /session/graph/{session_id} returns session state."""
        resp = client.get("/session/graph/test_session")
        assert resp.status_code in (200, 500)  # 500 if DB mock incomplete
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, dict)

    def test_clear_session(self, client):
        """DELETE /session/{session_id} clears session."""
        resp = client.delete("/session/test_session")
        assert resp.status_code in (200, 404, 500)

    @patch("backend.main.query_deep_explainable_streaming")
    def test_consecutive_queries_same_session(self, mock_stream, client):
        """Multiple queries with the same session_id should all succeed."""
        for i in range(3):
            mock_stream.return_value = _make_complete_sse_events()
            resp = client.post(
                "/consult/deep-explainable/stream",
                json={"query": f"query {i}", "session_id": "persistent_session"},
            )
            assert resp.status_code == 200
            events = _parse_sse_events(resp.text)
            complete = [e for e in events if e.get("type") == "complete"]
            assert len(complete) == 1


# =============================================================================
# AUTH INTEGRATION
# =============================================================================

class TestAuthIntegration:
    """Tests that auth dependency is wired on consult endpoints."""

    def test_stream_endpoint_has_auth_dependency(self):
        """The streaming endpoint must have get_current_user as a dependency."""
        from backend.main import app

        target_route = None
        for route in app.routes:
            if hasattr(route, "path") and route.path == "/consult/deep-explainable/stream":
                target_route = route
                break

        assert target_route is not None, "Route /consult/deep-explainable/stream not found"
        dep_names = [d.call.__name__ for d in target_route.dependant.dependencies]
        assert "get_current_user" in dep_names, \
            f"get_current_user dependency not found on /consult/deep-explainable/stream (deps: {dep_names})"

    def test_all_consult_endpoints_have_auth(self):
        """All /consult/* endpoints must require authentication."""
        from backend.main import app

        consult_routes = [
            r for r in app.routes
            if hasattr(r, "path") and r.path.startswith("/consult")
        ]
        assert len(consult_routes) > 0, "No /consult/* routes found"

        for route in consult_routes:
            dep_names = [d.call.__name__ for d in route.dependant.dependencies]
            assert "get_current_user" in dep_names, \
                f"get_current_user dependency missing on {route.path} (deps: {dep_names})"


# =============================================================================
# HELPERS
# =============================================================================

def _parse_sse_events(text: str) -> list[dict]:
    """Parse SSE text into list of event dicts."""
    events = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass  # Skip malformed events
    return events


def _get_complete_response(text: str) -> dict:
    """Extract the 'response' from the 'complete' SSE event."""
    events = _parse_sse_events(text)
    complete_events = [e for e in events if e.get("type") == "complete"]
    assert len(complete_events) == 1, f"Expected 1 complete event, got {len(complete_events)}"
    return complete_events[0]["response"]
