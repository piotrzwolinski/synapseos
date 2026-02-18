import json
import os
import time  # batch stats cache
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from database import db
from chat import session_manager
from ingestor import ingest_case, ingest_email_thread_image, ingest_email_thread_text
from ingestor_docs import analyze_document_schema, ingest_document
from retriever import consult_brain, query_explainable, query_deep_explainable, query_deep_explainable_streaming
from models import IngestRequest, ConsultRequest, ConsultResponse, ProductListResponse, ExplainableResponse, DeepExplainableResponse, GraphNeighborhoodResponse, SessionGraphState, SessionGraphVisualization
from config_loader import (
    get_ui_config,
    get_config,
    get_available_domains,
    get_current_domain,
    set_current_domain,
    get_domain_config_summary,
    reload_config
)
from auth import LoginRequest, TokenResponse, login, get_current_user, get_current_user_info

app = FastAPI(title="Graph Chatbot API")  # v3.8

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for UI prototypes
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


async def _cleanup_sessions_periodically():
    """Background task to clean up stale chat sessions every 30 minutes."""
    while True:
        await asyncio.sleep(1800)
        session_manager.cleanup_stale()

@app.on_event("startup")
async def startup_event():
    """Warm up connections and caches on server start."""
    print("🚀 Starting server warmup...")
    db.warmup()
    # Initialize Layer 4 session schema
    try:
        db.init_session_schema()
    except Exception as e:
        print(f"⚠ Session schema init failed (non-fatal): {e}")
    asyncio.create_task(_cleanup_sessions_periodically())
    print("✅ Server ready!")


class ChatMessage(BaseModel):
    message: str
    session_id: str = "default"

class ClearChatRequest(BaseModel):
    session_id: str = "default"

class ProductPivot(BaseModel):
    """Product substitution info for UI banner"""
    original_product: str
    pivoted_to: str
    reason: str
    physics_explanation: Optional[str] = None
    user_misconception: Optional[str] = None
    required_feature: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    product_pivot: Optional[ProductPivot] = None
    risk_detected: Optional[bool] = None
    risk_severity: Optional[str] = None

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


@app.get("/test-lab/results")
async def get_test_lab_results(_user: str = Depends(get_current_user)):
    """Serve the latest test results JSON for the Test Lab viewer."""
    results_path = STATIC_DIR / "test-results.json"
    if results_path.exists():
        return FileResponse(results_path, media_type="application/json")
    raise HTTPException(status_code=404, detail="No test results available. Run the test suite with --json flag first.")


@app.get("/test-lab/multistep-results")
async def get_multistep_results(_user: str = Depends(get_current_user)):
    """Serve the latest multi-step test results JSON."""
    results_path = Path(__file__).parent.parent / "tests" / "multistep" / "results" / "latest.json"
    if results_path.exists():
        return FileResponse(results_path, media_type="application/json")
    raise HTTPException(status_code=404, detail="No multi-step test results available.")


def _compute_batch_stats(batch_dir: Path) -> dict:
    """Compute stats for a batch dir. Cached to _stats.json."""
    cache_file = batch_dir / "_stats.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except Exception:
            pass
    json_files = [f for f in batch_dir.glob("*.json") if f.name not in ("SUMMARY.json", "_stats.json")]
    judge_totals: dict[str, list[float]] = {"gemini": [], "openai": [], "anthropic": []}
    dim_totals: dict[str, list[float]] = {}
    pass_count = 0
    fail_count = 0
    judged_count = 0
    for f in json_files:
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        for turn in reversed(data.get("turns", [])):
            jr = turn.get("judge_results")
            if jr:
                has_judge = False
                for provider in ["gemini", "openai", "anthropic"]:
                    j = jr.get(provider)
                    if j and isinstance(j, dict) and j.get("recommendation") != "ERROR":
                        has_judge = True
                        score = j.get("overall_score", 0)
                        if score > 0:
                            judge_totals[provider].append(score)
                        if j.get("recommendation") == "FAIL":
                            fail_count += 1
                        for dim, val in j.get("scores", {}).items():
                            if isinstance(val, (int, float)) and val > 0:
                                dim_totals.setdefault(dim, []).append(val)
                if has_judge:
                    judged_count += 1
                    recs = [jr.get(p, {}).get("recommendation") for p in ["gemini", "openai", "anthropic"]
                            if isinstance(jr.get(p), dict) and jr.get(p, {}).get("recommendation") != "ERROR"]
                    if recs and all(r == "PASS" for r in recs):
                        pass_count += 1
                break
    judge_avgs = {p: round(sum(v) / len(v), 2) if v else 0 for p, v in judge_totals.items()}
    all_scores = [s for v in judge_totals.values() for s in v]
    dim_avgs = {d: round(sum(v) / len(v), 2) for d, v in dim_totals.items() if v}
    stats = {
        "test_count": len(json_files),
        "judged_count": judged_count,
        "judge_avgs": judge_avgs,
        "overall_avg": round(sum(all_scores) / len(all_scores), 2) if all_scores else 0,
        "dimension_avgs": dim_avgs,
        "pass_count": pass_count,
        "fail_count": fail_count,
    }
    try:
        cache_file.write_text(json.dumps(stats))
    except Exception:
        pass
    return stats


@app.get("/test-lab/batches")
async def list_batches(_user: str = Depends(get_current_user)):
    """List all batch result directories with summary stats including per-judge averages."""
    reports_dir = Path(__file__).parent.parent / "reports"
    if not reports_dir.exists():
        return []
    batches = []
    for d in sorted(reports_dir.iterdir(), reverse=True):
        if d.is_dir() and d.name.startswith("batch-"):
            # Parse timestamp from directory name (batch-2026-02-15T12-10-27)
            ts_str = d.name.replace("batch-", "")
            try:
                dt = datetime.strptime(ts_str, "%Y-%m-%dT%H-%M-%S")
                ts = dt.timestamp()
            except ValueError:
                ts = d.stat().st_mtime
            stats = _compute_batch_stats(d)
            if stats.get("test_count", 0) >= 20:
                batches.append({"id": d.name, "timestamp": ts, **stats})
    return batches[:20]


@app.get("/test-lab/batches/{batch_id}")
async def get_batch_results(batch_id: str, _user: str = Depends(get_current_user)):
    """Get all test results from a specific batch with judge scores."""
    reports_dir = Path(__file__).parent.parent / "reports" / batch_id
    if not reports_dir.exists():
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
    results = []
    for f in sorted(reports_dir.glob("*.json")):
        if f.name in ("SUMMARY.json", "_stats.json"):
            continue
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        # Extract last-turn judge scores
        judge_scores = {}
        last_turn_num = 0
        for turn in reversed(data.get("turns", [])):
            jr = turn.get("judge_results")
            if jr:
                last_turn_num = turn.get("turn_number", 0)
                for provider in ["gemini", "openai", "anthropic"]:
                    j = jr.get(provider)
                    if j and isinstance(j, dict) and j.get("recommendation") != "ERROR":
                        judge_scores[provider] = {
                            "overall": j.get("overall_score", 0),
                            "recommendation": j.get("recommendation", ""),
                            "scores": j.get("scores", {}),
                            "explanation": j.get("explanation", ""),
                            "weaknesses": j.get("weaknesses", []),
                            "strengths": j.get("strengths", []),
                            "pdf_citations": j.get("pdf_citations", []),
                            "dimension_explanations": j.get("dimension_explanations", {}),
                        }
                break
        # Count turns
        total_turns = sum(1 for t in data.get("turns", []) if t.get("role") == "assistant")
        results.append({
            "name": data.get("name", f.stem),
            "query": data.get("query", ""),
            "duration_s": data.get("duration_s", 0),
            "error": data.get("error"),
            "total_turns": total_turns,
            "last_judged_turn": last_turn_num,
            "judges": judge_scores,
        })
    return {
        "batch_id": batch_id,
        "test_count": len(results),
        "results": results,
    }


