import json
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from database import db
from chat import chatbot
from ingestor import ingest_case, ingest_email_thread_image, ingest_email_thread_text
from ingestor_docs import analyze_document_schema, ingest_document
from retriever import consult_brain, query_explainable, query_deep_explainable
from models import IngestRequest, ConsultRequest, ConsultResponse, ProductListResponse, ExplainableResponse, DeepExplainableResponse, GraphNeighborhoodResponse
from config_loader import (
    get_ui_config,
    get_config,
    get_available_domains,
    get_current_domain,
    set_current_domain,
    get_domain_config_summary,
    reload_config
)

app = FastAPI(title="Graph Chatbot API")

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for UI prototypes
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

class GraphStats(BaseModel):
    nodes: int
    relationships: int
    connected: bool

@app.get("/")
async def root():
    return {"message": "Graph Chatbot API is running"}


@app.get("/ui/explainable")
async def explainable_ui():
    """Serve the Explainable AI chat interface."""
    html_path = STATIC_DIR / "explainable-chat.html"
    if html_path.exists():
        return FileResponse(html_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="UI not found")


@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """Send a message to the chatbot and get a response"""
    try:
        response = chatbot.send_message(message.message)
        return ChatResponse(response=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream(message: ChatMessage):
    """Stream chat with reasoning steps via Server-Sent Events"""

    def generate():
        total_start = time.time()
        graph_context = ""
        prompt_preview = ""
        retrieval_time = 0
        safety_risks = None

        # Stream reasoning steps
        retrieval_start = time.time()
        for step_data in chatbot._get_graph_context_with_steps(message.message):
            if "_context" in step_data:
                graph_context = step_data["_context"]
                prompt_preview = step_data.get("_prompt_preview", "")
                retrieval_time = time.time() - retrieval_start
            elif "_safety_risks" in step_data:
                # SAFETY PATH: Hazards detected - bypass normal processing
                safety_risks = step_data["_safety_risks"]
                retrieval_time = time.time() - retrieval_start
            else:
                yield f"data: {json.dumps(step_data)}\n\n"

        # PRIORITY: If safety risks detected, force safety_guard response
        if safety_risks:
            try:
                # Generate forced safety_guard widget response
                response = chatbot.generate_safety_response(message.message, safety_risks)
                total_time = time.time() - total_start
                print(f"🚨 SAFETY RESPONSE: {len(safety_risks)} risks, total={total_time:.2f}s")
                yield f"data: {json.dumps({'step': 'thinking', 'status': 'done', 'detail': '⚠️ Safety response generated'})}\n\n"
                yield f"data: {json.dumps({'step': 'complete', 'response': response})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'step': 'error', 'status': 'error', 'detail': str(e)})}\n\n"
            return  # Exit early - don't do normal response

        # Send prompt preview before final response
        if prompt_preview:
            yield f"data: {json.dumps({'step': 'prompt', 'prompt_preview': prompt_preview})}\n\n"

        # Now generate the final response (normal path)
        try:
            response = chatbot.send_message_with_context(message.message, graph_context)
            total_time = time.time() - total_start
            print(f"⏱️ TIMING SUMMARY: retrieval={retrieval_time:.2f}s, total={total_time:.2f}s")
            yield f"data: {json.dumps({'step': 'thinking', 'status': 'done', 'detail': 'Response ready'})}\n\n"
            yield f"data: {json.dumps({'step': 'complete', 'response': response})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'step': 'error', 'status': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/chat/clear")
async def clear_chat():
    """Clear the chat history"""
    chatbot.clear_history()
    return {"message": "Chat history cleared"}

@app.get("/chat/history")
async def get_chat_history():
    """Get the chat history"""
    return {"messages": chatbot.get_history()}

@app.get("/chat/model")
async def get_model_info():
    """Get current model information"""
    return chatbot.get_model_info()

