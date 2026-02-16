"""
Automated Conversation Test Runner (Batch Mode).

Sends test questions to the Graph Reasoning endpoint, uses Gemini to
auto-answer clarifications, records full conversations with internal data
(graph state, technical state, inference steps) and judge evaluations.

Generates per-test HTML chat reports + a summary judge report.

Usage:
    # Single test:
    TEST_QUESTION="I need a GDB..." python scripts/auto_conversation_test.py

    # Batch mode (first N tests from test-results.json):
    python scripts/auto_conversation_test.py --batch 10

    # Batch with concurrency:
    python scripts/auto_conversation_test.py --batch 10 --concurrency 5
"""

import asyncio
import argparse
import json
import os
import sys
import time
import uuid
import httpx
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("SYNAPSE_BASE_URL", "http://localhost:8000")
USERNAME = os.getenv("SYNAPSE_USER", "mh")
PASSWORD = os.getenv("SYNAPSE_PASS", "MHFind@r2026")
MAX_TURNS = 6
GEMINI_MODEL = "gemini-2.0-flash"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class ConversationTurn:
    def __init__(self, role: str, content: str, turn_number: int):
        self.role = role
        self.content = content
        self.turn_number = turn_number
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.clarification: Optional[dict] = None
        self.product_card: Optional[dict] = None
        self.product_cards: Optional[list] = None
        self.status_badges: Optional[list] = None
        self.inference_steps: list = []
        self.judge_results: Optional[dict] = None
        self.is_complete: bool = False
        # Internal data (for debugging)
        self.locked_context: Optional[dict] = None
        self.technical_state: Optional[dict] = None
        self.graph_report: Optional[dict] = None
        self.session_state: Optional[dict] = None
        self.content_segments: Optional[list] = None
        self.raw_response: Optional[dict] = None