# =============================================================================
# Authentication Endpoints (Public)
# =============================================================================

@app.post("/auth/login", response_model=TokenResponse)
async def auth_login(request: LoginRequest):
    """Authenticate user and return JWT token."""
    return login(request)


@app.get("/auth/verify")
async def auth_verify(user_info: dict = Depends(get_current_user_info)):
    """Verify that the current token is valid."""
    return {"valid": True, "username": user_info["username"], "role": user_info["role"]}


# =============================================================================
# Protected Endpoints (Require Authentication)
# =============================================================================

@app.post("/chat", response_model=ChatResponse)
async def chat(message: ChatMessage, _user: str = Depends(get_current_user)):
    """Send a message to the chatbot and get a response.

    Uses LLM-DRIVEN architecture:
    - Full conversation history as "Project Ledger"
    - GRAPH_DATA injection for ground truth
    - Zero-Hallucination system prompt
    """
    try:
        bot = session_manager.get_session(message.session_id)
        # Step 1: Get GRAPH_DATA (The Big Data Dump)
        graph_data = bot.get_graph_data_for_query(message.message)

        # Step 2: Send with LLM-driven approach
        response = bot.send_message_llm_driven(message.message, graph_data)

        return ChatResponse(response=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream(message: ChatMessage, _user: str = Depends(get_current_user)):
    """Stream chat with reasoning steps via Server-Sent Events.

    Uses LLM-DRIVEN architecture:
    - Full conversation history as "Project Ledger"
    - GRAPH_DATA injection (Big Data Dump) for ground truth
    - Zero-Hallucination system prompt
    """
    print(f"\n{'='*60}")
    print(f"🎯 [ENDPOINT HIT] /chat/stream  (LLM + Graph Data mode)")
    print(f"{'='*60}\n")

    def generate():
        bot = session_manager.get_session(message.session_id)
        total_start = time.time()

        try:
            # Step 1: Intent Analysis
            yield f"data: {json.dumps({'step': 'intent', 'status': 'active', 'detail': '🔍 Analyzing project context...'})}\n\n"
            t1 = time.time()

            # Extract product family and application
            query_upper = message.message.upper()
            detected_family = None
            for family in ['GDMI', 'GDB', 'GDC', 'GDP']:
                if family in query_upper:
                    detected_family = family
                    break
            detected_family = detected_family or "GDB"

            # Detect application/environment
            query_lower = message.message.lower()
            detected_app = None
            app_keywords = {
                'hospital': 'Hospital', 'szpital': 'Hospital',
                'kitchen': 'Kitchen', 'outdoor': 'Outdoor', 'roof': 'Outdoor'
            }
            for kw, app in app_keywords.items():
                if kw in query_lower:
                    detected_app = app
                    break

            intent_detail = f"🔍 Detected: {detected_family}"
            if detected_app:
                intent_detail += f" for {detected_app}"
            yield f"data: {json.dumps({'step': 'intent', 'status': 'done', 'detail': f'{intent_detail} ({time.time()-t1:.1f}s)'})}\n\n"

            # Step 2: Big Data Dump from Graph
            yield f"data: {json.dumps({'step': 'embed', 'status': 'active', 'detail': '📦 Loading product catalog from Graph...'})}\n\n"
            t2 = time.time()
            graph_data = bot.get_graph_data_for_query(message.message)
            variant_count = len(graph_data.get('product_catalog', {}).get('variants', []))
            material_count = len(graph_data.get('product_catalog', {}).get('materials', []))
            yield f"data: {json.dumps({'step': 'embed', 'status': 'done', 'detail': f'📦 Loaded {variant_count} variants, {material_count} materials ({time.time()-t2:.1f}s)'})}\n\n"

            # Step 3: Project Ledger (Conversation History)
            yield f"data: {json.dumps({'step': 'vector', 'status': 'active', 'detail': '📋 Reviewing Project Ledger (conversation history)...'})}\n\n"
            history_turns = len(bot.chat_history) // 2

            # Extract key locked parameters from history for display
            locked_params = []
            for item in bot.chat_history:
                content = item["parts"][0].lower() if item["parts"] else ""
                if "stainless" in content or "rf" in content.split():
                    if "Material: RF" not in locked_params:
                        locked_params.append("Material: RF")
                if "hospital" in content or "szpital" in content:
                    if "Environment: Hospital" not in locked_params:
                        locked_params.append("Environment: Hospital")

            ledger_detail = f"📋 Project Ledger: {history_turns} turn(s)"
            if locked_params:
                ledger_detail += f" | Locked: {', '.join(locked_params)}"
            yield f"data: {json.dumps({'step': 'vector', 'status': 'done', 'detail': ledger_detail})}\n\n"

            # Step 4: Guardian Check (Environment Restrictions)
            yield f"data: {json.dumps({'step': 'graph', 'status': 'active', 'detail': '🛡️ Guardian: Checking environment constraints...'})}\n\n"
            t4 = time.time()

            restrictions = graph_data.get('product_catalog', {}).get('environment_restrictions', [])
            vulnerabilities = graph_data.get('product_catalog', {}).get('product_vulnerabilities', [])
            app_context = graph_data.get('application_context', {})

            # Build graph traversal paths for visualization
            graph_paths = []
            if detected_family:
                graph_paths.append(f"ProductFamily({detected_family}) → ProductVariant[{variant_count} variants]")
            if detected_app:
                graph_paths.append(f"Application({detected_app}) → REQUIRES_MATERIAL → Material[]")
            for r in restrictions:
                env = r.get('environment', '')
                required = r.get('required_materials', [])
                if env and required:
                    graph_paths.append(f"Application({env}) → REQUIRES_MATERIAL → [{', '.join(required)}]")
            for v in vulnerabilities:
                risk = v.get('risk', '')
                product = v.get('product', detected_family)
                if risk:
                    graph_paths.append(f"ProductVariant({product}) → VULNERABLE_TO → Risk({risk})")
            if app_context.get('material_requirements'):
                for mat in app_context['material_requirements']:
                    if mat.get('code'):
                        reason = mat.get('reason', '')
                        graph_paths.append(f"Application → REQUIRES_MATERIAL → Material({mat['code']})" + (f" [{reason}]" if reason else ""))
            if app_context.get('available_mitigations'):
                for mit in app_context['available_mitigations']:
                    if mit.get('mechanism'):
                        graph_paths.append(f"ProductVariant({mit.get('product_family', '?')}) → MITIGATES → Risk({mit.get('risk', '?')}) [{mit['mechanism']}]")

            guardian_detail = "🛡️ Guardian: All checks passed"
            if detected_app and restrictions:
                for r in restrictions:
                    if r.get('environment', '').lower() == detected_app.lower():
                        required = r.get('required_materials', [])
                        if required:
                            guardian_detail = f"🛡️ Guardian: {detected_app} requires {'/'.join(required)}"
                            break

            yield f"data: {json.dumps({'step': 'graph', 'status': 'done', 'detail': f'{guardian_detail} ({time.time()-t4:.1f}s)', 'data': {'graph_paths': graph_paths}})}\n\n"

            # Step 5: LLM Synthesis (with keepalive events during long call)
            yield f"data: {json.dumps({'step': 'thinking', 'status': 'active', 'detail': '👔 Senior Engineer: Synthesizing recommendation...'})}\n\n"
            t5 = time.time()

            # Run LLM call in thread with keepalive events
            import threading
            import queue
            result_queue = queue.Queue()

            def llm_worker():
                try:
                    result = bot.send_message_llm_driven(message.message, graph_data)
                    result_queue.put(("success", result))
                except Exception as e:
                    result_queue.put(("error", str(e)))

            thread = threading.Thread(target=llm_worker)
            thread.start()

            # Send keepalive comments every 5 seconds while waiting
            response = None
            while thread.is_alive():
                thread.join(timeout=5)
                if thread.is_alive():
                    elapsed = time.time() - t5
                    yield f": keepalive {elapsed:.0f}s\n\n"  # SSE comment for keepalive

            # Get result from queue
            status, result = result_queue.get()
            if status == "error":
                raise Exception(result)
            response = result
            llm_time = time.time() - t5

            total_time = time.time() - total_start
            print(f"⏱️ [LLM-DRIVEN] Total: {total_time:.2f}s (LLM: {llm_time:.2f}s)")

            yield f"data: {json.dumps({'step': 'thinking', 'status': 'done', 'detail': f'👔 Recommendation ready ({llm_time:.1f}s)'})}\n\n"

            # Emit prompt preview for diagnostics
            if bot.last_prompt:
                prompt_text = f"=== SYSTEM PROMPT ===\n{bot.last_system_prompt or '(default)'}\n\n=== USER PROMPT ===\n{bot.last_prompt}"
                yield f"data: {json.dumps({'step': 'prompt', 'prompt_preview': prompt_text})}\n\n"

            # Emit diagnostics
            yield f"data: {json.dumps({'step': 'diagnostics', 'data': {'model': bot.model_name, 'llm_time_s': round(llm_time, 2), 'total_time_s': round(total_time, 2), 'history_turns': history_turns, 'variant_count': variant_count, 'material_count': material_count, 'graph_paths_count': len(graph_paths)}})}\n\n"

            yield f"data: {json.dumps({'step': 'complete', 'response': response})}\n\n"

        except Exception as e:
            import traceback
            print(f"❌ [LLM-DRIVEN] Error: {e}")
            traceback.print_exc()
            yield f"data: {json.dumps({'step': 'error', 'status': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/chat/clear")
