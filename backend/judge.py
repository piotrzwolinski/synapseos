"""
LLM-as-a-Judge evaluation system for SynapseOS Graph Reasoning.

Multi-LLM parallel judging: Gemini 3 Pro Preview + GPT-5.2.
Both judges receive the product catalog PDF for ground-truth verification.
Evaluates across 6 dimensions: correctness, completeness, safety, tone,
reasoning_quality, constraint_adherence.
"""

import json
import time
import uuid
import asyncio
import base64
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, AsyncGenerator

from api_keys import api_keys_manager
from judge_prompts import (
    JUDGE_SYSTEM_PROMPT,
    JUDGE_USER_PROMPT_TEMPLATE,
    QUESTION_GENERATION_PROMPT,
)

JUDGE_MODEL = "gemini-3-pro-preview"
OPENAI_JUDGE_MODEL = "gpt-5.2"
CLAUDE_JUDGE_MODEL = "claude-opus-4-6"
JUDGE_RESULTS_FILE = Path(__file__).parent / "static" / "judge-results.json"
JUDGE_QUESTIONS_FILE = Path(__file__).parent / "static" / "judge-questions.json"

DIMENSIONS = [
    "correctness", "completeness", "safety",
    "tone", "reasoning_quality", "constraint_adherence",
]


@dataclass
class JudgeResult:
    scores: dict = field(default_factory=dict)
    overall_score: float = 0.0
    explanation: str = ""
    dimension_explanations: dict = field(default_factory=dict)
    strengths: list = field(default_factory=list)
    weaknesses: list = field(default_factory=list)
    pdf_citations: list = field(default_factory=list)  # specific facts verified against PDF
    recommendation: str = "FAIL"
    usage: dict = field(default_factory=dict)  # token usage: prompt, cached, output, duration_s


# ---------------------------------------------------------------------------
# Shared helpers — PDF file caching (upload once, reuse by ID)
# ---------------------------------------------------------------------------

_PDF_PATH = Path(__file__).parent.parent / "testdata" / "filter_housings_sweden.pdf"

# Gemini: file reference from Files API (persists 48h server-side)
_GEMINI_FILE_REF = None  # google.genai File object

# OpenAI: file_id from Files API
_OPENAI_FILE_ID: Optional[str] = None

# Gemini: explicit CachedContent name (PDF + system prompt, TTL 1h)
_GEMINI_CACHE_NAME: Optional[str] = None


def _load_pdf() -> Optional[bytes]:
    """Load PDF bytes from disk. Returns None if file not found."""
    if not _PDF_PATH.exists():
        print(f"  [JUDGE] WARNING: PDF not found at {_PDF_PATH}")
        return None
    return _PDF_PATH.read_bytes()


def _get_gemini_file():
    """Upload PDF to Gemini Files API once, return file ref for reuse."""
    global _GEMINI_FILE_REF
    if _GEMINI_FILE_REF is not None:
        return _GEMINI_FILE_REF
    if not _PDF_PATH.exists():
        print(f"  [JUDGE] WARNING: PDF not found at {_PDF_PATH}")
        return None
    from google import genai
    api_key = api_keys_manager.get_key("gemini")
    if not api_key:
        return None
    client = genai.Client(api_key=api_key)
    _GEMINI_FILE_REF = client.files.upload(file=str(_PDF_PATH))
    print(f"  [JUDGE] Uploaded PDF to Gemini Files API: {_GEMINI_FILE_REF.name}")
    return _GEMINI_FILE_REF


def _get_gemini_cache() -> Optional[str]:
    """Create/reuse Gemini explicit cache (PDF + system prompt). Returns cache name."""
    global _GEMINI_CACHE_NAME
    if _GEMINI_CACHE_NAME is not None:
        return _GEMINI_CACHE_NAME
    from google import genai
    from google.genai import types
    api_key = api_keys_manager.get_key("gemini")
    if not api_key:
        return None
    client = genai.Client(api_key=api_key)
    file_ref = _get_gemini_file()
    if not file_ref:
        return None
    try:
        cache = client.caches.create(
            model=f"models/{JUDGE_MODEL}",
            config=types.CreateCachedContentConfig(
                display_name="judge-pdf-cache",
                system_instruction=JUDGE_SYSTEM_PROMPT,
                contents=[file_ref],
                ttl="3600s",  # 1 hour
            ),
        )
        _GEMINI_CACHE_NAME = cache.name
        print(f"  [JUDGE] Created Gemini cache: {_GEMINI_CACHE_NAME}")
        return _GEMINI_CACHE_NAME
    except Exception as e:
        print(f"  [JUDGE] Gemini cache creation failed (will use inline): {e}")
        return None