@app.post("/chat/model")
async def set_model(request: dict):
    """Set the Gemini model to use"""
    model = request.get("model", "").strip()
    valid_models = ["gemini-3-pro-preview", "gemini-3-flash-preview"]
    if model not in valid_models:
        raise HTTPException(status_code=400, detail=f"Invalid model. Must be one of: {valid_models}")
    chatbot.model_name = model
    return {"model": model, "message": f"Model set to {model}"}

@app.post("/chat/thinking")
async def set_thinking_level(request: dict):
    """Set the thinking level for the model (Gemini 3 Pro supports: low, high)"""
    level = request.get("level", "high").lower()
    valid_levels = ["low", "high"]
    if level not in valid_levels:
        raise HTTPException(status_code=400, detail=f"Invalid level. Must be one of: {valid_levels}")
    chatbot.thinking_level = level
    return {"thinking_level": level, "message": f"Thinking level set to {level}"}

@app.get("/graph/stats", response_model=GraphStats)
async def get_graph_stats():
    """Get statistics about the graph database"""
    try:
        connected = db.verify_connection()
        nodes = db.get_node_count()
        relationships = db.get_relationship_count()
        return GraphStats(nodes=nodes, relationships=relationships, connected=connected)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/graph/clear")
async def clear_graph():
    """Clear all nodes and relationships from the graph"""
    try:
        db.clear_graph()
        return {"message": "Graph cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/graph/data")
async def get_graph_data():
    """Get all nodes and relationships for visualization"""
    try:
        data = db.get_graph_data()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/neighborhood/{node_id}", response_model=GraphNeighborhoodResponse)
async def get_graph_neighborhood(node_id: str, depth: int = 1, max_nodes: int = 30):
    """Get the neighborhood of a node for visualization.

    Args:
        node_id: The node identifier (elementId or name property)
        depth: Number of hops to traverse (default 1, max 3)
        max_nodes: Maximum number of nodes to return (default 30, max 100)

    Returns:
        GraphNeighborhoodResponse with center_node, nodes[], relationships[]
    """
    # Clamp parameters to reasonable limits
    depth = min(max(depth, 1), 3)
    max_nodes = min(max(max_nodes, 1), 100)

    try:
        result = db.fetch_graph_neighborhood(node_id, depth=depth, max_nodes=max_nodes)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config/ui")
async def get_ui_configuration():
    """Get UI configuration for graph visualization styling.

    Returns the ui_config.yaml contents as JSON, including:
    - graph_visualization: node_styles, relationship_styles, layout
    - entity_card: title_field, fallback_title_fields, priority_fields
    """
    try:
        config = get_ui_config()
        # Convert Pydantic model to dict for JSON response
        return config.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Domain Configuration Endpoints (Multi-tenant Support)
# =============================================================================