async def clear_chat(request: ClearChatRequest, _user: str = Depends(get_current_user)):
    """Clear the chat history for a session and its Layer 4 graph state."""
    session_manager.clear_session(request.session_id)
    # Also clear Layer 4 graph state
    try:
        session_graph_mgr = db.get_session_graph_manager()
        session_graph_mgr.clear_session(request.session_id)
    except Exception as e:
        print(f"⚠ Session graph clear (non-fatal): {e}")
    return {"message": "Chat history and session graph cleared"}

@app.get("/chat/history")
async def get_chat_history(session_id: str = "default", _user: str = Depends(get_current_user)):
    """Get the chat history for a session"""
    bot = session_manager.get_session(session_id)
    return {"messages": bot.get_history()}

@app.get("/chat/model")
async def get_model_info(_user: str = Depends(get_current_user)):
    """Get current model information"""
    return session_manager.get_model_info()

@app.get("/chat/models")
async def get_available_models(_user: str = Depends(get_current_user)):
    """Get list of available LLM models for the frontend dropdown."""
    from llm_router import AVAILABLE_MODELS, DEFAULT_MODEL
    return {"models": AVAILABLE_MODELS, "default": DEFAULT_MODEL, "current": session_manager.model_name}

@app.post("/chat/model")
async def set_model(request: dict, _user: str = Depends(get_current_user)):
    """Set the Gemini model to use"""
    model = request.get("model", "").strip()
    from llm_router import AVAILABLE_MODELS
    valid_models = [m["id"] for m in AVAILABLE_MODELS]
    if model not in valid_models:
        raise HTTPException(status_code=400, detail=f"Invalid model. Must be one of: {valid_models}")
    session_manager.set_model(model)
    return {"model": model, "message": f"Model set to {model}"}

@app.post("/chat/thinking")
async def set_thinking_level(request: dict, _user: str = Depends(get_current_user)):
    """Set the thinking level for the model (Gemini 3 Pro supports: low, high)"""
    level = request.get("level", "high").lower()
    valid_levels = ["low", "high"]
    if level not in valid_levels:
        raise HTTPException(status_code=400, detail=f"Invalid level. Must be one of: {valid_levels}")
    session_manager.set_thinking_level(level)
    return {"thinking_level": level, "message": f"Thinking level set to {level}"}


# =============================================================================
# LLM-DRIVEN DEMO ENDPOINT (New Architecture)
# =============================================================================

