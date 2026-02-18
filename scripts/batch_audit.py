#!/usr/bin/env python3
"""
Batch Audit CLI — multi-turn test conversations + multi-LLM judges.

The system asks clarification questions (e.g. "What airflow?") and an LLM
plays the user role to answer them. The full conversation is recorded and
judged by up to 3 LLMs (Gemini 3 Pro, GPT-5.2, Claude Opus 4.6).

Usage:
    python scripts/batch_audit.py                         # 10 tests, gemini judge
    python scripts/batch_audit.py --all                   # All tests
    python scripts/batch_audit.py --limit 20              # First 20
    python scripts/batch_audit.py --category sizing       # Filter
    python scripts/batch_audit.py --max-turns 5           # Conversation depth
    python scripts/batch_audit.py --parallel 3            # Concurrent tests
    python scripts/batch_audit.py --judges gemini,openai,anthropic
    python scripts/batch_audit.py --failures-only         # Reprint last run
"""

import argparse
import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

TEST_RUNNER_DIR = (
    Path(__file__).resolve().parent.parent / ".claude" / "skills" / "test-hvac" / "scripts"
)
sys.path.insert(0, str(TEST_RUNNER_DIR))

RESULTS_FILE = BACKEND_DIR / "static" / "judge-results.json"
FAILURES_FILE = BACKEND_DIR / "static" / "audit-failures.json"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

DEFAULT_LIMIT = 10
DEFAULT_MAX_TURNS = 6
SIMULATED_USER_MODEL = "gemini-2.0-flash"

# ANSI
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; B = "\033[1m"; D = "\033[2m"; C = "\033[96m"; X = "\033[0m"


# ---------------------------------------------------------------------------
# Simulated user — Gemini Flash answers clarifications
# ---------------------------------------------------------------------------

_SIM_USER_PROMPT = """You simulate a technical sales engineer asking about HVAC filter products.

ORIGINAL QUESTION: {original_query}

The system asked a clarification:
QUESTION: {question}
WHY: {why}
{options}

Reply with JUST the answer (e.g. "3400 m3/h", "550mm", "Galvanized steel").
- If options given, pick the most typical/common one
- Under 15 words, no explanation, no pleasantries
- If the original query already answers this, repeat that info"""