@app.get("/config/domains")
async def list_available_domains():
    """Get list of available domain configurations.

    Returns all configured domains with their metadata.
    """
    try:
        domains = get_available_domains()
        current = get_current_domain()
        return {
            "current_domain": current,
            "available_domains": domains
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config/domain")
async def get_domain_configuration():
    """Get current domain configuration summary.

    Returns detailed information about the active domain config including:
    - Domain metadata (company, name, description)
    - Guardian rules summary (materials, environments, products)
    - Sample questions
    - Clarification parameters
    """
    try:
        return get_domain_config_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/config/domain/{domain_id}")
async def switch_domain(domain_id: str):
    """Switch to a different domain configuration.

    Args:
        domain_id: The domain to switch to (e.g., 'mann_hummel', 'wacker')

    Returns:
        The new domain configuration summary.
    """
    try:
        set_current_domain(domain_id)
        return {
            "message": f"Switched to domain: {domain_id}",
            "config": get_domain_config_summary()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/config/domain/{domain_id}/reload")
async def reload_domain_config(domain_id: str):
    """Reload a domain configuration from disk.

    Useful after editing the YAML config file.
    """
    try:
        reload_config(domain_id=domain_id)
        return {
            "message": f"Reloaded domain config: {domain_id}",
            "config": get_domain_config_summary()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# GraphRAG Endpoints
@app.post("/ingest")
async def ingest_case_study(request: IngestRequest):
    """Ingest a case study into the knowledge graph.

    This extracts hard data (products, competitors) and soft knowledge
    (concepts, observations, actions) from the text and stores them in Neo4j.
    """
    try:
        counts = ingest_case(
            text=request.text,
            project_name=request.project_name,
            customer=request.customer
        )
        return {
            "message": "Case study ingested successfully",
            "counts": counts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/thread")
async def ingest_thread(file: UploadFile = File(...)):
    """Ingest an email thread image into the knowledge graph.

    Upload a screenshot (PNG/JPEG) or PDF of an Outlook email thread.
    The system will:
    1. Use Gemini Vision to segment and analyze the thread
    2. Extract the engineering decision-making process
    3. Create an Event Graph with chronological email chain
    4. Identify Observations (Symptom/Constraint/Blocker) and Actions (Standard/Workaround)
    5. Build causality relationships (REVEALED, ADDRESSES)

    Returns a summary of the created graph nodes and the extracted data.
    """
    # Validate file type
    allowed_types = {
        "image/png": "image/png",
        "image/jpeg": "image/jpeg",
        "image/jpg": "image/jpeg",
        "application/pdf": "application/pdf"
    }

    content_type = file.content_type
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {content_type}. Allowed: PNG, JPEG, PDF"
        )

    try:
        # Read file content
        image_data = await file.read()

        # Process the image
        result = ingest_email_thread_image(
            image_data=image_data,
            mime_type=allowed_types[content_type]
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ThreadTextRequest(BaseModel):
    text: str


@app.post("/ingest/thread/text")
async def ingest_thread_text(request: ThreadTextRequest):
    """Ingest an email thread (as text) into the knowledge graph.

    Paste the full email thread text. The system will:
    1. Use Gemini to segment and analyze the thread
    2. Extract the engineering decision-making process
    3. Create an Event Graph with chronological email chain
    4. Identify Observations (Symptom/Constraint/Blocker) and Actions (Standard/Workaround)
    5. Build causality relationships (REVEALED, ADDRESSES)

    Returns a summary of the created graph nodes and the extracted data.
    """
    try:
        result = ingest_email_thread_text(request.text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/consult", response_model=ConsultResponse)
async def consult_knowledge_graph(request: ConsultRequest):
    """Query the knowledge graph for sales assistance.

    Uses hybrid vector + graph retrieval to find relevant past cases
    and synthesize a helpful response.
    """
    try:
        response = consult_brain(request.query)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/consult/explainable", response_model=ExplainableResponse)
async def consult_explainable(request: ConsultRequest):
    """Query the knowledge graph with full explainability.

    Returns structured response with:
    - reasoning_steps: Step-by-step thinking process
    - final_answer_markdown: Answer with [[REF:ID]] citation markers
    - references: Lookup table for citation details

    Designed for the Explainable UI that highlights verified facts.
    """
    try:
        response = query_explainable(request.query)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/consult/deep-explainable", response_model=DeepExplainableResponse)
async def consult_deep_explainable(request: ConsultRequest):
    """Query with Deep Explainability - Enterprise UI with segmented content.

    Returns structured response with:
    - reasoning_summary: High-level Polish reasoning timeline (3-5 steps)
    - content_segments: Answer broken into GRAPH_FACT/INFERENCE/GENERAL chunks
    - product_card: Structured product recommendation with specs

    Designed for Enterprise UI with "Expert Mode" toggle:
    - OFF: Clean readable text
    - ON: Highlights showing GRAPH_FACT (green) and INFERENCE (amber)
    """
    try:
        response = query_deep_explainable(request.query)
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/graph/init-vector-index")
async def init_vector_index():
    """Initialize the vector index for concept embeddings.

    This must be called before using vector search. Creates a Neo4j
    vector index on Concept.embedding if it doesn't exist.
    """
    try:
        db.create_vector_index()
        return {"message": "Vector index created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ACTIVE LEARNING - Human-in-the-loop Rule Learning
# =============================================================================

class LearnRuleRequest(BaseModel):
    """Request to learn a new rule from confirmed inference."""
    trigger_text: str  # The context trigger (e.g., "Swimming Pool", "Basen")
    rule_text: str     # The engineering rule (e.g., "Requires C5 corrosion class")
    context: str = None  # Optional additional context
    confirmed_by: str = "expert"  # Who confirmed this

class LearnRuleResponse(BaseModel):
    """Response from learning a new rule."""
    status: str
    keyword: str
    requirement: str
    confidence: float
    message: str


@app.post("/api/learn_rule", response_model=LearnRuleResponse)
async def learn_rule(request: LearnRuleRequest):
    """Learn a new engineering rule from human feedback.

    This endpoint is called when an expert confirms an INFERENCE.
    It creates or updates:
    - Keyword node with vector embedding for semantic search
    - Requirement node with the rule text
    - IMPLIES relationship between them

    Future queries will find this rule via vector similarity,
    so "Pool" rules will also apply to "Aquapark", "Water Park", etc.
    """
    from embeddings import generate_embedding

    try:
        # Step 1: Ensure the vector index exists
        db.ensure_learned_rules_index()

        # Step 2: Generate embedding for the trigger text
        embedding = generate_embedding(request.trigger_text)

        # Step 3: Save the rule to the graph
        result = db.save_learned_rule(
            trigger_text=request.trigger_text,
            rule_text=request.rule_text,
            embedding=embedding,
            context=request.context,
            confirmed_by=request.confirmed_by
        )

        return LearnRuleResponse(
            status="success",
            keyword=result["keyword"],
            requirement=result["requirement"],
            confidence=result["confidence"],
            message=f"Rule learned: '{request.trigger_text}' → '{request.rule_text}'"
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to learn rule: {str(e)}")


@app.get("/api/learned_rules")
async def get_learned_rules():
    """Get all learned rules (for admin/debugging)."""
    try:
        rules = db.get_all_learned_rules()
        return {
            "count": len(rules),
            "rules": rules
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/learned_rules")
async def delete_learned_rule(trigger: str, rule: str):
    """Delete a specific learned rule."""
    try:
        success = db.delete_learned_rule(trigger, rule)
        if success:
            return {"status": "deleted", "trigger": trigger, "rule": rule}
        else:
            raise HTTPException(status_code=404, detail="Rule not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/init_learned_rules_index")
async def init_learned_rules_index():
    """Initialize the vector index for learned rules.

    Creates a Neo4j vector index on Keyword.embedding if it doesn't exist.
    """
    try:
        success = db.ensure_learned_rules_index()
        if success:
            return {"message": "Learned rules vector index ready"}
        else:
            raise HTTPException(status_code=500, detail="Failed to create index")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/products", response_model=ProductListResponse)
async def list_products():
    """List all products with their competitor mappings."""
    try:
        products = db.get_all_products()
        return ProductListResponse(products=products)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/knowledge/timeline")
async def get_project_timeline(project_name: str):
    """Get the full timeline for a project with logic nodes (Deep Dive feature).

    Fetches all events in chronological order with their associated
    Observations and Actions, including citations for source verification.

    This endpoint supports the "Source Inspection" feature in the frontend,
    allowing users to verify the AI's reasoning by viewing the original
    email thread and the evidence for each classification.
    """
    try:
        timeline_data = db.get_project_timeline(project_name)
        if not timeline_data:
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
        return timeline_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Data Explorer Endpoints
@app.get("/explorer/projects")
async def get_explorer_projects():
    """Get all projects with details for the data explorer."""
    try:
        projects = db.get_all_projects_with_details()
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explorer/projects/{project_name}")
async def get_explorer_project_details(project_name: str):
    """Get full details for a specific project."""
    try:
        project = db.get_project_details(project_name)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explorer/concepts")
async def get_explorer_concepts():
    """Get all concepts with details for the data explorer."""
    try:
        concepts = db.get_all_concepts_with_details()
        return {"concepts": concepts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explorer/concepts/{concept_name}")
async def get_explorer_concept_details(concept_name: str):
    """Get full details for a specific concept."""
    try:
        concept = db.get_concept_details(concept_name)
        if not concept:
            raise HTTPException(status_code=404, detail="Concept not found")
        return concept
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explorer/observations")
async def get_explorer_observations():
    """Get all observations with details for the data explorer."""
    try:
        observations = db.get_all_observations_with_details()
        return {"observations": observations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explorer/actions")
async def get_explorer_actions():
    """Get all actions with details for the data explorer."""
    try:
        actions = db.get_all_actions_with_details()
        return {"actions": actions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explorer/competitors")
async def get_explorer_competitors():
    """Get all competitor products with details for the data explorer."""
    try:
        competitors = db.get_all_competitors_with_details()
        return {"competitors": competitors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Thread Explorer Endpoints
@app.get("/threads")
async def list_threads():
    """Get all email threads (projects) with summary info."""
    try:
        threads = db.get_all_threads_summary()
        return {"threads": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/threads/{project_name}")
async def get_thread_details(project_name: str):
    """Get full thread details including timeline with logic nodes."""
    try:
        timeline_data = db.get_project_timeline(project_name)
        if not timeline_data:
            raise HTTPException(status_code=404, detail=f"Thread '{project_name}' not found")
        return timeline_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/threads/{project_name}")
async def delete_thread(project_name: str):
    """Delete a thread and all its related graph data."""
    try:
        counts = db.delete_project(project_name)
        if counts.get("projects", 0) == 0:
            raise HTTPException(status_code=404, detail=f"Thread '{project_name}' not found")
        return {
            "message": f"Thread '{project_name}' deleted successfully",
            "deleted": counts
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Knowledge Source Discovery Endpoints
class KnowledgeVerifyRequest(BaseModel):
    candidate_id: str
    action: str  # "reject" | "create_new" | "map_to_existing"
    verified_name: str | None = None
    description: str | None = None
    existing_source_id: str | None = None


@app.get("/knowledge/candidates")
async def get_knowledge_candidates(status: str | None = None):
    """Get knowledge candidates for verification.

    Query params:
    - status: Filter by status (pending, verified, rejected). Default: all.
    """
    try:
        candidates = db.get_all_knowledge_candidates(status=status)
        return {"candidates": candidates}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/knowledge/verify")
async def verify_knowledge_candidate(request: KnowledgeVerifyRequest):
    """Verify, reject, or map a knowledge candidate.

    Actions:
    - reject: Mark candidate as rejected (spam, false positive)
    - create_new: Create a new VerifiedSource from this candidate
    - map_to_existing: Map this candidate as an alias of an existing VerifiedSource
    """
    valid_actions = ["reject", "create_new", "map_to_existing"]
    if request.action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Must be one of: {valid_actions}"
        )

    if request.action == "create_new" and not request.verified_name:
        raise HTTPException(
            status_code=400,
            detail="verified_name is required when action is 'create_new'"
        )

    if request.action == "map_to_existing" and not request.existing_source_id:
        raise HTTPException(
            status_code=400,
            detail="existing_source_id is required when action is 'map_to_existing'"
        )

    try:
        result = db.verify_knowledge_candidate(
            candidate_id=request.candidate_id,
            action=request.action,
            verified_name=request.verified_name,
            description=request.description,
            existing_source_id=request.existing_source_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/knowledge/library")
async def get_knowledge_library():
    """Get all verified knowledge sources (the Knowledge Library).

    Returns verified sources with their usage frequency and aliases.
    """
    try:
        sources = db.get_verified_sources_library()
        return {"sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/knowledge/library/{source_id}")
async def get_knowledge_source_details(source_id: str):
    """Get detailed information about a verified knowledge source."""
    try:
        source = db.get_verified_source_details(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        return source
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/knowledge/candidates/{candidate_id}")
async def delete_knowledge_candidate(candidate_id: str):
    """Delete a knowledge candidate."""
    try:
        deleted = db.delete_knowledge_candidate(candidate_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return {"message": "Candidate deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/knowledge/experts")
async def get_expert_knowledge_map():
    """Get SME connectivity - which experts are linked to which knowledge sources.

    Shows which team members have demonstrated expertise with specific tools,
    data sources, and processes based on email thread analysis.
    """
    try:
        experts = db.get_expert_knowledge_map()
        return {"experts": experts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/knowledge/stats")
async def get_knowledge_stats():
    """Get knowledge discovery statistics.

    Returns counts of pending candidates, verified sources, coverage metrics.
    """
    try:
        stats = db.get_knowledge_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Document Ingestion Endpoints (Generic Two-Pass AI)
@app.post("/ingest/doc/analyze")
async def analyze_document(
    file: UploadFile = File(...),
    document_hint: str = Form(None)
):
    """Pass 1 - Architect: Analyze document and propose schema.

    Upload a document (PDF, image, or text file) and optionally provide a hint
    about what the document contains. The AI will analyze it and propose a
    graph schema (node types, relationships, concepts).

    Returns the proposed schema for user confirmation before extraction.
    """
    # Validate file type
    allowed_types = {
        "application/pdf": "application/pdf",
        "image/png": "image/png",
        "image/jpeg": "image/jpeg",
        "image/jpg": "image/jpeg",
        "text/plain": "text/plain",
        "text/csv": "text/csv",
        "text/markdown": "text/markdown",
    }

    content_type = file.content_type
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {content_type}. Allowed: PDF, PNG, JPEG, TXT, CSV, MD"
        )

    try:
        file_bytes = await file.read()
        print(f"[DEBUG] Analyzing document: {file.filename}, size: {len(file_bytes)}, type: {content_type}")
        schema = analyze_document_schema(
            file_bytes=file_bytes,
            mime_type=allowed_types[content_type],
            document_hint=document_hint
        )
        print(f"[DEBUG] Schema result: {schema}")

        return {
            "message": "Schema analysis complete",
            "filename": file.filename,
            "schema": schema
        }
    except Exception as e:
        import traceback
        print(f"[ERROR] analyze_document failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/doc/execute")
async def execute_document_extraction(
    file: UploadFile = File(...),
    confirmed_schema: str = Form(..., alias="schema"),
    source_name: str = Form(None)
):
    """Pass 2 - Builder: Extract data using confirmed schema and write to Neo4j.

    Upload the same document along with the confirmed schema (as JSON string).
    The AI will extract entities and relationships according to the schema
    and write them to the knowledge graph.

    Returns counts of created nodes and relationships.
    """
    allowed_types = {
        "application/pdf": "application/pdf",
        "image/png": "image/png",
        "image/jpeg": "image/jpeg",
        "image/jpg": "image/jpeg",
        "text/plain": "text/plain",
        "text/csv": "text/csv",
        "text/markdown": "text/markdown",
    }

    content_type = file.content_type
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {content_type}. Allowed: PDF, PNG, JPEG, TXT, CSV, MD"
        )

    try:
        # Parse schema JSON
        schema_dict = json.loads(confirmed_schema)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid schema JSON: {str(e)}"
        )

    try:
        file_bytes = await file.read()

        # Use filename as source name if not provided
        doc_source_name = source_name or file.filename or "Unknown Document"

        result = ingest_document(
            file_bytes=file_bytes,
            mime_type=allowed_types[content_type],
            schema=schema_dict,
            source_name=doc_source_name
        )

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