class TestResult:
    def __init__(self, name: str, description: str, query: str):
        self.name = name
        self.description = description
        self.query = query
        self.turns: list[ConversationTurn] = []
        self.session_id: str = str(uuid.uuid4())
        self.start_time: float = 0
        self.duration_s: float = 0
        self.error: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def get_auth_token(client: httpx.AsyncClient) -> str:
    resp = await client.post(f"{BASE_URL}/auth/login", json={
        "username": USERNAME, "password": PASSWORD,
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Gemini auto-player
# ---------------------------------------------------------------------------

def gemini_answer_clarification(
    conversation_so_far: list[ConversationTurn],
    clarification: dict,
) -> str:
    from google import genai
    gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    conv_text = ""
    for turn in conversation_so_far:
        prefix = "User" if turn.role == "user" else "System"
        conv_text += f"{prefix}: {turn.content}\n"

    options = clarification.get("options", [])
    options_text = ""
    for i, opt in enumerate(options, 1):
        if isinstance(opt, dict):
            label = opt.get("display_label") or opt.get("label") or opt.get("value", "")
            value = opt.get("value", label)
            options_text += f"  {i}. {label} (value: {value})\n"
        else:
            options_text += f"  {i}. {opt}\n"

    question = clarification.get("question", clarification.get("missing_info", ""))
    why = clarification.get("why_needed", "")

    prompt = f"""You are simulating a customer in a sales conversation about industrial filter housings.
The system has asked you a clarification question. Pick the most reasonable answer.

CONVERSATION SO FAR:
{conv_text}

SYSTEM ASKS: {question}
REASON: {why}

AVAILABLE OPTIONS:
{options_text}

Rules:
- Pick ONE option that makes technical sense for this product configuration.
- If options include specific values like "550mm" and "750mm", pick one that's common/standard.
- Reply with ONLY the exact option value (e.g. "750mm" or "550"). Nothing else.
- If you must pick "Other", reply with a reasonable numeric value.
"""

    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={"temperature": 0.0, "max_output_tokens": 64},
    )
    return response.text.strip().strip('"').strip("'")


# ---------------------------------------------------------------------------
# SSE stream consumer
# ---------------------------------------------------------------------------

async def send_message_streaming(
    client: httpx.AsyncClient, token: str, query: str, session_id: str,
    label: str = "",
) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    result = {
        "response_data": None,
        "locked_context": {},
        "technical_state": {},
        "inference_steps": [],
        "graph_report": {},
        "session_state": None,
    }

    async with client.stream(
        "POST", f"{BASE_URL}/consult/deep-explainable/stream",
        json={"query": query, "session_id": session_id},
        headers=headers, timeout=120.0,
    ) as resp:
        resp.raise_for_status()
        buffer = ""
        async for chunk in resp.aiter_text():
            buffer += chunk
            lines = buffer.split("\n")
            buffer = lines.pop()

            for line in lines:
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                if event.get("type") == "inference":
                    result["inference_steps"].append({
                        "step": event.get("step"),
                        "detail": event.get("detail"),
                        "status": event.get("status"),
                        "data": event.get("data"),
                    })
                elif event.get("type") == "complete":
                    result["response_data"] = event.get("response", {})
                    result["locked_context"] = event.get("locked_context", {})
                    result["technical_state"] = event.get("technical_state", {})
                    result["graph_report"] = event.get("graph_report", {})
                elif event.get("type") == "session_state":
                    result["session_state"] = event.get("data")
                elif event.get("type") == "error":
                    print(f"  [{label}] ERROR: {event.get('detail')}")

    return result


# ---------------------------------------------------------------------------
# Judge evaluation
# ---------------------------------------------------------------------------

async def evaluate_with_judges(
    client: httpx.AsyncClient, token: str, question: str,
    conversation_history: list[dict], response_data: dict,
    inference_steps: list[dict], graph_report: dict,
) -> Optional[dict]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    segments = response_data.get("content_segments", [])
    content_text = "".join(seg.get("text", "") for seg in segments) if isinstance(segments, list) else ""

    judge_payload = {
        "question": question,
        "response_data": {
            "conversation_history": conversation_history,
            "content_text": content_text,
            "product_card": response_data.get("product_card"),
            "product_cards": response_data.get("product_cards"),
            "clarification_needed": response_data.get("clarification_needed", False),
            "graph_report": graph_report,
            "inference_steps": inference_steps,
        },
    }

    try:
        resp = await client.post(
            f"{BASE_URL}/judge/evaluate", json=judge_payload,
            headers=headers, timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Judge evaluation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Single conversation runner
# ---------------------------------------------------------------------------

async def run_single_test(
    client: httpx.AsyncClient, token: str, test: TestResult,
    semaphore: asyncio.Semaphore,
) -> TestResult:
    async with semaphore:
        test.start_time = time.time()
        label = test.name
        locked_context: dict = {}
        technical_state: dict = {}
        turn_number = 0
        current_query = test.query

        try:
            while turn_number < MAX_TURNS:
                turn_number += 1

                # User turn
                user_turn = ConversationTurn("user", current_query, turn_number)
                test.turns.append(user_turn)

                # Build context
                query_with_context = current_query
                if locked_context:
                    parts = []
                    if locked_context.get("material"):
                        parts.append(f"material={locked_context['material']}")
                    if locked_context.get("project"):
                        parts.append(f"project={locked_context['project']}")
                    if locked_context.get("filter_depths"):
                        parts.append(f"filter_depths={','.join(str(d) for d in locked_context['filter_depths'])}")
                    if locked_context.get("dimension_mappings"):
                        dim_str = ",".join(
                            f"{d['width']}x{d['height']}" + (f"x{d['depth']}" if d.get('depth') else "")
                            for d in locked_context["dimension_mappings"]
                        )
                        parts.append(f"dimensions={dim_str}")
                    if parts:
                        query_with_context = f"{current_query} [LOCKED: {'; '.join(parts)}]"
                if technical_state:
                    query_with_context = f"{query_with_context} [STATE: {json.dumps(technical_state)}]"

                # System turn
                print(f"  [{label}] Turn {turn_number}: {current_query[:80]}...")
                stream_result = await send_message_streaming(
                    client, token, query_with_context, test.session_id, label
                )

                response_data = stream_result["response_data"] or {}
                locked_context.update(stream_result.get("locked_context") or {})
                technical_state.update(stream_result.get("technical_state") or {})

                segments = response_data.get("content_segments", [])
                content_text = "".join(seg.get("text", "") for seg in segments) if isinstance(segments, list) else "No response"

                assistant_turn = ConversationTurn("assistant", content_text, turn_number)
                assistant_turn.inference_steps = stream_result["inference_steps"]
                assistant_turn.clarification = response_data.get("clarification")
                assistant_turn.product_card = response_data.get("product_card")
                assistant_turn.product_cards = response_data.get("product_cards")
                assistant_turn.status_badges = response_data.get("status_badges")
                # Internal debug data
                assistant_turn.locked_context = dict(locked_context)
                assistant_turn.technical_state = dict(technical_state)
                assistant_turn.graph_report = stream_result.get("graph_report")
                assistant_turn.session_state = stream_result.get("session_state")
                assistant_turn.content_segments = response_data.get("content_segments")
                assistant_turn.raw_response = response_data

                # Judge
                conv_history = []
                for t in test.turns:
                    entry = {"role": t.role, "content": t.content, "product_card": None,
                             "product_cards": None, "clarification_needed": False, "status_badges": None}
                    if t.role == "assistant":
                        entry.update({"product_card": t.product_card, "product_cards": t.product_cards,
                                      "clarification_needed": t.clarification is not None, "status_badges": t.status_badges})
                    conv_history.append(entry)
                conv_history.append({
                    "role": "assistant", "content": content_text,
                    "product_card": response_data.get("product_card"),
                    "product_cards": response_data.get("product_cards"),
                    "clarification_needed": response_data.get("clarification_needed", False),
                    "status_badges": response_data.get("status_badges"),
                })

                judge_results = await evaluate_with_judges(
                    client, token, current_query, conv_history,
                    response_data, stream_result["inference_steps"],
                    stream_result.get("graph_report", {}),
                )
                assistant_turn.judge_results = judge_results
                test.turns.append(assistant_turn)

                # Score summary
                if judge_results:
                    scores = []
                    for prov, res in judge_results.items():
                        if isinstance(res, dict) and res.get("recommendation") != "ERROR":
                            scores.append(f"{prov}:{res.get('overall_score', '?')}")
                    print(f"  [{label}] Turn {turn_number} judges: {', '.join(scores)}")

                # Check complete
                if not response_data.get("clarification_needed") or not response_data.get("clarification"):
                    assistant_turn.is_complete = True
                    break

                # Auto-answer
                clarification = response_data["clarification"]
                answer = gemini_answer_clarification(test.turns, clarification)
                print(f"  [{label}] Auto-answer: {answer}")

                matched_value = answer
                for opt in clarification.get("options", []):
                    if isinstance(opt, dict):
                        lbl = opt.get("display_label") or opt.get("label") or opt.get("value", "")
                        val = opt.get("value", lbl)
                        if answer.lower() in lbl.lower() or answer.lower() in str(val).lower():
                            matched_value = f"{val} ({lbl})" if lbl != val else str(val)
                            break
                    elif answer.lower() in str(opt).lower():
                        matched_value = str(opt)
                        break
                current_query = matched_value

        except Exception as e:
            test.error = str(e)
            print(f"  [{label}] ERROR: {e}")

        test.duration_s = round(time.time() - test.start_time, 1)
        print(f"  [{label}] Done ({test.duration_s}s, {len(test.turns)} messages)")
        return test


# ---------------------------------------------------------------------------
# HTML generators
# ---------------------------------------------------------------------------

def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("\n", "<br>"))


def generate_chat_html(test: TestResult, output_path: Path) -> None:
    """Generate per-test HTML chat view."""

    def render_judge_badge(jr: dict) -> str:
        if not jr:
            return ""
        h = '<div class="judge-badges">'
        for prov, r in jr.items():
            if not isinstance(r, dict): continue
            sc = r.get("overall_score", 0)
            rec = r.get("recommendation", "FAIL")
            ok = rec == "PASS" or sc >= 4.0
            cls = "badge-pass" if ok else "badge-fail"
            icon = {"gemini": "✦", "openai": "⚙", "anthropic": "◈"}.get(prov, "●")
            lbl = {"gemini": "Gemini", "openai": "GPT-5.2", "anthropic": "Claude"}.get(prov, prov)
            h += f'<span class="judge-badge {cls}">{icon} {lbl} {sc}/5 <span class="bl">{"PASS" if ok else "FAIL"}</span></span>'
        return h + '</div>'

    def render_judge_details(jr: dict) -> str:
        if not jr: return ""
        h = '<div class="judge-details">'
        for prov, r in jr.items():
            if not isinstance(r, dict): continue
            lbl = {"gemini": "Gemini", "openai": "GPT-5.2", "anthropic": "Claude"}.get(prov, prov)
            dur = r.get("usage", {}).get("duration_s", 0)
            h += f'<div class="jc"><div class="jh"><strong>{lbl}</strong><span class="jt">{dur:.1f}s</span></div>'
            h += f'<p class="je">{_escape(r.get("explanation", ""))}</p>'
            scores = r.get("scores", {})
            dims = {"correctness": "COR", "completeness": "COM", "safety": "SAF", "tone": "TON", "reasoning_quality": "REA", "constraint_adherence": "CON"}
            h += '<div class="ds">'
            for d, s in dims.items():
                v = scores.get(d, 0)
                c = "dg" if v >= 4 else "dy" if v >= 3 else "dr"
                h += f'<span class="db {c}">{s}:{v}</span>'
            h += '</div>'
            cites = r.get("pdf_citations", [])
            if cites:
                h += '<div class="pc"><strong>PDF Citations</strong><ul>' + "".join(f'<li>{_escape(str(c))}</li>' for c in cites[:3]) + '</ul></div>'
            usage = r.get("usage", {})
            parts = []
            if usage.get("prompt_tokens"): parts.append(f"in:{usage['prompt_tokens']:,}")
            if usage.get("cached_tokens"): parts.append(f"cached:{usage['cached_tokens']:,}")
            if usage.get("output_tokens"): parts.append(f"out:{usage['output_tokens']:,}")
            if parts: h += f'<div class="ju">{" ".join(parts)}</div>'
            h += '</div>'
        return h + '</div>'

    def render_product_card(card: dict) -> str:
        if not card: return ""
        title = _escape(card.get("title", "Product"))
        h = f'<div class="pcard"><div class="pch">⊙ {title}</div><div class="pcs">'
        for k, v in card.get("specs", {}).items():
            h += f'<div class="sp"><span class="sl">{_escape(k.upper().replace("_", " "))}</span><span class="sv">{_escape(str(v))}</span></div>'
        return h + '</div></div>'

    def render_clarification(clar: dict) -> str:
        if not clar: return ""
        q = _escape(clar.get("question", ""))
        why = _escape(clar.get("why_needed", ""))
        h = f'<div class="cl"><div class="cb"></div><div class="cc"><strong>{q}</strong>'
        if why: h += f'<p class="cw">{why}</p>'
        h += '<div class="co">'
        for opt in clar.get("options", []):
            lbl = opt.get("display_label") or opt.get("label") or opt.get("value", "") if isinstance(opt, dict) else str(opt)
            h += f'<button class="btn">{_escape(lbl)}</button>'
        h += '<button class="btn bo">Other...</button></div></div></div>'
        return h

    def render_badges(badges: list) -> str:
        if not badges: return ""
        h = '<div class="sb">'
        for b in badges:
            t = b.get("type", "INFO")
            ic = "⚠" if t == "WARNING" else "✓" if t == "SUCCESS" else "ℹ"
            h += f'<div class="sbi s-{t.lower()}">{ic} {_escape(b.get("text", ""))}</div>'
        return h + '</div>'

    msgs = ""
    for turn in test.turns:
        if turn.role == "user":
            msgs += f'<div class="msg um"><div class="bub ub">{_escape(turn.content)}</div><div class="av ua">👤</div></div>'
        else:
            msgs += f'<div class="msg am"><div class="av aa">🤖</div><div class="bub ab">'
            msgs += render_badges(turn.status_badges)
            msgs += f'<div class="ct">{_escape(turn.content)}</div>'
            msgs += render_clarification(turn.clarification)
            msgs += render_product_card(turn.product_card)
            msgs += "".join(render_product_card(c) for c in (turn.product_cards or []))
            msgs += render_judge_badge(turn.judge_results)
            msgs += render_judge_details(turn.judge_results)
            msgs += '</div></div>'

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(test.name)} — {ts}</title>
<style>
:root{{--b:#2563eb;--v:#7c3aed;--s50:#f8fafc;--s100:#f1f5f9;--s200:#e2e8f0;--s400:#94a3b8;--s600:#475569;--s800:#1e293b;--s900:#0f172a}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,var(--s50),#eff6ff,#f5f3ff);min-height:100vh;color:var(--s800)}}
.hd{{background:#fff;border-bottom:1px solid var(--s200);padding:16px 24px;display:flex;align-items:center;gap:12px}}
.hl{{width:40px;height:40px;background:linear-gradient(135deg,var(--b),var(--v));border-radius:12px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:20px}}
.ht{{font-weight:700;font-size:18px;color:var(--s900)}}.hm{{margin-left:auto;color:var(--s400);font-size:13px}}
.wrap{{max-width:900px;margin:0 auto;padding:24px 16px}}
.msg{{display:flex;gap:12px;margin-bottom:24px;align-items:flex-start}}.um{{justify-content:flex-end}}
.av{{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}}
.ua{{background:linear-gradient(135deg,var(--b),var(--v));order:2}}.aa{{background:var(--s100);border:1px solid var(--s200)}}
.bub{{max-width:75%;padding:14px 18px;border-radius:18px;line-height:1.55;font-size:15px}}
.ub{{background:linear-gradient(135deg,var(--b),var(--v));color:#fff;border-bottom-right-radius:4px}}
.ab{{background:#fff;border:1px solid var(--s200);border-bottom-left-radius:4px;max-width:85%}}
.ct{{margin-bottom:8px}}
.cl{{display:flex;gap:12px;margin:16px 0;padding:16px 0;border-top:1px solid var(--s100)}}
.cb{{width:3px;background:var(--b);border-radius:2px;flex-shrink:0}}.cc{{flex:1}}.cc strong{{font-size:15px;display:block;margin-bottom:4px}}
.cw{{color:var(--s400);font-size:13px;margin-bottom:10px}}.co{{display:flex;gap:8px;flex-wrap:wrap}}
.btn{{padding:8px 20px;border:1px solid var(--s200);border-radius:20px;background:#fff;font-size:14px;cursor:pointer;color:var(--s800)}}
.bo{{border-style:dashed;color:var(--s400)}}
.pcard{{background:var(--s50);border:1px solid var(--s200);border-radius:12px;margin:12px 0;overflow:hidden}}
.pch{{padding:12px 16px;font-weight:600;font-size:15px;border-bottom:1px solid var(--s200)}}
.pcs{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--s200)}}
.sp{{background:#fff;padding:10px 16px}}.sl{{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--s400);margin-bottom:2px}}.sv{{font-size:14px;font-weight:500}}
.sb{{margin-bottom:8px}}.sbi{{display:inline-flex;align-items:center;gap:6px;padding:8px 14px;border-radius:8px;font-size:13px;margin-bottom:6px}}
.s-success{{background:#f0fdf4;border:1px solid #bbf7d0;color:#166534}}.s-warning{{background:#fefce8;border:1px solid #fef08a;color:#854d0e}}
.judge-badges{{display:flex;gap:8px;margin-top:12px;padding-top:12px;border-top:1px solid var(--s100);flex-wrap:wrap}}
.judge-badge{{display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:20px;font-size:13px;font-weight:500}}
.badge-pass{{background:#f0fdf4;border:1px solid #86efac;color:#166534}}.badge-fail{{background:#fef2f2;border:1px solid #fca5a5;color:#991b1b}}
.bl{{font-size:11px;font-weight:700;padding:1px 6px;border-radius:4px}}.badge-pass .bl{{background:#22c55e;color:#fff}}.badge-fail .bl{{background:#ef4444;color:#fff}}
.judge-details{{margin-top:8px;display:flex;flex-direction:column;gap:10px}}
.jc{{background:var(--s50);border:1px solid var(--s200);border-radius:10px;padding:12px 16px}}
.jh{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}}.jt{{color:var(--s400);font-size:12px}}
.je{{font-size:13px;color:var(--s600);margin-bottom:8px;line-height:1.5}}
.ds{{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px}}.db{{padding:2px 8px;border-radius:6px;font-size:12px;font-weight:600}}
.dg{{background:#dcfce7;color:#166534}}.dy{{background:#fef9c3;color:#854d0e}}.dr{{background:#fee2e2;color:#991b1b}}
.pc{{font-size:12px;color:var(--s600);margin-top:6px}}.pc ul{{margin-left:16px;margin-top:4px}}.pc li{{margin-bottom:2px}}
.ju{{font-size:11px;color:var(--s400);margin-top:6px;font-family:monospace}}
.ft{{text-align:center;padding:24px;color:var(--s400);font-size:12px}}
</style></head><body>
<div class="hd"><div class="hl">🧠</div><div><div class="ht">{_escape(test.name)}</div></div><div class="hm">{ts} · {test.duration_s}s</div></div>
<div class="wrap">{msgs}</div>
<div class="ft">{_escape(test.description)} · {len(test.turns)} messages</div>
</body></html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def generate_summary_html(tests: list[TestResult], output_path: Path) -> None:
    """Generate a summary report across all tests with judge opinions."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    providers = ["gemini", "openai", "anthropic"]
    prov_labels = {"gemini": "Gemini", "openai": "GPT-5.2", "anthropic": "Claude"}

    # Compute aggregates
    totals = {p: {"scores": [], "pass": 0, "fail": 0, "borderline": 0, "error": 0} for p in providers}

    rows = ""
    for test in tests:
        # Get the LAST assistant turn's judge results (final verdict)
        last_judge = None
        for t in reversed(test.turns):
            if t.role == "assistant" and t.judge_results:
                last_judge = t.judge_results
                break

        rows += f'<tr><td class="tn"><a href="{test.name}.html">{_escape(test.name)}</a><br><span class="td">{_escape(test.description)}</span></td>'
        rows += f'<td class="tt">{len([t for t in test.turns if t.role == "assistant"])}</td>'
        rows += f'<td class="tt">{test.duration_s}s</td>'

        for prov in providers:
            if last_judge and isinstance(last_judge.get(prov), dict):
                r = last_judge[prov]
                sc = r.get("overall_score", 0)
                rec = r.get("recommendation", "ERROR")
                cls = "p" if rec == "PASS" or sc >= 4.0 else "bl" if rec == "BORDERLINE" else "f"
                rows += f'<td class="sc {cls}">{sc}/5<br><span class="rc">{rec}</span></td>'
                if rec != "ERROR":
                    totals[prov]["scores"].append(sc)
                if rec == "PASS" or sc >= 4.0: totals[prov]["pass"] += 1
                elif rec == "BORDERLINE": totals[prov]["borderline"] += 1
                elif rec == "ERROR": totals[prov]["error"] += 1
                else: totals[prov]["fail"] += 1
            else:
                rows += '<td class="sc">-</td>'

        # Weaknesses column: collect unique weaknesses across all judges
        weaknesses = []
        if last_judge:
            for prov in providers:
                r = last_judge.get(prov, {})
                if isinstance(r, dict):
                    for w in r.get("weaknesses", [])[:1]:  # top 1 per judge
                        weaknesses.append(f"<strong>{prov_labels.get(prov, prov)}:</strong> {_escape(str(w)[:120])}")
        rows += f'<td class="wk">{"<br>".join(weaknesses) if weaknesses else "—"}</td></tr>'

    # Aggregate footer
    agg = '<tr class="agg"><td><strong>Average</strong></td><td></td><td></td>'
    for prov in providers:
        s = totals[prov]["scores"]
        avg = sum(s) / len(s) if s else 0
        agg += f'<td class="sc"><strong>{avg:.2f}/5</strong><br>{totals[prov]["pass"]}P / {totals[prov]["borderline"]}B / {totals[prov]["fail"]}F</td>'
    agg += '<td></td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Judge Summary — {ts}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f8fafc;color:#1e293b;padding:24px}}
h1{{font-size:24px;margin-bottom:4px}}h2{{font-size:14px;color:#94a3b8;font-weight:400;margin-bottom:24px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
th{{background:#f1f5f9;padding:12px 16px;text-align:left;font-size:13px;font-weight:600;color:#475569;border-bottom:2px solid #e2e8f0}}
td{{padding:10px 16px;border-bottom:1px solid #f1f5f9;font-size:13px;vertical-align:top}}
.tn{{min-width:200px}}.tn a{{color:#2563eb;text-decoration:none;font-weight:600}}.tn a:hover{{text-decoration:underline}}
.td{{color:#94a3b8;font-size:11px}}.tt{{text-align:center;color:#64748b}}
.sc{{text-align:center;font-weight:600}}.sc .rc{{font-size:10px;font-weight:700;padding:1px 6px;border-radius:4px}}
.p{{color:#166534;background:#f0fdf4}}.p .rc{{background:#22c55e;color:#fff}}
.bl{{color:#854d0e;background:#fffbeb}}.bl .rc{{background:#f59e0b;color:#fff}}
.f{{color:#991b1b;background:#fef2f2}}.f .rc{{background:#ef4444;color:#fff}}
.wk{{font-size:12px;color:#64748b;max-width:400px;line-height:1.4}}
.agg td{{background:#f1f5f9;font-weight:600;border-top:2px solid #e2e8f0}}
.ft{{text-align:center;padding:24px;color:#94a3b8;font-size:12px}}
</style></head><body>
<h1>🧠 Judge Summary Report</h1>
<h2>{len(tests)} tests · {ts} · Graph Reasoning Mode</h2>
<table>
<thead><tr><th>Test</th><th>Turns</th><th>Time</th>{"".join(f'<th>{prov_labels[p]}</th>' for p in providers)}<th>Top Weaknesses</th></tr></thead>
<tbody>{rows}{agg}</tbody>
</table>
<div class="ft">Auto-generated · SynapseOS Automated Test Suite</div>
</body></html>"""

    output_path.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# JSON serializer (includes internal debug data)
# ---------------------------------------------------------------------------

def serialize_test(test: TestResult) -> dict:
    turns = []
    for t in test.turns:
        entry = {
            "role": t.role, "content": t.content, "turn_number": t.turn_number,
            "timestamp": t.timestamp,
        }
        if t.role == "assistant":
            entry.update({
                "clarification": t.clarification,
                "product_card": t.product_card,
                "product_cards": t.product_cards,
                "status_badges": t.status_badges,
                "judge_results": t.judge_results,
                "inference_steps": t.inference_steps,
                # Internal debug data
                "locked_context": t.locked_context,
                "technical_state": t.technical_state,
                "graph_report": t.graph_report,
                "session_state": t.session_state,
                "content_segments": t.content_segments,
            })
        turns.append(entry)
    return {
        "name": test.name, "description": test.description,
        "query": test.query, "session_id": test.session_id,
        "duration_s": test.duration_s, "error": test.error,
        "turns": turns,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="SynapseOS Automated Conversation Test")
    parser.add_argument("--batch", type=int, default=0, help="Run N tests from test-results.json")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N tests (use with --batch)")
    parser.add_argument("--concurrency", type=int, default=5, help="Max parallel tests")
    parser.add_argument("--question", type=str, default=None, help="Single question to test")
    args = parser.parse_args()

    # Build test list
    tests: list[TestResult] = []

    if args.batch > 0:
        test_file = Path(__file__).parent.parent / "backend" / "static" / "test-results.json"
        data = json.loads(test_file.read_text())
        all_tests = data["tests"][args.offset:]
        for t in all_tests[:args.batch]:
            tests.append(TestResult(t["name"], t["description"], t["query"]))
    else:
        q = args.question or os.getenv("TEST_QUESTION", "I need a GDB housing, size 600×600, Galvanized FZ, airflow 2500 m³/h.")
        tests.append(TestResult("single_test", q[:80], q))

    print("=" * 60)
    print(f"SynapseOS Automated Test Suite — {len(tests)} tests, concurrency={args.concurrency}")
    print("=" * 60)

    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient() as client:
        token = await get_auth_token(client)
        print(f"Authenticated. Starting tests...\n")

        tasks = [run_single_test(client, token, test, semaphore) for test in tests]
        await asyncio.gather(*tasks)

    # Save results
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    reports_dir = Path(__file__).parent.parent / "reports" / f"batch-{timestamp}"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Per-test JSON + HTML
    for test in tests:
        json_path = reports_dir / f"{test.name}.json"
        json_path.write_text(json.dumps(serialize_test(test), indent=2, ensure_ascii=False), encoding="utf-8")
        html_path = reports_dir / f"{test.name}.html"
        generate_chat_html(test, html_path)

    # Summary report
    summary_path = reports_dir / "SUMMARY.html"
    generate_summary_html(tests, summary_path)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"RESULTS — {reports_dir}")
    print(f"{'=' * 60}")
    for test in tests:
        last_judge = None
        for t in reversed(test.turns):
            if t.role == "assistant" and t.judge_results:
                last_judge = t.judge_results
                break
        scores = []
        if last_judge:
            for p in ["gemini", "openai", "anthropic"]:
                r = last_judge.get(p, {})
                if isinstance(r, dict) and r.get("recommendation") != "ERROR":
                    scores.append(f"{p}:{r.get('overall_score', '?')}")
        status = "ERR" if test.error else "OK"
        print(f"  {status} {test.name:45s} {test.duration_s:6.1f}s  {', '.join(scores)}")

    print(f"\nSummary: {summary_path}")
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