def _simulate_user_answer(original_query: str, clarification: dict) -> str:
    """Use Gemini Flash to generate a realistic user answer to a system clarification."""
    from google import genai
    from google.genai import types
    from api_keys import api_keys_manager

    options = clarification.get("options", [])

    api_key = api_keys_manager.get_key("gemini")
    if not api_key:
        return options[0].get("value", "standard") if options else "standard"

    if options:
        opts_text = "OPTIONS:\n" + "\n".join(
            f"  - {o.get('display_label', o.get('value', ''))}: {o.get('description', '')}"
            for o in options
        )
    else:
        opts_text = "(no predefined options)"

    prompt = _SIM_USER_PROMPT.format(
        original_query=original_query,
        question=clarification.get("question", ""),
        why=clarification.get("why_needed", ""),
        options=opts_text,
    )

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=SIMULATED_USER_MODEL,
            contents=[types.Content(parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(max_output_tokens=64, temperature=0.1),
        )
        return resp.text.strip().strip('"').strip("'")
    except Exception as e:
        print(f"      {D}[sim-user] LLM failed ({e}), using first option{X}")
        return options[0].get("value", "standard") if options else "standard"


# ---------------------------------------------------------------------------
# Multi-turn conversation runner
# ---------------------------------------------------------------------------

def _run_conversation(name: str, tc, max_turns: int) -> dict:
    """Run query → response → [clarification → simulated answer]* → product/end."""
    from judge import _call_system

    session_id = f"audit-{name}-{uuid.uuid4().hex[:8]}"
    t0 = time.time()

    turns = []
    current_query = tc.query
    follow_ups = list(getattr(tc, "follow_ups", []) or [])
    final_product_cards = []
    reached_product = False
    status = "ok"
    error = ""

    for turn_num in range(1, max_turns + 1):
        # User turn
        turns.append({"role": "user", "content": current_query, "turn": turn_num})

        # System turn
        t_sys = time.time()
        try:
            resp = _call_system(current_query, session_id=session_id)
        except Exception as e:
            status = "error"
            error = str(e)
            break

        sys_turn = {
            "role": "system",
            "content": resp.get("content_text", ""),
            "turn": turn_num,
            "clarification": resp.get("clarification"),
            "clarification_needed": resp.get("clarification_needed", False),
            "product_card": resp.get("product_card"),
            "product_cards": resp.get("product_cards", []),
            "risk_detected": resp.get("risk_detected", False),
            "graph_report": resp.get("graph_report", {}),
            "technical_state": resp.get("technical_state", {}),
            "duration_s": round(time.time() - t_sys, 1),
        }
        turns.append(sys_turn)

        # Check: got product?
        pcards = resp.get("product_cards", [])
        pcard = resp.get("product_card")
        if pcard and not pcards:
            pcards = [pcard]
        if pcards:
            reached_product = True
            final_product_cards = pcards
            break

        # Check: clarification → answer it
        clar = resp.get("clarification")
        if resp.get("clarification_needed") and clar and turn_num < max_turns:
            if follow_ups:
                nq = follow_ups.pop(0)
                current_query = nq.query if hasattr(nq, "query") else str(nq)
            else:
                current_query = _simulate_user_answer(tc.query, clar)
            cq = clar.get("question", "?")
            print(f"      {D}↳ \"{cq[:55]}\" → \"{current_query}\"{X}")
            continue

        # No clarification, no product → text-only end (warning/block)
        break

    total_turns = (len(turns) + 1) // 2  # user+system pairs
    return {
        "test_name": name,
        "initial_query": tc.query,
        "description": tc.description,
        "category": tc.category,
        "pdf_reference": getattr(tc, "pdf_reference", ""),
        "session_id": session_id,
        "turns": turns,
        "total_turns": total_turns,
        "reached_product": reached_product,
        "reached_max_turns": total_turns >= max_turns and not reached_product,
        "final_product_cards": final_product_cards,
        "duration_system_s": round(time.time() - t0, 1),
        "status": status,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Build judge payload from conversation
# ---------------------------------------------------------------------------

def _judge_payload(conv: dict) -> dict:
    """Build the response_data dict judges expect (with conversation_history)."""
    history = []
    for t in conv["turns"]:
        entry = {"role": t["role"], "content": t["content"]}
        if t["role"] == "system":
            if t.get("product_card"):
                entry["product_card"] = t["product_card"]
            if t.get("product_cards"):
                entry["product_cards"] = t["product_cards"]
            badges = []
            if t.get("risk_detected"):
                badges.append({"type": "WARNING", "text": "Risk detected"})
            if t.get("clarification"):
                badges.append({"type": "CLARIFICATION", "text": t["clarification"].get("question", "")})
            if badges:
                entry["status_badges"] = badges
        history.append(entry)

    cards = conv.get("final_product_cards", [])
    return {
        "conversation_history": history,
        "product_cards": cards,
        "product_card": cards[0] if cards else None,
    }


# ---------------------------------------------------------------------------
# Judge a conversation with selected LLMs
# ---------------------------------------------------------------------------

JUDGE_FNS = {}  # lazy-loaded

def _get_judge_fns():
    global JUDGE_FNS
    if not JUDGE_FNS:
        from judge import _judge_with_gemini, _judge_with_openai, _judge_with_claude
        JUDGE_FNS = {
            "gemini": _judge_with_gemini,
            "openai": _judge_with_openai,
            "anthropic": _judge_with_claude,
        }
    return JUDGE_FNS


def _judge_conversation(conv: dict, judge_names: list) -> dict:
    """Run selected judges in parallel. Returns {name: JudgeResult dict}."""
    fns = _get_judge_fns()
    payload = _judge_payload(conv)
    query = conv["initial_query"]
    results = {}

    with ThreadPoolExecutor(max_workers=len(judge_names)) as pool:
        futures = {}
        for jn in judge_names:
            fn = fns.get(jn)
            if not fn:
                continue
            futures[pool.submit(fn, query, payload)] = jn

        for fut in as_completed(futures):
            jn = futures[fut]
            try:
                jr = fut.result()
                results[jn] = asdict(jr)
            except Exception as e:
                results[jn] = {"overall_score": 0, "recommendation": "ERROR", "explanation": str(e)}

    return results


# ---------------------------------------------------------------------------
# Run one test end-to-end
# ---------------------------------------------------------------------------

def _run_one(name: str, tc, index: int, total: int, max_turns: int, judge_names: list) -> dict:
    t0 = time.time()

    # Phase 1: multi-turn conversation
    conv = _run_conversation(name, tc, max_turns)

    if conv["status"] == "error":
        print(f"  [{index}/{total}] {name} {'.' * max(1, 42 - len(name))} {R}ERROR{X}  {conv['error'][:80]}")
        conv["judges"] = {}
        conv["duration_total_s"] = round(time.time() - t0, 1)
        return conv

    # Phase 2: judge
    conv["judges"] = _judge_conversation(conv, judge_names)
    conv["duration_total_s"] = round(time.time() - t0, 1)

    # Display
    primary = conv["judges"].get("gemini") or conv["judges"].get("openai") or conv["judges"].get("anthropic") or {}
    score = primary.get("overall_score", 0)
    rec = primary.get("recommendation", "?")
    color = G if rec == "PASS" else (Y if rec == "BORDERLINE" else R)
    dots = "." * max(1, 38 - len(name))
    tt = conv["total_turns"]
    prod = "P" if conv["reached_product"] else ("-" if not conv["reached_max_turns"] else "X")

    jscores = " ".join(
        f"{jn[0].upper()}:{conv['judges'][jn].get('overall_score', 0):.1f}"
        for jn in judge_names if jn in conv["judges"]
    )

    print(
        f"  [{index}/{total}] {name} {dots} "
        f"{color}{score:.1f} {rec}{X}  "
        f"{D}[{tt}t {prod}] [{jscores}] {conv['duration_total_s']}s{X}"
    )
    return conv


# ---------------------------------------------------------------------------
# Failure classification & display
# ---------------------------------------------------------------------------

def _primary(r: dict) -> dict:
    j = r.get("judges", {})
    return j.get("gemini") or j.get("openai") or j.get("anthropic") or {}


def _classify(r: dict) -> str:
    if r.get("status") == "error":
        return "system_error"
    if r.get("reached_max_turns") and not r.get("reached_product"):
        return "clarification_loop"
    judge = _primary(r)
    explanation = judge.get("explanation", "").lower()
    scores = judge.get("scores", {})
    if scores.get("correctness", 5) <= 2:
        if "hallucin" in explanation:
            return "llm_hallucination"
        if "graph" in explanation or "missing" in explanation:
            return "graph_data"
        return "engine_logic"
    if scores.get("constraint_adherence", 5) <= 2:
        return "constraint_violation"
    if scores.get("safety", 5) <= 2:
        return "safety_miss"
    return "unknown"


def _print_failures(failures: list):
    if not failures:
        print(f"\n  {G}No failures!{X}")
        return

    print(f"\n{R}  FAILURES ({len(failures)}):{X}")
    print("  " + "─" * 78)

    for i, f in enumerate(failures, 1):
        judge = _primary(f)
        scores = judge.get("scores", {})
        score_str = " ".join(f"{k[:3].upper()}:{v}" for k, v in scores.items()) if scores else "n/a"

        explanation = judge.get("explanation", "")
        sentences = explanation.split(". ")
        short = ". ".join(sentences[:2]) + ("." if len(sentences) > 2 else "")

        rec = judge.get("recommendation", "?")
        overall = judge.get("overall_score", 0)
        cause = f.get("likely_cause", "unknown")
        tt = f.get("total_turns", 0)
        end = "product" if f.get("reached_product") else ("max_turns" if f.get("reached_max_turns") else "text")

        print(f"\n  {i}. {B}{f['test_name']}{X} [{f.get('category', '?')}] — {overall:.1f} {rec}")
        print(f"     Query: {f.get('initial_query', f.get('query', ''))[:100]}")
        print(f"     Turns: {tt} → {end}")
        print(f"     Scores: {score_str}")
        print(f"     → {short[:200]}")

        # Show clarification turns
        for t in f.get("turns", []):
            if t.get("role") == "system" and t.get("clarification_needed"):
                clar = t.get("clarification", {})
                print(f"     {D}Clar: \"{clar.get('question', '')}\" why: \"{clar.get('why_needed', '')}\"{X}")

        # Show secondary judge verdicts
        for jn, jd in f.get("judges", {}).items():
            if jd is not judge:
                print(f"     [{jn}] {jd.get('overall_score', 0):.1f} {jd.get('recommendation', '?')}")

        print(f"     Likely cause: {B}{cause}{X}")


# ---------------------------------------------------------------------------
# Load tests
# ---------------------------------------------------------------------------

def _load_tests(category: str = None, limit: int = DEFAULT_LIMIT, names: list = None):
    from run_tests import TEST_CASES
    cases = dict(TEST_CASES)
    if names:
        cases = {k: v for k, v in cases.items() if k in names}
    elif category and category != "all":
        cases = {k: v for k, v in cases.items() if v.category == category}
    if limit > 0 and not names:
        cases = dict(list(cases.items())[:limit])
    return cases


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_batch(
    category: str = None,
    limit: int = DEFAULT_LIMIT,
    max_turns: int = DEFAULT_MAX_TURNS,
    parallel: int = 1,
    judge_names: list = None,
    names: list = None,
):
    if judge_names is None:
        judge_names = ["gemini"]

    cases = _load_tests(category, limit, names=names)
    total = len(cases)
    if total == 0:
        print("No tests found.")
        return

    cat_label = f" [{category}]" if category else ""
    jlabel = "+".join(judge_names)
    print(f"\n  {'═' * 78}")
    print(f"  BATCH AUDIT — {total} tests{cat_label} | max {max_turns} turns | judges: {jlabel} | parallel: {parallel}")
    print(f"  {'═' * 78}\n")

    t0 = time.time()
    results = []

    if parallel <= 1:
        for i, (name, tc) in enumerate(cases.items(), 1):
            results.append(_run_one(name, tc, i, total, max_turns, judge_names))
    else:
        items = list(cases.items())
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = {
                pool.submit(_run_one, name, tc, i, total, max_turns, judge_names): name
                for i, (name, tc) in enumerate(items, 1)
            }
            for fut in as_completed(futures):
                results.append(fut.result())

    duration = round(time.time() - t0, 1)

    # --- Aggregation ---
    pass_n = sum(1 for r in results if _primary(r).get("recommendation") == "PASS")
    fail_n = sum(1 for r in results if _primary(r).get("recommendation") == "FAIL")
    border_n = sum(1 for r in results if _primary(r).get("recommendation") == "BORDERLINE")
    err_n = sum(1 for r in results if r.get("status") == "error")

    scores = [_primary(r).get("overall_score", 0) for r in results if _primary(r).get("overall_score", 0) > 0]
    avg = round(sum(scores) / len(scores), 2) if scores else 0.0

    total_turns = sum(r.get("total_turns", 0) for r in results)
    avg_turns = round(total_turns / len(results), 1) if results else 0
    product_n = sum(1 for r in results if r.get("reached_product"))
    maxed_n = sum(1 for r in results if r.get("reached_max_turns"))

    per_judge = {}
    for jn in judge_names:
        js = [r.get("judges", {}).get(jn, {}).get("overall_score", 0) for r in results
              if r.get("judges", {}).get(jn, {}).get("overall_score", 0) > 0]
        per_judge[jn] = {"avg": round(sum(js) / len(js), 2) if js else 0, "n": len(js)}

    # --- Summary ---
    print(f"\n  {'═' * 78}")
    print(f"  {total} tests | {G}{pass_n} PASS{X} | {Y}{border_n} BORDER{X} | {R}{fail_n} FAIL{X} | {err_n} ERR | {duration}s")
    print(f"  Avg score: {avg} | Avg turns: {avg_turns} | Products: {product_n}/{total} | Max-turns hit: {maxed_n}")
    for jn, js in per_judge.items():
        print(f"  [{jn}] avg={js['avg']} ({js['n']} scored)")
    print(f"  {'═' * 78}")

    # --- Failures ---
    failures = []
    for r in results:
        rec = _primary(r).get("recommendation", "")
        if rec in ("FAIL", "BORDERLINE", "ERROR") or r.get("status") == "error":
            r["likely_cause"] = _classify(r)
            failures.append(r)
    failures.sort(key=lambda x: _primary(x).get("overall_score", 0))
    _print_failures(failures)

    # --- Save ---
    cat_scores = {}
    for r in results:
        cat = r.get("category", "other")
        sc = _primary(r).get("overall_score", 0)
        if sc > 0:
            cat_scores.setdefault(cat, []).append(sc)

    output = {
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "batch_audit_multiturn",
            "total_questions": total,
            "passed": pass_n, "failed": fail_n, "borderline": border_n, "errors": err_n,
            "avg_overall_score": avg,
            "avg_turns": avg_turns,
            "products_reached": product_n, "max_turns_reached": maxed_n,
            "duration_s": duration,
            "max_turns_setting": max_turns,
            "judges": judge_names,
            "per_judge": per_judge,
            "category_summary": {c: round(sum(v) / len(v), 2) for c, v in cat_scores.items()},
            "filter": category or "all",
            "limit": limit,
        },
        "results": sorted(results, key=lambda r: _primary(r).get("overall_score", 0)),
    }

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results: {RESULTS_FILE}")

    FAILURES_FILE.write_text(json.dumps({
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat(),
                 "total": total, "passed": pass_n, "failed": fail_n,
                 "borderline": border_n, "avg_score": avg},
        "failures": failures,
    }, indent=2, default=str))
    if failures:
        print(f"  Failures: {FAILURES_FILE}")

    # Markdown report
    md_path = _write_markdown_report(results, output["meta"], failures, judge_names)
    print(f"  Report:   {md_path}")
    print()


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _write_markdown_report(results: list, meta: dict, failures: list, judge_names: list) -> Path:
    """Generate a markdown report with full conversation transcripts."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"audit_{ts}.md"

    lines = []
    w = lines.append

    w(f"# Batch Audit Report")
    w(f"**{meta['timestamp']}** | {meta['total_questions']} tests | "
      f"{meta['passed']} PASS | {meta['borderline']} BORDER | {meta['failed']} FAIL | {meta['errors']} ERR")
    w(f"")
    w(f"| Metric | Value |")
    w(f"|--------|-------|")
    w(f"| Avg score | {meta['avg_overall_score']} |")
    w(f"| Avg turns | {meta['avg_turns']} |")
    w(f"| Products reached | {meta['products_reached']}/{meta['total_questions']} |")
    w(f"| Max-turns hit | {meta['max_turns_reached']} |")
    w(f"| Duration | {meta['duration_s']}s |")
    w(f"| Judges | {', '.join(judge_names)} |")
    w("")

    # Per-judge summary
    pj = meta.get("per_judge", {})
    if len(pj) > 1:
        w("## Judge Comparison")
        w("| Judge | Avg Score | Scored |")
        w("|-------|-----------|--------|")
        for jn, js in pj.items():
            w(f"| {jn} | {js['avg']} | {js['n']} |")
        w("")

    # Category summary
    cs = meta.get("category_summary", {})
    if cs:
        w("## Category Breakdown")
        w("| Category | Avg Score |")
        w("|----------|-----------|")
        for cat, sc in sorted(cs.items()):
            w(f"| {cat} | {sc} |")
        w("")

    # Sort results by score ascending (worst first)
    sorted_results = sorted(results, key=lambda r: _primary(r).get("overall_score", 0))

    # Results table
    w("## Results")
    w("")
    jcols = " | ".join(f"{jn}" for jn in judge_names)
    w(f"| # | Test | Cat | Turns | Product | {jcols} | Verdict |")
    w(f"|---|------|-----|-------|---------|" + "|".join("------" for _ in judge_names) + "|---------|")
    for i, r in enumerate(sorted_results, 1):
        name = r.get("test_name", "?")
        cat = r.get("category", "?")
        tt = r.get("total_turns", 0)
        prod = "yes" if r.get("reached_product") else "no"
        pj_scores = []
        for jn in judge_names:
            jd = r.get("judges", {}).get(jn, {})
            sc = jd.get("overall_score", 0)
            rec = jd.get("recommendation", "?")
            pj_scores.append(f"{sc:.1f} {rec}")
        prim = _primary(r)
        verdict = prim.get("recommendation", "?")
        emoji = {"PASS": "PASS", "BORDERLINE": "BORDER", "FAIL": "FAIL", "ERROR": "ERR"}.get(verdict, verdict)
        w(f"| {i} | {name} | {cat} | {tt} | {prod} | " + " | ".join(pj_scores) + f" | **{emoji}** |")
    w("")

    # Detailed conversations
    w("## Conversations")
    w("")
    for r in sorted_results:
        name = r.get("test_name", "?")
        prim = _primary(r)
        score = prim.get("overall_score", 0)
        rec = prim.get("recommendation", "?")

        w(f"### {name} — {score:.1f} {rec}")
        w(f"")
        w(f"**Query:** {r.get('initial_query', r.get('query', ''))}")
        w(f"**Category:** {r.get('category', '?')} | **Turns:** {r.get('total_turns', 0)} | "
          f"**Product:** {'yes' if r.get('reached_product') else 'no'} | "
          f"**Duration:** {r.get('duration_total_s', 0)}s")
        w("")

        # Conversation transcript
        for t in r.get("turns", []):
            role = t["role"].upper()
            content = t.get("content", "")
            w(f"**{role}** (turn {t.get('turn', '?')}):")
            # Indent content as blockquote
            for line in content.split("\n"):
                w(f"> {line}")

            if t.get("clarification_needed") and t.get("clarification"):
                clar = t["clarification"]
                w(f">")
                w(f"> *Clarification: {clar.get('question', '')}*")
                w(f"> *Why: {clar.get('why_needed', '')}*")
                opts = clar.get("options", [])
                if opts:
                    w(f"> Options: {', '.join(str(o.get('display_label') or o.get('value') or '?') for o in opts)}")

            if t.get("product_cards"):
                for pc in t["product_cards"]:
                    code = pc.get("product_code", pc.get("code", "?"))
                    w(f">")
                    w(f"> **Product Card: `{code}`**")
                    # Show key fields
                    for k in ("weight_kg", "housing_length_mm", "airflow_m3h", "material", "dimensions"):
                        if k in pc:
                            w(f"> - {k}: {pc[k]}")
            w("")

        # Judge evaluations
        w("**Judge Evaluations:**")
        w("")
        for jn in judge_names:
            jd = r.get("judges", {}).get(jn, {})
            if not jd:
                continue
            sc = jd.get("overall_score", 0)
            rec = jd.get("recommendation", "?")
            w(f"**{jn}** — {sc:.1f} {rec}")

            scores = jd.get("scores", {})
            if scores:
                w(f"| Dimension | Score |")
                w(f"|-----------|-------|")
                for dim, val in scores.items():
                    w(f"| {dim} | {val} |")
                w("")

            expl = jd.get("explanation", "")
            if expl:
                w(f"*{expl}*")
                w("")

            strengths = jd.get("strengths", [])
            if strengths:
                w("Strengths: " + "; ".join(strengths))

            weaknesses = jd.get("weaknesses", [])
            if weaknesses:
                w("Weaknesses: " + "; ".join(weaknesses))
            w("")

        w("---")
        w("")

    # Failure summary at the end
    if failures:
        w("## Failure Analysis")
        w("")
        for i, f in enumerate(failures, 1):
            name = f.get("test_name", "?")
            cause = f.get("likely_cause", "unknown")
            prim_f = _primary(f)
            sc = prim_f.get("overall_score", 0)
            rec = prim_f.get("recommendation", "?")
            w(f"{i}. **{name}** — {sc:.1f} {rec} — likely cause: `{cause}`")
        w("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Show last failures
# ---------------------------------------------------------------------------

def _show_last_failures():
    if not FAILURES_FILE.exists():
        print("No previous audit results found.")
        return
    data = json.loads(FAILURES_FILE.read_text())
    meta = data.get("meta", {})
    failures = data.get("failures", [])
    print(f"\n  Last audit: {meta.get('timestamp', '?')}")
    print(f"  {meta.get('total', 0)} tests | {meta.get('passed', 0)} PASS | "
          f"{meta.get('borderline', 0)} BORDER | {meta.get('failed', 0)} FAIL")
    _print_failures(failures)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Batch audit: multi-turn conversations + LLM judges")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"Max tests (default {DEFAULT_LIMIT}, 0=unlimited)")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--category", type=str, default=None,
                        help="Filter by category")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS,
                        help=f"Max conversation turns (default {DEFAULT_MAX_TURNS})")
    parser.add_argument("--parallel", type=int, default=1,
                        help="Concurrent test runs (default 1)")
    parser.add_argument("--judges", type=str, default="gemini",
                        help="Comma-separated judges: gemini,openai,anthropic (default gemini)")
    parser.add_argument("--failures-only", action="store_true",
                        help="Reprint failures from last run")
    parser.add_argument("--names", type=str, default=None,
                        help="Comma-separated test names to run (exact match)")
    args = parser.parse_args()

    if args.failures_only:
        _show_last_failures()
        return

    names = [n.strip() for n in args.names.split(",") if n.strip()] if args.names else None

    run_batch(
        category=args.category,
        limit=0 if args.all else args.limit,
        max_turns=args.max_turns,
        parallel=args.parallel,
        judge_names=[j.strip() for j in args.judges.split(",") if j.strip()],
        names=names,
    )


if __name__ == "__main__":
    main()