@app.post("/chat/llm-driven")
async def chat_llm_driven(message: ChatMessage, _user: str = Depends(get_current_user)):
    """LLM-DRIVEN CHAT: Uses full history + Big Data Dump for demo stability.

    This endpoint implements the refactored architecture:
    1. LLM maintains state via full conversation history
    2. GRAPH_DATA (Big Data Dump) injected for ground truth
    3. Zero-Hallucination system prompt

    Advantages for demo:
    - No Python state drift (material never reverts to FZ)
    - Exact weights from graph (no guessing)
    - Single LLM call (faster)
    """
    try:
        bot = session_manager.get_session(message.session_id)
        # Step 1: Get GRAPH_DATA (The Big Data Dump)
        graph_data = bot.get_graph_data_for_query(message.message)

        # Step 2: Send with LLM-driven approach
        response = bot.send_message_llm_driven(message.message, graph_data)

        return ChatResponse(response=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/llm-driven/stream")
async def chat_llm_driven_stream(message: ChatMessage, _user: str = Depends(get_current_user)):
    """STREAMING LLM-DRIVEN CHAT with reasoning steps.

    Same as /chat/llm-driven but with Server-Sent Events for UI feedback.
    """
    print(f"\n{'='*60}")
    print(f"🎯 [ENDPOINT HIT] /chat/llm-driven/stream  (LLM Only mode)")
    print(f"{'='*60}\n")

    def generate():
        bot = session_manager.get_session(message.session_id)
        total_start = time.time()

        try:
            # Step 1: Intent Analysis
            yield f"data: {json.dumps({'step': 'intent', 'status': 'active', 'detail': '🔍 Analyzing project context...'})}\n\n"
            t1 = time.time()

            # Extract product family and application
            query_upper = message.message.upper()
            detected_family = None
            for family in ['GDMI', 'GDB', 'GDC', 'GDP']:
                if family in query_upper:
                    detected_family = family
                    break
            detected_family = detected_family or "GDB"

            yield f"data: {json.dumps({'step': 'intent', 'status': 'done', 'detail': f'🔍 Detected: {detected_family} family ({time.time()-t1:.1f}s)'})}\n\n"

            # Step 2: Big Data Dump
            yield f"data: {json.dumps({'step': 'embed', 'status': 'active', 'detail': '📦 Loading product catalog from Graph...'})}\n\n"
            t2 = time.time()
            graph_data = bot.get_graph_data_for_query(message.message)
            variant_count = len(graph_data.get('product_catalog', {}).get('variants', []))
            yield f"data: {json.dumps({'step': 'embed', 'status': 'done', 'detail': f'📦 Loaded {variant_count} variants ({time.time()-t2:.1f}s)'})}\n\n"

            # Step 3: History Check
            yield f"data: {json.dumps({'step': 'vector', 'status': 'active', 'detail': '📋 Reviewing conversation history...'})}\n\n"
            history_turns = len(bot.chat_history) // 2
            yield f"data: {json.dumps({'step': 'vector', 'status': 'done', 'detail': f'📋 Project Ledger: {history_turns} previous turn(s)'})}\n\n"

            # Step 3.5: Load Session Graph State
            session_graph_mgr = None
            try:
                session_graph_mgr = db.get_session_graph_manager()
                session_graph_mgr.ensure_session(message.session_id)
                graph_state = session_graph_mgr.get_project_state(message.session_id)
                if graph_state.get("tags"):
                    tag_count = graph_state["tag_count"]
                    yield f"data: {json.dumps({'step': 'vector', 'status': 'done', 'detail': f'📋 Project Ledger: {history_turns} turn(s) + {tag_count} tag(s) from graph'})}\n\n"
            except Exception as e:
                print(f"⚠ Session graph load (non-fatal): {e}")

            # Step 4: LLM Processing
            yield f"data: {json.dumps({'step': 'thinking', 'status': 'active', 'detail': '👔 Senior Engineer synthesizing response...'})}\n\n"
            t4 = time.time()
            response = bot.send_message_llm_driven(message.message, graph_data, session_id=message.session_id)
            llm_time = time.time() - t4

            total_time = time.time() - total_start
            yield f"data: {json.dumps({'step': 'thinking', 'status': 'done', 'detail': f'👔 Response ready ({llm_time:.1f}s, total: {total_time:.1f}s)'})}\n\n"

            # Emit prompt preview for diagnostics
            if bot.last_prompt:
                prompt_text = f"=== SYSTEM PROMPT ===\n{bot.last_system_prompt or '(default)'}\n\n=== USER PROMPT ===\n{bot.last_prompt}"
                yield f"data: {json.dumps({'step': 'prompt', 'prompt_preview': prompt_text})}\n\n"

            # Emit diagnostics
            yield f"data: {json.dumps({'step': 'diagnostics', 'data': {'model': bot.model_name, 'llm_time_s': round(llm_time, 2), 'total_time_s': round(total_time, 2), 'history_turns': history_turns, 'variant_count': variant_count}})}\n\n"

            yield f"data: {json.dumps({'step': 'complete', 'response': response})}\n\n"

            # Emit session graph state for frontend visualization
            if session_graph_mgr:
                try:
                    session_state = session_graph_mgr.get_project_state(message.session_id)
                    reasoning_paths = session_graph_mgr.get_reasoning_path(message.session_id)
                    session_state["reasoning_paths"] = reasoning_paths
                    yield f"data: {json.dumps({'step': 'session_state', 'data': session_state})}\n\n"
                except Exception as e:
                    print(f"⚠ Session state emit (non-fatal): {e}")

        except Exception as e:
            yield f"data: {json.dumps({'step': 'error', 'status': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/graph/stats", response_model=GraphStats)
async def get_graph_stats(_user: str = Depends(get_current_user)):
    """Get statistics about the graph database"""
    try:
        connected = db.verify_connection()
        nodes = db.get_node_count()
        relationships = db.get_relationship_count()
        return GraphStats(nodes=nodes, relationships=relationships, connected=connected)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/graph/clear")
async def clear_graph(_user: str = Depends(get_current_user)):
    """Clear all nodes and relationships from the graph"""
    try:
        db.clear_graph()
        return {"message": "Graph cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/graph/data")
async def get_graph_data(_user: str = Depends(get_current_user)):
    """Get all nodes and relationships for visualization"""
    try:
        data = db.get_graph_data()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/neighborhood/{node_id}", response_model=GraphNeighborhoodResponse)
async def get_graph_neighborhood(node_id: str, depth: int = 1, max_nodes: int = 30, _user: str = Depends(get_current_user)):
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


# =============================================================================
# SESSION GRAPH ENDPOINTS (Layer 4)
# =============================================================================