def _get_openai_file_id() -> Optional[str]:
    """Upload PDF to OpenAI Files API once, return file_id for reuse."""
    global _OPENAI_FILE_ID
    if _OPENAI_FILE_ID is not None:
        return _OPENAI_FILE_ID
    if not _PDF_PATH.exists():
        print(f"  [JUDGE] WARNING: PDF not found at {_PDF_PATH}")
        return None
    api_key = api_keys_manager.get_key("openai")
    if not api_key:
        return None
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    with open(_PDF_PATH, "rb") as f:
        file_obj = client.files.create(file=f, purpose="user_data")
    _OPENAI_FILE_ID = file_obj.id
    print(f"  [JUDGE] Uploaded PDF to OpenAI Files API: {_OPENAI_FILE_ID}")
    return _OPENAI_FILE_ID


def _build_judge_prompt(question: str, response_data: dict) -> str:
    """Build the formatted user prompt from question + response data.

    If response_data contains 'conversation_history' (list of {role, content, ...}),
    formats the full multi-turn conversation. Otherwise falls back to single-response mode.
    """
    conversation_history = response_data.get("conversation_history")

    if conversation_history and isinstance(conversation_history, list):
        # Multi-turn: format the full conversation as the user sees it
        conversation_lines = []
        for turn in conversation_history:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            label = "USER" if role == "user" else "SYSTEM"
            conversation_lines.append(f"**{label}:** {content}")

            # Include product card if present (user-visible data)
            pc = turn.get("product_card")
            if pc:
                conversation_lines.append(f"  [Product Card: {json.dumps(pc)}]")
            pcs = turn.get("product_cards")
            if pcs:
                for card in pcs:
                    conversation_lines.append(f"  [Product Card: {json.dumps(card)}]")

            # Include status badges if present (warnings, environment blocks)
            badges = turn.get("status_badges")
            if badges:
                for badge in badges:
                    conversation_lines.append(f"  [{badge.get('type', 'INFO')}: {badge.get('text', '')}]")

        conversation_text = "\n\n".join(conversation_lines)
    else:
        # Single-response fallback
        response_text = (
            response_data.get("content_text")
            or response_data.get("response", {}).get("content_text", "")
        )
        conversation_text = f"**USER:** {question}\n\n**SYSTEM:** {response_text}"

    # Collect all product cards from the conversation
    product_card = response_data.get("product_card") or response_data.get("response", {}).get("product_card")
    product_cards = response_data.get("product_cards") or []
    if product_card and not product_cards:
        product_cards = [product_card]
    product_card_text = json.dumps(product_cards, indent=2) if product_cards else "(no product cards)"

    return JUDGE_USER_PROMPT_TEMPLATE.format(
        conversation=conversation_text,
        product_card=product_card_text,
    )