@app.get("/session/graph/{session_id}")
async def get_session_graph(session_id: str, _user: str = Depends(get_current_user)):
    """Get session graph state for visualization.

    Returns:
        SessionGraphState with project, tags, reasoning paths
    """
    try:
        session_graph_mgr = db.get_session_graph_manager()
        state = session_graph_mgr.get_project_state(session_id)
        reasoning_paths = session_graph_mgr.get_reasoning_path(session_id)
        state["reasoning_paths"] = reasoning_paths
        return state
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/session/graph/{session_id}/visualization")
async def get_session_graph_visualization(session_id: str, _user: str = Depends(get_current_user)):
    """Get session graph nodes and relationships for ForceGraph2D visualization.

    Returns nodes (Session, ActiveProject, TagUnit + linked Layer 1 nodes)
    and their relationships for rendering in the frontend graph viewer.
    """
    try:
        session_graph_mgr = db.get_session_graph_manager()
        return session_graph_mgr.get_session_graph_data(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/session/{session_id}")
async def clear_session_graph(session_id: str, _user: str = Depends(get_current_user)):
    """Clear all Layer 4 session state from the graph.

    Called alongside /chat/clear to clean up session graph nodes.
    """
    try:
        session_graph_mgr = db.get_session_graph_manager()
        session_graph_mgr.clear_session(session_id)
        return {"message": f"Session {session_id} cleared from graph"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config/ui")
async def get_ui_configuration(_user: str = Depends(get_current_user)):
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
async def list_available_domains(_user: str = Depends(get_current_user)):
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
async def get_domain_configuration(_user: str = Depends(get_current_user)):
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
async def switch_domain(domain_id: str, _user: str = Depends(get_current_user)):
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
async def reload_domain_config(domain_id: str, _user: str = Depends(get_current_user)):
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
async def ingest_case_study(request: IngestRequest, _user: str = Depends(get_current_user)):
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
async def ingest_thread(file: UploadFile = File(...), _user: str = Depends(get_current_user)):
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
async def ingest_thread_text(request: ThreadTextRequest, _user: str = Depends(get_current_user)):
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
async def consult_knowledge_graph(request: ConsultRequest, _user: str = Depends(get_current_user)):
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
async def consult_explainable(request: ConsultRequest, _user: str = Depends(get_current_user)):
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
async def consult_deep_explainable(request: ConsultRequest, _user: str = Depends(get_current_user)):
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


@app.post("/consult/deep-explainable/stream")
async def consult_deep_explainable_stream(request: ConsultRequest, _user: str = Depends(get_current_user)):
    """Streaming version of Deep Explainable query with real-time inference chain.

    Returns Server-Sent Events showing the reasoning process:
    - Intent detection with discovered entities
    - Domain rule matching (e.g., Hospital -> VDI 6022)
    - Guardian risk detection (e.g., FZ vs C5 conflict)
    - Product matching results
    - Final recommendation

    SSE Event Types:
    - inference: Intermediate reasoning step with data
    - complete: Final response ready
    """
    print(f"\n{'='*60}")
    print(f"🎯 [ENDPOINT HIT] /consult/deep-explainable/stream  (Graph Reasoning mode)")
    print(f"   Session ID: {request.session_id or '(none)'}")
    print(f"{'='*60}\n")
    def generate():
        try:
            for event in query_deep_explainable_streaming(request.query, session_id=request.session_id, model=session_manager.model_name):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/consult/universal/stream")
async def consult_universal_stream(request: ConsultRequest, _user: str = Depends(get_current_user)):
    """Streaming Universal Neuro-Symbolic Engine query.

    Uses the domain-agnostic UniversalGraphEngine with:
    - Vector KNN context detection
    - Constraint propagation from graph
    - Entropy-reduction discriminators
    - Risk assessment via graph traversal

    Returns SSE events matching the deep-explainable format for UI compatibility.
    """
    print(f"\n{'='*60}")
    print(f"🎯 [ENDPOINT HIT] /consult/universal/stream  (Neuro-Symbolic mode)")
    print(f"{'='*60}\n")
    def generate():
        try:
            from logic.engine_adapter import GraphEngineAdapter
            from google import genai as genai_client
            import os

            t_start = time.time()

            # Step 1: Initialize engine
            yield f"data: {json.dumps({'type': 'inference', 'step': 'init', 'status': 'active', 'detail': '🔗 Initializing neuro-symbolic engine...'})}\n\n"

            llm_client = genai_client.Client(api_key=os.getenv("GEMINI_API_KEY"))

            # Wrap Neo4jConnection with a .query() adapter for the universal engine
            class DbQueryAdapter:
                def __init__(self, neo4j_conn):
                    self._conn = neo4j_conn
                def query(self, cypher, params=None):
                    driver = self._conn.connect()
                    with driver.session(database=self._conn.database) as session:
                        result = session.run(cypher, parameters=params or {})
                        return [dict(r) for r in result]

            db_adapter = DbQueryAdapter(db)
            adapter = GraphEngineAdapter(db_connection=db_adapter, llm_client=llm_client)

            yield f"data: {json.dumps({'type': 'inference', 'step': 'init', 'status': 'done', 'detail': f'🔗 Engine ready ({time.time()-t_start:.1f}s)'})}\n\n"

            # Step 2: Run engine
            yield f"data: {json.dumps({'type': 'inference', 'step': 'context', 'status': 'active', 'detail': '🔍 Detecting contexts via vector KNN...'})}\n\n"

            t_engine = time.time()
            result = adapter.process_query(request.query)
            engine_time = time.time() - t_engine

            # Emit reasoning steps from the result
            for i, step in enumerate(result.reasoning_summary):
                step_id = step.get('step', f'step_{i}').lower().replace(' ', '_')
                yield f"data: {json.dumps({'type': 'inference', 'step': step_id, 'status': 'done', 'detail': f'{step.get("icon", "🔍")} {step.get("step", "")}: {step.get("description", "")}', 'data': step.get('graph_traversals', [])})}\n\n"

            # Build deep-explainable-compatible response
            segments = result.content_segments or []
            # Ensure segments are dicts
            safe_segments = [s for s in segments if isinstance(s, dict)]
            if not safe_segments:
                safe_segments = [{"text": "The neuro-symbolic engine completed but found no matching items in the graph. This graph uses domain-specific node types (ProductVariant, Application, Risk) rather than the universal schema (Item, Context, Property) expected by this engine.", "type": "GENERAL"}]

            response_data = {
                "reasoning_summary": result.reasoning_summary or [],
                "content_segments": safe_segments,
                "product_card": result.product_card,
                "clarification_needed": result.clarification is not None,
                "clarification": result.clarification,
                "risk_detected": result.risk_detected,
                "risk_severity": result.risk_severity,
                "policy_warnings": result.policy_warnings or [],
                "graph_facts_count": len([s for s in safe_segments if isinstance(s, dict) and s.get('type') == 'GRAPH_FACT']),
                "inference_count": len([s for s in safe_segments if isinstance(s, dict) and s.get('type') == 'INFERENCE']),
                "timings": {"engine": round(engine_time, 2), "total": round(time.time() - t_start, 2)},
            }

            yield f"data: {json.dumps({'type': 'complete', 'response': response_data, 'timings': {'engine': round(engine_time, 2), 'total': round(time.time() - t_start, 2)}})}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/graph/init-vector-index")
async def init_vector_index(_user: str = Depends(get_current_user)):
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
async def learn_rule(request: LearnRuleRequest, _user: str = Depends(get_current_user)):
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
async def get_learned_rules(_user: str = Depends(get_current_user)):
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
async def delete_learned_rule(trigger: str, rule: str, _user: str = Depends(get_current_user)):
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
async def init_learned_rules_index(_user: str = Depends(get_current_user)):
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
async def list_products(_user: str = Depends(get_current_user)):
    """List all products with their competitor mappings."""
    try:
        products = db.get_all_products()
        return ProductListResponse(products=products)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/knowledge/timeline")
async def get_project_timeline(project_name: str, _user: str = Depends(get_current_user)):
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
async def get_explorer_projects(_user: str = Depends(get_current_user)):
    """Get all projects with details for the data explorer."""
    try:
        projects = db.get_all_projects_with_details()
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explorer/projects/{project_name}")
async def get_explorer_project_details(project_name: str, _user: str = Depends(get_current_user)):
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
async def get_explorer_concepts(_user: str = Depends(get_current_user)):
    """Get all concepts with details for the data explorer."""
    try:
        concepts = db.get_all_concepts_with_details()
        return {"concepts": concepts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explorer/concepts/{concept_name}")
async def get_explorer_concept_details(concept_name: str, _user: str = Depends(get_current_user)):
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
async def get_explorer_observations(_user: str = Depends(get_current_user)):
    """Get all observations with details for the data explorer."""
    try:
        observations = db.get_all_observations_with_details()
        return {"observations": observations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explorer/actions")
async def get_explorer_actions(_user: str = Depends(get_current_user)):
    """Get all actions with details for the data explorer."""
    try:
        actions = db.get_all_actions_with_details()
        return {"actions": actions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explorer/competitors")
async def get_explorer_competitors(_user: str = Depends(get_current_user)):
    """Get all competitor products with details for the data explorer."""
    try:
        competitors = db.get_all_competitors_with_details()
        return {"competitors": competitors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Thread Explorer Endpoints
@app.get("/threads")
async def list_threads(_user: str = Depends(get_current_user)):
    """Get all email threads (projects) with summary info."""
    try:
        threads = db.get_all_threads_summary()
        return {"threads": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/threads/{project_name}")
async def get_thread_details(project_name: str, _user: str = Depends(get_current_user)):
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
async def delete_thread(project_name: str, _user: str = Depends(get_current_user)):
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
async def get_knowledge_candidates(status: str | None = None, _user: str = Depends(get_current_user)):
    """Get knowledge candidates for verification.

    Query params:
    - status: Filter by status (pending, verified, rejected). Default: all.
    """
    try:
        candidates = db.get_all_knowledge_candidates(status=status)
        # Merge graph-derived rule candidates (always available for pending view)
        if status is None or status == "pending":
            graph_rules = db.get_graph_rules_as_candidates()
        else:
            graph_rules = []
        return {"candidates": candidates + graph_rules}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/knowledge/verify")
async def verify_knowledge_candidate(request: KnowledgeVerifyRequest, _user: str = Depends(get_current_user)):
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
async def get_knowledge_library(_user: str = Depends(get_current_user)):
    """Get all verified knowledge sources (the Knowledge Library).

    Returns verified sources with their usage frequency and aliases.
    """
    try:
        sources = db.get_verified_sources_library()
        return {"sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/knowledge/library/{source_id}")
async def get_knowledge_source_details(source_id: str, _user: str = Depends(get_current_user)):
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
async def delete_knowledge_candidate(candidate_id: str, _user: str = Depends(get_current_user)):
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
async def get_expert_knowledge_map(_user: str = Depends(get_current_user)):
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
async def get_knowledge_stats(_user: str = Depends(get_current_user)):
    """Get knowledge discovery statistics.

    Returns counts of pending candidates, verified sources, coverage metrics.
    """
    try:
        stats = db.get_knowledge_stats()
        # Include graph-derived rules in the pending count
        graph_rules = db.get_graph_rules_as_candidates()  # cached
        stats["pending"] = stats.get("pending", 0) + len(graph_rules)
        stats["total_candidates"] = stats.get("total_candidates", 0) + len(graph_rules)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Document Ingestion Endpoints (Generic Two-Pass AI)
@app.post("/ingest/doc/analyze")
async def analyze_document(
    file: UploadFile = File(...),
    document_hint: str = Form(None),
    _user: str = Depends(get_current_user)
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
    source_name: str = Form(None),
    _user: str = Depends(get_current_user)
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


# =============================================================================
# Multi-LLM Test Generator Endpoints
# =============================================================================

from api_keys import api_keys_manager
from pydantic import BaseModel as PydanticBaseModel


class ApproveTestsRequest(PydanticBaseModel):
    tests: list


GENERATED_TESTS_FILE = STATIC_DIR / "generated-tests.json"
PRODUCT_CATALOG_PDF = Path(__file__).parent.parent / "testdata" / "filter_housings_sweden.pdf"


@app.get("/config/api-keys")
async def get_api_keys(_user: str = Depends(get_current_user)):
    """Get status of all LLM provider API keys (read-only, from env vars)."""
    return api_keys_manager.get_status()


@app.post("/test-generator/debate/stream")
async def start_debate_stream(
    config: str = Form("{}"),
    _user: str = Depends(get_current_user),
):
    """Start a multi-LLM debate to generate test cases from the product catalog PDF.

    Config JSON fields:
    - selected_providers: ["openai", "gemini", "anthropic"]
    - target_test_count: 15
    - category_focus: "env" (optional)

    Returns SSE stream with debate events.
    """
    from llm_providers import get_all_providers
    from debate_orchestrator import DebateOrchestrator, DebateConfig

    if not PRODUCT_CATALOG_PDF.exists():
        raise HTTPException(status_code=500, detail=f"Product catalog PDF not found at {PRODUCT_CATALOG_PDF}")

    pdf_bytes = PRODUCT_CATALOG_PDF.read_bytes()

    # Parse config
    try:
        config_dict = json.loads(config)
    except json.JSONDecodeError:
        config_dict = {}

    debate_config = DebateConfig(
        selected_providers=config_dict.get("selected_providers", ["openai", "gemini", "anthropic"]),
        target_test_count=config_dict.get("target_test_count", 15),
        category_focus=config_dict.get("category_focus"),
    )

    # Get providers that are both configured and selected
    all_providers = get_all_providers()
    selected = [p for p in all_providers
                if p.name in debate_config.selected_providers and p.is_configured()]

    if not selected:
        raise HTTPException(
            status_code=400,
            detail="No LLM providers configured. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY env vars."
        )

    # Get existing test names to avoid duplicates
    existing_names = []
    results_path = STATIC_DIR / "test-results.json"
    if results_path.exists():
        try:
            results_data = json.loads(results_path.read_text())
            existing_names = [t.get("name", "") for t in results_data.get("tests", [])]
        except (json.JSONDecodeError, KeyError):
            pass
    # Also include previously generated tests
    if GENERATED_TESTS_FILE.exists():
        try:
            gen_data = json.loads(GENERATED_TESTS_FILE.read_text())
            existing_names.extend([t.get("name", "") for t in gen_data])
        except (json.JSONDecodeError, KeyError):
            pass

    orchestrator = DebateOrchestrator(
        providers=selected,
        pdf_bytes=pdf_bytes,
        pdf_mime_type="application/pdf",
        existing_test_names=existing_names,
        config=debate_config,
    )

    async def generate():
        try:
            async for event in orchestrator.run_debate():
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/test-generator/approve")
async def approve_generated_tests(request: ApproveTestsRequest, _user: str = Depends(get_current_user)):
    """Approve selected test cases and add them to the generated tests file."""
    import datetime

    # Load existing generated tests
    existing = []
    if GENERATED_TESTS_FILE.exists():
        try:
            existing = json.loads(GENERATED_TESTS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            existing = []

    existing_names = {t.get("name") for t in existing}

    added = 0
    for test in request.tests:
        name = test.get("name", "")
        if name and name not in existing_names:
            test["approved_at"] = datetime.datetime.utcnow().isoformat() + "Z"
            existing.append(test)
            existing_names.add(name)
            added += 1

    GENERATED_TESTS_FILE.write_text(json.dumps(existing, indent=2))
    return {"status": "ok", "added": added, "total": len(existing)}


@app.get("/test-generator/approved")
async def get_approved_tests(_user: str = Depends(get_current_user)):
    """List all previously approved generated tests."""
    if GENERATED_TESTS_FILE.exists():
        try:
            return json.loads(GENERATED_TESTS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


@app.delete("/test-generator/approved/{test_name}")
async def delete_approved_test(test_name: str, _user: str = Depends(get_current_user)):
    """Remove a specific approved test by name."""
    if not GENERATED_TESTS_FILE.exists():
        raise HTTPException(status_code=404, detail="No generated tests file")

    try:
        tests = json.loads(GENERATED_TESTS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        raise HTTPException(status_code=500, detail="Failed to read generated tests")

    original_count = len(tests)
    tests = [t for t in tests if t.get("name") != test_name]

    if len(tests) == original_count:
        raise HTTPException(status_code=404, detail=f"Test '{test_name}' not found")

    GENERATED_TESTS_FILE.write_text(json.dumps(tests, indent=2))
    return {"status": "ok", "removed": test_name, "remaining": len(tests)}


# =============================================================================
# LLM-AS-A-JUDGE ENDPOINTS
# =============================================================================

JUDGE_RESULTS_FILE = STATIC_DIR / "judge-results.json"
JUDGE_QUESTIONS_FILE = STATIC_DIR / "judge-questions.json"


class JudgeRunRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class JudgeBatchRequest(BaseModel):
    test_filter: str = "all"
    limit: int = 0


class ApproveJudgeQuestionsRequest(BaseModel):
    questions: list[dict]


@app.post("/judge/run/stream")
async def judge_single_stream(request: JudgeRunRequest, _user: str = Depends(get_current_user)):
    """Judge a single question in real-time via SSE.

    Sends the question to Graph Reasoning, collects the response,
    then evaluates it with Gemini 3 Pro Preview across 6 dimensions.
    """
    from judge import JudgeOrchestrator

    orchestrator = JudgeOrchestrator()

    async def generate():
        try:
            async for event in orchestrator.run_single_streaming(
                request.question, request.session_id
            ):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/judge/batch/stream")
async def judge_batch_stream(request: JudgeBatchRequest, _user: str = Depends(get_current_user)):
    """Run judge on test suite via SSE with streaming progress."""
    from judge import JudgeOrchestrator

    orchestrator = JudgeOrchestrator()

    async def generate():
        try:
            async for event in orchestrator.run_batch_streaming(
                request.test_filter, request.limit
            ):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/judge/results")
async def get_judge_results(_user: str = Depends(get_current_user)):
    """Serve the latest judge results JSON."""
    if JUDGE_RESULTS_FILE.exists():
        return FileResponse(JUDGE_RESULTS_FILE, media_type="application/json")
    raise HTTPException(status_code=404, detail="No judge results available yet")


@app.post("/judge/generate/stream")
async def generate_judge_questions_stream(
    file: UploadFile = File(...),
    config: str = Form("{}"),
    _user: str = Depends(get_current_user),
):
    """Generate evaluation questions from a PDF via Gemini 3 Pro."""
    from judge import JudgeOrchestrator

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files supported")

    pdf_bytes = await file.read()
    config_dict = json.loads(config)
    orchestrator = JudgeOrchestrator()

    async def generate():
        try:
            async for event in orchestrator.generate_questions_streaming(
                pdf_bytes, config_dict
            ):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/judge/questions")
async def approve_judge_questions(
    request: ApproveJudgeQuestionsRequest, _user: str = Depends(get_current_user)
):
    """Save approved generated questions to judge-questions.json."""
    import datetime as dt

    existing = []
    if JUDGE_QUESTIONS_FILE.exists():
        try:
            existing = json.loads(JUDGE_QUESTIONS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            existing = []

    existing_ids = {q.get("id") for q in existing}
    added = 0
    for q in request.questions:
        qid = q.get("id", str(uuid.uuid4()))
        if qid not in existing_ids:
            q["id"] = qid
            q["approved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            existing.append(q)
            existing_ids.add(qid)
            added += 1

    JUDGE_QUESTIONS_FILE.write_text(json.dumps(existing, indent=2))
    return {"status": "ok", "added": added, "total": len(existing)}


@app.get("/judge/questions")
async def get_judge_questions(_user: str = Depends(get_current_user)):
    """List all approved judge questions."""
    if JUDGE_QUESTIONS_FILE.exists():
        try:
            return json.loads(JUDGE_QUESTIONS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


class JudgeEvaluateRequest(BaseModel):
    question: str
    response_data: dict


@app.post("/judge/evaluate")
async def judge_evaluate(request: JudgeEvaluateRequest, _user: str = Depends(get_current_user)):
    """Judge a pre-existing response with Gemini + OpenAI in parallel.

    Both judges receive the product catalog PDF for ground-truth verification.
    Used by the main chat to auto-judge Graph Reasoning responses.
    """
    from judge import judge_parallel

    return await judge_parallel(request.question, request.response_data)


# =============================================================================
# Expert Review Endpoints
# =============================================================================

class ExpertReviewRequest(BaseModel):
    comment: str = ""
    overall_score: str  # "thumbs_up" or "thumbs_down"
    dimension_scores: Optional[dict] = None
    provider: Optional[str] = None  # "gemini", "openai", "anthropic" for per-judge review
    turn_number: Optional[int] = None


class SaveJudgeResultsRequest(BaseModel):
    turn_number: int
    judge_results: dict  # {gemini: {...}, openai: {...}, anthropic: {...}}


@app.get("/expert/conversations")
async def list_expert_conversations(
    limit: int = 50,
    offset: int = 0,
    _user: dict = Depends(get_current_user_info),
):
    """List all conversations with turn counts and review status."""
    return db.get_expert_conversations(limit=limit, offset=offset)


@app.get("/expert/conversations/{session_id}")
async def get_expert_conversation(
    session_id: str,
    _user: dict = Depends(get_current_user_info),
):
    """Get full conversation detail with turns, reviews, and judge results."""
    detail = db.get_conversation_detail(session_id)

    # Scan judge results file for matching session
    judge_results = None
    try:
        judge_path = os.path.join(os.path.dirname(__file__), "static", "judge-results.json")
        if os.path.exists(judge_path):
            with open(judge_path, "r") as f:
                all_judges = json.load(f)
            for jr in all_judges:
                if jr.get("session_id", "").endswith(session_id) or session_id in jr.get("session_id", ""):
                    judge_results = jr.get("judges")
                    break
    except Exception:
        pass

    detail["judge_results"] = judge_results
    return detail


@app.post("/expert/review/{session_id}")
async def submit_expert_review(
    session_id: str,
    review: ExpertReviewRequest,
    user_info: dict = Depends(get_current_user_info),
):
    """Submit an expert review (comment + thumbs up/down) for a conversation or a specific judge."""
    if review.overall_score not in ("thumbs_up", "thumbs_down"):
        raise HTTPException(400, "overall_score must be 'thumbs_up' or 'thumbs_down'")
    if review.provider and review.provider not in ("gemini", "openai", "anthropic"):
        raise HTTPException(400, "provider must be 'gemini', 'openai', or 'anthropic'")

    dimension_json = json.dumps(review.dimension_scores) if review.dimension_scores else None
    result = db.submit_expert_review(
        session_id=session_id,
        reviewer=user_info["username"],
        comment=review.comment,
        overall_score=review.overall_score,
        dimension_scores=dimension_json,
        provider=review.provider,
        turn_number=review.turn_number,
    )
    return {"status": "ok", "review": result}


@app.post("/session/{session_id}/judge-results")
async def save_judge_results(
    session_id: str,
    body: SaveJudgeResultsRequest,
    _user: dict = Depends(get_current_user_info),
):
    """Persist judge evaluation results on a conversation turn (called from chat UI)."""
    ok = db.save_judge_results(
        session_id=session_id,
        turn_number=body.turn_number,
        judge_results=json.dumps(body.judge_results),
    )
    if not ok:
        raise HTTPException(404, "Turn not found")
    return {"status": "ok"}


@app.get("/expert/reviews")
async def get_expert_reviews_summary(
    _user: dict = Depends(get_current_user_info),
):
    """Get aggregate expert review statistics and recent reviews."""
    return db.get_expert_reviews_summary()


# =============================================================================
# Graph Audit Debate Endpoints
# =============================================================================

class GraphAuditRequest(BaseModel):
    selected_providers: list[str] = ["openai", "gemini_pro", "anthropic_opus"]
    audit_scope: str = "full"


@app.post("/graph-audit/debate/stream")
async def graph_audit_debate_stream(
    config: str = Form("{}"),
    _user: dict = Depends(get_current_user_info),
):
    """Run a 3-round multi-LLM debate to audit the knowledge graph against the PDF catalog."""
    from graph_auditor import GraphAuditOrchestrator, GraphAuditConfig, build_graph_data_snapshot
    from llm_providers import get_audit_providers

    # Load PDF
    pdf_path = os.path.join(os.path.dirname(__file__), "..", "testdata", "filter_housings_sweden.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(404, f"PDF catalog not found at {pdf_path}")

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    # Parse config
    try:
        cfg = json.loads(config) if config else {}
    except json.JSONDecodeError:
        cfg = {}

    audit_config = GraphAuditConfig(
        selected_providers=cfg.get("selected_providers", ["openai", "gemini_pro", "anthropic_opus"]),
        audit_scope=cfg.get("audit_scope", "full"),
    )

    # Get providers
    all_providers = get_audit_providers()
    selected = [p for p in all_providers if p.name in audit_config.selected_providers]
    if not selected:
        raise HTTPException(400, "No configured providers match the selection")

    # Build graph data snapshot
    graph_data_str = build_graph_data_snapshot(db)

    orchestrator = GraphAuditOrchestrator(
        providers=selected,
        pdf_bytes=pdf_bytes,
        graph_data_str=graph_data_str,
        config=audit_config,
    )

    async def generate():
        try:
            async for event in orchestrator.run_debate():
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/graph-audit/results")
async def get_graph_audit_results(
    _user: dict = Depends(get_current_user_info),
):
    """Get the latest graph audit debate report."""
    reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    if not os.path.exists(reports_dir):
        return {"error": "No reports directory"}

    # Find latest report
    report_files = sorted(
        [f for f in os.listdir(reports_dir) if f.startswith("graph_audit_debate_") and f.endswith(".json")],
        reverse=True,
    )
    if not report_files:
        return {"error": "No audit reports found"}

    with open(os.path.join(reports_dir, report_files[0]), "r") as f:
        return json.load(f)


@app.get("/graph-audit/results/list")
async def list_graph_audit_results(
    _user: dict = Depends(get_current_user_info),
):
    """List all available graph audit reports."""
    reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    if not os.path.exists(reports_dir):
        return []

    results = []
    for fname in sorted(os.listdir(reports_dir), reverse=True):
        if not (fname.startswith("graph_audit_debate_") and fname.endswith(".json")):
            continue
        try:
            with open(os.path.join(reports_dir, fname), "r") as f:
                data = json.load(f)
            meta = data.get("meta", {})
            final = data.get("final_report", {})
            results.append({
                "filename": fname,
                "timestamp": meta.get("timestamp", ""),
                "overall_score": final.get("overall_score", 0),
                "total_findings": final.get("total_findings", 0),
                "providers": meta.get("providers", []),
                "duration_s": meta.get("duration_s", 0),
            })
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Bulk Offer endpoints
# ---------------------------------------------------------------------------

from bulk_offer import (
    parse_excel, parse_pdf_order, analyze_order, llm_analyze_order,
    generate_offer_streaming, generate_offer_excel, llm_interpret_refinement,
    draft_offer_email, OfferConfig, _offer_sessions, _load_housing_variants,
    _load_capacity_rules,
    # Cross-reference mode
    parse_competitor_document, analyze_competitor_order, llm_analyze_crossref,
    generate_crossref_offer_streaming, llm_interpret_crossref_refinement,
)


class BulkGenerateRequest(BaseModel):
    offer_id: str
    material_code: str = "AZ"
    housing_length: int = 850
    filter_class: str = "ePM1 65%"
    product_family: str = "GDMI"
    overrides: dict = {}


class BulkChatRequest(BaseModel):
    offer_id: str
    message: str


class BulkRefineRequest(BaseModel):
    offer_id: str
    changes: dict = {}


class BulkEmailRequest(BaseModel):
    offer_id: str
    language: str = "sv"


@app.post("/offers/bulk/analyze")
async def bulk_analyze(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload and analyze an Excel or PDF order file."""
    file_bytes = await file.read()
    filename = file.filename or "upload"

    try:
        if filename.lower().endswith(".pdf"):
            rows = parse_pdf_order(file_bytes, filename)
        else:
            rows = parse_excel(file_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    if not rows:
        raise HTTPException(status_code=400, detail="No data rows found in file")

    analysis = analyze_order(rows, db)

    # Run LLM analysis in background
    try:
        variants = _load_housing_variants(db)
        capacity_rules = _load_capacity_rules(db)
        llm_result = llm_analyze_order(rows, variants, capacity_rules, filename)
        analysis["llm_analysis"] = llm_result
        # Store on session too
        session = _offer_sessions.get(analysis["offer_id"])
        if session:
            session.llm_analysis = llm_result
            session.filename = filename
    except Exception as e:
        analysis["llm_analysis"] = None

    analysis["filename"] = filename
    return analysis


@app.post("/offers/bulk/generate/stream")
async def bulk_generate_stream(req: BulkGenerateRequest, user=Depends(get_current_user)):
    """Generate offer with SSE streaming."""
    config = OfferConfig(
        material_code=req.material_code,
        housing_length=req.housing_length,
        filter_class=req.filter_class,
        product_family=req.product_family,
        overrides=req.overrides,
    )

    def event_stream():
        for event in generate_offer_streaming(req.offer_id, config, db):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/offers/bulk/chat")
async def bulk_chat(req: BulkChatRequest, user=Depends(get_current_user)):
    """LLM-powered refinement chat."""
    result = llm_interpret_refinement(req.message, req.offer_id, db)
    return result


@app.post("/offers/bulk/refine/stream")
async def bulk_refine(req: BulkRefineRequest, user=Depends(get_current_user)):
    """Apply row-level changes to an offer session."""
    session = _offer_sessions.get(req.offer_id)
    if not session:
        raise HTTPException(status_code=404, detail="Offer session not found")

    # Apply changes to original rows
    for row_id_str, changes in req.changes.items():
        row_id = int(row_id_str)
        for row in session.original_rows:
            if row.row_id == row_id:
                for field, value in changes.items():
                    if hasattr(row, field):
                        setattr(row, field, value)
                break

    return {"status": "ok", "changes_applied": len(req.changes)}


@app.post("/offers/bulk/email")
async def bulk_email(req: BulkEmailRequest, user=Depends(get_current_user)):
    """Draft a customer email for the offer."""
    result = draft_offer_email(req.offer_id, req.language)
    if not result:
        raise HTTPException(status_code=404, detail="Offer session not found or no results")
    return result


@app.get("/offers/bulk/export")
async def bulk_export(offer_id: str, user=Depends(get_current_user)):
    """Export offer as Excel file."""
    excel_bytes = generate_offer_excel(offer_id)
    if not excel_bytes:
        raise HTTPException(status_code=404, detail="Offer not found or no results")

    return StreamingResponse(
        iter([excel_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=offer_{offer_id}.xlsx"},
    )


# ---------------------------------------------------------------------------
# Bulk Offer — Competitor Cross-Reference endpoints
# ---------------------------------------------------------------------------

@app.post("/offers/bulk/crossref/analyze")
async def crossref_analyze(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload and analyze a competitor product document."""
    file_bytes = await file.read()
    filename = file.filename or "upload"

    try:
        items = parse_competitor_document(file_bytes, filename, db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse competitor document: {e}")

    if not items:
        raise HTTPException(status_code=400, detail="No competitor products found in document")

    analysis = analyze_competitor_order(items, filename, db)

    # LLM summary
    try:
        llm_result = llm_analyze_crossref(items, analysis["cross_ref_results"], filename)
        analysis["llm_analysis"] = llm_result
    except Exception:
        analysis["llm_analysis"] = None

    analysis["filename"] = filename
    return analysis


@app.post("/offers/bulk/crossref/generate/stream")
async def crossref_generate_stream(req: BulkGenerateRequest, user=Depends(get_current_user)):
    """Generate MH offer from cross-referenced competitor items (SSE streaming)."""
    config = OfferConfig(
        material_code=req.material_code,
        housing_length=req.housing_length,
        filter_class=req.filter_class,
        product_family=req.product_family,
        overrides=req.overrides,
    )

    def event_stream():
        for event in generate_crossref_offer_streaming(req.offer_id, config, db):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/offers/bulk/crossref/chat")
async def crossref_chat(req: BulkChatRequest, user=Depends(get_current_user)):
    """LLM-powered refinement for cross-reference results."""
    result = llm_interpret_crossref_refinement(req.message, req.offer_id, db)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