def _parse_judge_json(raw) -> JudgeResult:
    """Parse raw JSON string (or already-parsed dict) into JudgeResult, with truncation repair."""
    # Some SDKs auto-parse JSON responses into dicts
    if isinstance(raw, dict):
        parsed = raw
    elif not isinstance(raw, str):
        return JudgeResult(
            explanation=f"Unexpected judge response type: {type(raw).__name__}",
            recommendation="ERROR",
        )
    else:
        parsed = None

    if parsed is None:
        import re

        cleaned = raw.strip()

        # Strategy 1: Extract JSON from markdown code fences (```json ... ```)
        fence_match = re.search(r'```(?:json)?\s*\n(\{.*?\})\s*\n```', cleaned, re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        else:
            # Strategy 2: Find {"scores" pattern in preamble text
            json_match = re.search(r'\{\s*"scores"', cleaned)
            if json_match:
                cleaned = cleaned[json_match.start():]
                # Strip trailing markdown fence if present
                if cleaned.rstrip().endswith("```"):
                    cleaned = cleaned.rstrip()[:-3].rstrip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try repair from retriever, fall back to simple brace-closing
            repaired = cleaned
            try:
                from retriever import _repair_truncated_json
                repaired = _repair_truncated_json(cleaned)
            except Exception:
                # Simple repair: close any open braces/brackets
                open_braces = cleaned.count("{") - cleaned.count("}")
                open_brackets = cleaned.count("[") - cleaned.count("]")
                repaired = cleaned.rstrip().rstrip(",")
                repaired += "]" * max(0, open_brackets) + "}" * max(0, open_braces)
            # _repair_truncated_json may return a dict (already parsed) or string
            if isinstance(repaired, dict):
                parsed = repaired
            else:
                try:
                    parsed = json.loads(repaired)
                except (json.JSONDecodeError, TypeError):
                    return JudgeResult(
                        explanation=f"Failed to parse judge response: {str(raw)[:500]}",
                        recommendation="ERROR",
                    )

    return JudgeResult(
        scores=parsed.get("scores", {}),
        overall_score=parsed.get("overall_score", 0.0),
        explanation=parsed.get("explanation", ""),
        dimension_explanations=parsed.get("dimension_explanations", {}),
        strengths=parsed.get("strengths", []),
        weaknesses=parsed.get("weaknesses", []),
        pdf_citations=parsed.get("pdf_citations", []),
        recommendation=parsed.get("recommendation", "FAIL"),
    )


# ---------------------------------------------------------------------------
# Gemini judge (with PDF)
# ---------------------------------------------------------------------------

def _judge_with_gemini(question: str, response_data: dict) -> JudgeResult:
    """Call Gemini 3 Pro Preview to judge a single response, with PDF context.

    Strategy (cheapest first):
    1. Explicit cache (PDF + system prompt cached server-side, 1h TTL) → only send user prompt
    2. File ref (PDF uploaded once via Files API) → send file ref + system prompt + user prompt
    3. No PDF fallback → text-only
    """
    from google import genai
    from google.genai import types

    api_key = api_keys_manager.get_key("gemini")
    if not api_key:
        return JudgeResult(explanation="Gemini API key not configured", recommendation="ERROR")

    client = genai.Client(api_key=api_key)
    user_prompt = _build_judge_prompt(question, response_data)

    # Try explicit cache first (PDF + system prompt pre-cached)
    cache_name = _get_gemini_cache()
    config_kwargs = {
        "response_mime_type": "application/json",
        "max_output_tokens": 8192,
        "temperature": 0.0,
    }

    if cache_name:
        # Cache contains system prompt + PDF → only send user prompt as content
        contents = [types.Content(parts=[types.Part(text=user_prompt)])]
        config_kwargs["cached_content"] = cache_name
        print(f"  [JUDGE] Gemini: using explicit cache ({cache_name})")
    else:
        # Fallback: file ref from Files API (no re-upload, but no prompt caching)
        file_ref = _get_gemini_file()
        parts = []
        if file_ref:
            parts.append(types.Part.from_uri(file_uri=file_ref.uri, mime_type="application/pdf"))
            print(f"  [JUDGE] Gemini: using Files API ref ({file_ref.name})")
        else:
            print("  [JUDGE] Gemini: no PDF available, text-only evaluation")
        parts.append(types.Part(text=f"{JUDGE_SYSTEM_PROMPT}\n\n{user_prompt}"))
        contents = [types.Content(parts=parts)]

    t0 = time.time()
    try:
        response = client.models.generate_content(
            model=JUDGE_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        raw = response.text
        if isinstance(raw, str):
            raw = raw.strip()
        duration = round(time.time() - t0, 2)

        # Collect usage
        usage_data = {"duration_s": duration}
        usage = getattr(response, "usage_metadata", None)
        if usage:
            usage_data["prompt_tokens"] = getattr(usage, "prompt_token_count", 0) or 0
            usage_data["cached_tokens"] = getattr(usage, "cached_content_token_count", 0) or 0
            usage_data["output_tokens"] = getattr(usage, "candidates_token_count", 0) or 0
            print(f"  [JUDGE] Gemini responded in {duration}s | "
                  f"prompt={usage_data['prompt_tokens']}, "
                  f"cached={usage_data['cached_tokens']}, "
                  f"output={usage_data['output_tokens']}")
        else:
            print(f"  [JUDGE] Gemini responded in {duration}s (no usage data)")
    except Exception as e:
        print(f"  [JUDGE] Gemini call failed: {e}")
        return JudgeResult(explanation=f"Gemini judge failed: {e}", recommendation="ERROR")

    result = _parse_judge_json(raw)
    result.usage = usage_data
    return result


# ---------------------------------------------------------------------------
# OpenAI judge (with PDF)
# ---------------------------------------------------------------------------

def _judge_with_openai(question: str, response_data: dict) -> JudgeResult:
    """Call GPT-5.2 to judge a single response, with PDF context.

    Uses OpenAI Files API: PDF uploaded once, referenced by file_id on each call.
    OpenAI auto-caches matching prompt prefixes (50% discount on cached tokens).
    """
    from openai import OpenAI

    api_key = api_keys_manager.get_key("openai")
    if not api_key:
        return JudgeResult(explanation="OpenAI API key not configured", recommendation="ERROR")

    client = OpenAI(api_key=api_key)
    user_prompt = _build_judge_prompt(question, response_data)

    # Build user content: PDF by file_id (uploaded once) + text prompt
    user_content = []
    file_id = _get_openai_file_id()
    if file_id:
        user_content.append({
            "type": "input_file",
            "file_id": file_id,
        })
        print(f"  [JUDGE] GPT-5.2: using Files API ref ({file_id})")
    else:
        print("  [JUDGE] GPT-5.2: no PDF available, text-only evaluation")
    user_content.append({"type": "input_text", "text": user_prompt + "\n\nReturn your evaluation as a JSON object."})

    t0 = time.time()
    try:
        response = client.responses.create(
            model=OPENAI_JUDGE_MODEL,
            instructions=JUDGE_SYSTEM_PROMPT,
            input=[{"role": "user", "content": user_content}],
            text={"format": {"type": "json_object"}},
            max_output_tokens=4096,
        )
        raw = response.output_text.strip()
        duration = round(time.time() - t0, 2)

        # Collect usage
        usage_data = {"duration_s": duration}
        usage = getattr(response, "usage", None)
        if usage:
            usage_data["prompt_tokens"] = getattr(usage, "input_tokens", 0) or 0
            input_cached = getattr(usage, "input_tokens_details", None)
            usage_data["cached_tokens"] = getattr(input_cached, "cached_tokens", 0) if input_cached else 0
            usage_data["output_tokens"] = getattr(usage, "output_tokens", 0) or 0
            print(f"  [JUDGE] GPT-5.2 responded in {duration}s | "
                  f"prompt={usage_data['prompt_tokens']}, "
                  f"cached={usage_data['cached_tokens']}, "
                  f"output={usage_data['output_tokens']}")
        else:
            print(f"  [JUDGE] GPT-5.2 responded in {duration}s ({len(raw)} chars)")
    except Exception as e:
        print(f"  [JUDGE] GPT-5.2 call failed: {e}")
        return JudgeResult(explanation=f"GPT-5.2 judge failed: {e}", recommendation="ERROR")

    result = _parse_judge_json(raw)
    result.usage = usage_data
    return result


# ---------------------------------------------------------------------------
# Claude judge (with PDF)
# ---------------------------------------------------------------------------

def _judge_with_claude(question: str, response_data: dict) -> JudgeResult:
    """Call Claude Opus 4.6 to judge a single response, with PDF context.

    Uses Anthropic Messages API with native PDF document attachment.
    """
    import anthropic

    api_key = api_keys_manager.get_key("anthropic")
    if not api_key:
        return JudgeResult(explanation="Anthropic API key not configured", recommendation="ERROR")

    client = anthropic.Anthropic(api_key=api_key)
    user_prompt = _build_judge_prompt(question, response_data)

    # Build user content: PDF document + text prompt
    user_content = []
    pdf_bytes = _load_pdf()
    if pdf_bytes:
        file_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
        user_content.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": file_b64,
            },
            "cache_control": {"type": "ephemeral"},
        })
        print(f"  [JUDGE] Claude: PDF attached ({len(pdf_bytes):,} bytes)")
    else:
        print("  [JUDGE] Claude: no PDF available, text-only evaluation")
    user_content.append({"type": "text", "text": user_prompt + "\n\nReturn your evaluation as a JSON object."})

    t0 = time.time()
    try:
        response = client.messages.create(
            model=CLAUDE_JUDGE_MODEL,
            max_tokens=8192,
            temperature=0.0,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text if response.content else ""
        if isinstance(raw, str):
            raw = raw.strip()
        duration = round(time.time() - t0, 2)

        # Collect usage
        usage_data = {"duration_s": duration}
        usage = getattr(response, "usage", None)
        if usage:
            usage_data["prompt_tokens"] = getattr(usage, "input_tokens", 0) or 0
            usage_data["cached_tokens"] = getattr(usage, "cache_read_input_tokens", 0) or 0
            usage_data["output_tokens"] = getattr(usage, "output_tokens", 0) or 0
            print(f"  [JUDGE] Claude responded in {duration}s | "
                  f"prompt={usage_data['prompt_tokens']}, "
                  f"cached={usage_data['cached_tokens']}, "
                  f"output={usage_data['output_tokens']}")
        else:
            print(f"  [JUDGE] Claude responded in {duration}s (no usage data)")
    except Exception as e:
        print(f"  [JUDGE] Claude call failed: {e}")
        return JudgeResult(explanation=f"Claude judge failed: {e}", recommendation="ERROR")

    # Debug: log first 200 chars of raw response to diagnose parsing issues
    print(f"  [JUDGE] Claude raw response (first 200 chars): {repr(raw[:200])}")

    result = _parse_judge_json(raw)
    result.usage = usage_data
    return result


# Backward-compat alias used by batch/streaming orchestrator
_judge_response = _judge_with_gemini


# ---------------------------------------------------------------------------
# Parallel multi-LLM judge
# ---------------------------------------------------------------------------

async def judge_parallel(question: str, response_data: dict) -> dict:
    """Run Gemini + OpenAI + Claude judges in parallel, return all results."""
    loop = asyncio.get_event_loop()

    gemini_future = loop.run_in_executor(None, _judge_with_gemini, question, response_data)
    openai_future = loop.run_in_executor(None, _judge_with_openai, question, response_data)
    claude_future = loop.run_in_executor(None, _judge_with_claude, question, response_data)

    gemini_result, openai_result, claude_result = await asyncio.gather(
        gemini_future, openai_future, claude_future, return_exceptions=True
    )

    if isinstance(gemini_result, Exception):
        print(f"  [JUDGE] Gemini exception: {gemini_result}")
        gemini_result = JudgeResult(explanation=str(gemini_result), recommendation="ERROR")
    if isinstance(openai_result, Exception):
        print(f"  [JUDGE] OpenAI exception: {openai_result}")
        openai_result = JudgeResult(explanation=str(openai_result), recommendation="ERROR")
    if isinstance(claude_result, Exception):
        print(f"  [JUDGE] Claude exception: {claude_result}")
        claude_result = JudgeResult(explanation=str(claude_result), recommendation="ERROR")

    return {
        "gemini": asdict(gemini_result),
        "openai": asdict(openai_result),
        "anthropic": asdict(claude_result),
    }


# ---------------------------------------------------------------------------
# Call system (Graph Reasoning) internally
# ---------------------------------------------------------------------------

def _call_system(question: str, session_id: str = None) -> dict:
    """Call the deep-explainable streaming pipeline directly and collect the full response."""
    from retriever import query_deep_explainable_streaming

    sid = session_id or f"judge-{uuid.uuid4().hex[:12]}"
    inference_steps = []
    complete_data = {}

    for event in query_deep_explainable_streaming(question, session_id=sid):
        event_type = event.get("type")
        if event_type == "inference":
            inference_steps.append(event)
        elif event_type == "complete":
            complete_data = event
        # Ignore session_state events

    # Merge into a flat response dict the judge can evaluate
    response = complete_data.get("response", {})
    return {
        "content_text": response.get("content_text", ""),
        "product_card": response.get("product_card"),
        "product_cards": response.get("product_cards"),
        "clarification": response.get("clarification"),
        "clarification_needed": response.get("clarification_needed", False),
        "risk_detected": response.get("risk_detected", False),
        "inference_steps": inference_steps,
        "graph_report": complete_data.get("graph_report", {}),
        "technical_state": complete_data.get("technical_state", {}),
    }


def _call_system_streaming(question: str, queue: "asyncio.Queue", session_id: str = None):
    """Call system and push each event to the async queue for live streaming."""
    from retriever import query_deep_explainable_streaming

    sid = session_id or f"judge-{uuid.uuid4().hex[:12]}"
    inference_steps = []
    complete_data = {}

    for event in query_deep_explainable_streaming(question, session_id=sid):
        event_type = event.get("type")
        if event_type == "inference":
            inference_steps.append(event)
            queue.put_nowait({"type": "inference_step", "step": event.get("step", ""), "detail": event.get("detail", ""), "status": event.get("status", "")})
        elif event_type == "complete":
            complete_data = event

    response = complete_data.get("response", {})
    result = {
        "content_text": response.get("content_text", ""),
        "product_card": response.get("product_card"),
        "product_cards": response.get("product_cards"),
        "clarification": response.get("clarification"),
        "clarification_needed": response.get("clarification_needed", False),
        "risk_detected": response.get("risk_detected", False),
        "inference_steps": inference_steps,
        "graph_report": complete_data.get("graph_report", {}),
        "technical_state": complete_data.get("technical_state", {}),
    }
    queue.put_nowait({"type": "_done", "response_data": result})


# ---------------------------------------------------------------------------
# Orchestrator: streaming pipelines for the 3 modes
# ---------------------------------------------------------------------------

class JudgeOrchestrator:

    # --- Real-time: single question ---
    async def run_single_streaming(
        self, question: str, session_id: str = None
    ) -> AsyncGenerator[dict, None]:
        """Judge a single question with streaming SSE events including live inference steps."""
        yield {"type": "status", "message": "Sending question to Graph Reasoning..."}

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        # Run system call in background thread, streaming events via queue
        future = loop.run_in_executor(
            None, _call_system_streaming, question, queue, session_id
        )

        # Stream inference steps as they arrive
        response_data = None
        while True:
            # Check if thread is done
            if future.done() and queue.empty():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                if future.done() and queue.empty():
                    break
                continue

            if event["type"] == "inference_step":
                yield event
            elif event["type"] == "_done":
                response_data = event["response_data"]
                break

        # Ensure thread finished cleanly
        await future

        if response_data is None:
            yield {"type": "error", "detail": "System call returned no data"}
            return

        # Emit system response summary
        yield {
            "type": "system_response",
            "content_text": response_data.get("content_text", "")[:2000],
            "has_product_card": response_data.get("product_card") is not None,
            "has_clarification": response_data.get("clarification_needed", False),
            "inference_step_count": len(response_data.get("inference_steps", [])),
            "graph_report": response_data.get("graph_report", {}),
        }

        yield {"type": "status", "message": "Evaluating response with Gemini 3 Pro..."}

        result = await loop.run_in_executor(
            None, _judge_response, question, response_data
        )

        yield {
            "type": "judge_complete",
            "result": asdict(result),
            "question": question,
        }

    # --- Batch: run all tests ---
    async def run_batch_streaming(
        self, test_filter: str = "all", limit: int = 0
    ) -> AsyncGenerator[dict, None]:
        """Run judge on test cases with streaming progress."""
        import sys

        # Import test cases from run_tests.py
        test_runner_path = (
            Path(__file__).parent.parent / ".claude" / "skills" / "test-hvac" / "scripts"
        )
        sys.path.insert(0, str(test_runner_path))
        from run_tests import TEST_CASES

        # Filter
        if test_filter and test_filter != "all":
            cases = {
                k: v for k, v in TEST_CASES.items() if v.category == test_filter
            }
        else:
            cases = dict(TEST_CASES)

        if limit > 0:
            cases = dict(list(cases.items())[:limit])

        total = len(cases)
        yield {"type": "batch_start", "total": total, "filter": test_filter}

        results = []
        semaphore = asyncio.Semaphore(3)
        loop = asyncio.get_event_loop()

        async def _judge_one(name: str, tc) -> dict:
            async with semaphore:
                t0 = time.time()
                try:
                    response_data = await loop.run_in_executor(
                        None, _call_system, tc.query
                    )
                    judge_result = await loop.run_in_executor(
                        None, _judge_response, tc.query, response_data
                    )
                    duration = round(time.time() - t0, 2)
                    return {
                        "question_id": name,
                        "question_text": tc.query,
                        "description": tc.description,
                        "category": tc.category,
                        "system_response": {
                            "content_text": response_data.get("content_text", ""),
                            "graph_report": response_data.get("graph_report", {}),
                        },
                        "judge_result": asdict(judge_result),
                        "duration_s": duration,
                        "judged_at": datetime.now(timezone.utc).isoformat(),
                        "status": "ok",
                    }
                except Exception as e:
                    return {
                        "question_id": name,
                        "question_text": tc.query,
                        "description": tc.description,
                        "category": tc.category,
                        "judge_result": asdict(JudgeResult(
                            explanation=str(e), recommendation="ERROR"
                        )),
                        "duration_s": round(time.time() - t0, 2),
                        "status": "error",
                        "error": str(e),
                    }

        # Run with concurrency and yield progress
        completed = 0
        tasks = {
            asyncio.ensure_future(_judge_one(name, tc)): name
            for name, tc in cases.items()
        }

        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            completed += 1
            yield {
                "type": "test_progress",
                "current": completed,
                "total": total,
                "test_name": result["question_id"],
                "score": result["judge_result"].get("overall_score", 0),
                "recommendation": result["judge_result"].get("recommendation", "ERROR"),
            }

        # Compute summary
        scores = [
            r["judge_result"]["overall_score"]
            for r in results
            if r["judge_result"].get("overall_score", 0) > 0
        ]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        dist = {"5.0": 0, "4.0-4.9": 0, "3.0-3.9": 0, "2.0-2.9": 0, "1.0-1.9": 0}
        for s in scores:
            if s >= 5.0:
                dist["5.0"] += 1
            elif s >= 4.0:
                dist["4.0-4.9"] += 1
            elif s >= 3.0:
                dist["3.0-3.9"] += 1
            elif s >= 2.0:
                dist["2.0-2.9"] += 1
            else:
                dist["1.0-1.9"] += 1

        # Category breakdown
        cat_scores = {}
        for r in results:
            cat = r.get("category", "other")
            sc = r["judge_result"].get("overall_score", 0)
            if sc > 0:
                cat_scores.setdefault(cat, []).append(sc)
        category_summary = {
            cat: round(sum(vals) / len(vals), 2)
            for cat, vals in cat_scores.items()
        }

        # Save results
        output = {
            "meta": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "batch",
                "judge_model": JUDGE_MODEL,
                "total_questions": total,
                "avg_overall_score": avg_score,
                "score_distribution": dist,
                "category_summary": category_summary,
                "filter": test_filter,
            },
            "results": sorted(results, key=lambda r: r["judge_result"].get("overall_score", 0)),
        }

        JUDGE_RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        JUDGE_RESULTS_FILE.write_text(json.dumps(output, indent=2, default=str))

        yield {
            "type": "batch_complete",
            "summary": output["meta"],
            "results_saved": True,
        }

    # --- Generate questions from PDF ---
    async def generate_questions_streaming(
        self, pdf_bytes: bytes, config: dict
    ) -> AsyncGenerator[dict, None]:
        """Generate evaluation questions from PDF using Gemini 3 Pro."""
        from google import genai
        from google.genai import types

        api_key = api_keys_manager.get_key("gemini")
        if not api_key:
            yield {"type": "error", "detail": "Gemini API key not configured"}
            return

        target_count = config.get("target_count", 20)

        yield {
            "type": "generation_start",
            "target_count": target_count,
            "model": JUDGE_MODEL,
        }

        client = genai.Client(api_key=api_key)

        prompt = QUESTION_GENERATION_PROMPT.format(target_count=target_count)

        file_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        loop = asyncio.get_event_loop()

        def _call_gemini():
            return client.models.generate_content(
                model=JUDGE_MODEL,
                contents=[
                    types.Content(parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="application/pdf",
                                data=file_b64,
                            )
                        ),
                        types.Part(text=prompt),
                    ])
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=8192,
                    temperature=0.3,
                ),
            )

        yield {"type": "status", "message": "Analyzing PDF with Gemini 3 Pro..."}

        t0 = time.time()
        try:
            response = await loop.run_in_executor(None, _call_gemini)
            raw = response.text.strip()
            duration = round(time.time() - t0, 2)
        except Exception as e:
            yield {"type": "error", "detail": f"Gemini call failed: {e}"}
            return

        yield {"type": "status", "message": f"Generated in {duration}s, parsing..."}

        try:
            questions = json.loads(raw)
        except json.JSONDecodeError:
            try:
                from retriever import _repair_truncated_json
                questions = json.loads(_repair_truncated_json(raw))
            except Exception:
                yield {"type": "error", "detail": f"Failed to parse: {raw[:500]}"}
                return

        if not isinstance(questions, list):
            questions = questions.get("questions", []) if isinstance(questions, dict) else []

        # Add IDs
        for q in questions:
            q["id"] = q.get("id", uuid.uuid4().hex[:12])

        yield {
            "type": "generation_complete",
            "questions": questions,
            "count": len(questions),
            "duration_s": duration,
        }
