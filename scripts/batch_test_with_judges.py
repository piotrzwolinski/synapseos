#!/usr/bin/env python3
"""
Batch Multi-Turn Test Runner with Judge Evaluation

Runs the first 10 test cases through /consult/deep-explainable/stream,
responds to clarifications like a human, collects judge scores at each turn,
and exports full session JSONs for audit.

Usage:
    python scripts/batch_test_with_judges.py
    python scripts/batch_test_with_judges.py --count 5      # run first 5 only
    python scripts/batch_test_with_judges.py --parallel 3    # 3 concurrent sessions
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
USERNAME = os.getenv("TEST_USERNAME", "mh")
PASSWORD = os.getenv("TEST_PASSWORD", "MHFind@r2026")
TIMEOUT = int(os.getenv("TEST_TIMEOUT", "120"))
MAX_TURNS = 4  # Max conversation turns per test

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")

# ---------------------------------------------------------------------------
# Test case definitions (first 10 from active suite)
# ---------------------------------------------------------------------------
TEST_CASES = [
    {
        "id": "Q01_gdb_600x600_2500_ok",
        "description": "GDB 600x600, 2500 m³/h, FZ → OK (capacity 3400)",
        "query": "I need a GDB housing, size 600x600, Galvanized FZ, airflow 2500 m³/h.",
        "expected": "No capacity block, proceeds to clarification or card",
    },
    {
        "id": "Q02_gdb_600x600_3800_undersized",
        "description": "GDB 600x600 at 3800 m³/h → undersized (limit 3400)",
        "query": "I need a GDB housing 600x600 for 3800 m³/h airflow. FZ material.",
        "expected": "Capacity exceeded, suggest 900x600 or parallel",
    },
    {
        "id": "Q03_gdb_15000_height_constraint",
        "description": "GDB for 15000 m³/h with height ≤1500mm constraint",
        "query": "I need a GDB housing for 15000 m³/h airflow. The maximum height of the housing cannot exceed 1500mm. Standard Galvanized FZ.",
        "expected": "Multi-module sizing, 1800x900 or similar",
    },
    {
        "id": "Q04_gdb_1500x1200_16000_ok",
        "description": "GDB 1500x1200 at 16000 m³/h → OK (capacity 17000)",
        "query": "I need a GDB housing 1500x1200 for 16000 m³/h airflow. FZ material.",
        "expected": "No capacity block, proceeds",
    },
    {
        "id": "Q05_gdcflex_600x600_3000_undersized",
        "description": "GDC-FLEX 600x600 at 3000 m³/h → undersized (1750)",
        "query": "I need a GDC-FLEX carbon housing 600x600 for 3000 m³/h airflow. Indoor ventilation system.",
        "expected": "Capacity exceeded (1750), suggest 1200x600 or 2 parallel",
    },
    {
        "id": "Q06_gdcflex_900x600_2500_ok",
        "description": "GDC-FLEX 900x600 at 2500 m³/h → OK (exact match)",
        "query": "I need a GDC-FLEX carbon housing 900x600 for 2500 m³/h airflow. FZ material. Indoor ventilation.",
        "expected": "No capacity block, proceeds",
    },
    {
        "id": "Q07_gdc_600x600_2000_ok",
        "description": "GDC 600x600 at 2000 m³/h → OK (exact match)",
        "query": "I need a GDC carbon cartridge housing 600x600 for 2000 m³/h airflow. FZ material. Indoor warehouse ventilation.",
        "expected": "No capacity block, proceeds",
    },
    {
        "id": "Q08_gdc_600x600_2800_undersized",
        "description": "GDC 600x600 at 2800 m³/h → undersized (2000)",
        "query": "I need a GDC carbon housing 600x600 for 2800 m³/h airflow. Indoor warehouse ventilation.",
        "expected": "Capacity exceeded, suggest 900x600 or parallel",
    },
    {
        "id": "Q09_gdmi_600x600_3400_ok",
        "description": "GDMI 600x600 at 3400 m³/h → OK (exact match)",
        "query": "I need a GDMI insulated housing 600x600 for 3400 m³/h airflow. ZM material.",
        "expected": "No capacity block, proceeds",
    },
    {
        "id": "Q10_gdmi_600x600_4000_undersized",
        "description": "GDMI 600x600 at 4000 m³/h → undersized (3400)",
        "query": "I need a GDMI insulated housing 600x600 for 4000 m³/h airflow. ZM material.",
        "expected": "Capacity exceeded, suggest 900x600 or parallel",
    },
]


# ---------------------------------------------------------------------------
# Human-like response generator
# ---------------------------------------------------------------------------
def generate_human_response(turn_response: dict, test_case: dict) -> str | None:
    """Analyze the system's response and generate a human-like follow-up.

    Returns None if no follow-up is needed (conversation complete).
    """
    content = turn_response.get("content", "")
    clarification = turn_response.get("clarification")
    product_cards = turn_response.get("product_cards", [])
    product_card = turn_response.get("product_card")

    # If there's an explicit clarification, answer it
    if clarification and isinstance(clarification, dict):
        missing = (clarification.get("missing_info") or "").lower()
        question = (clarification.get("question") or "").lower()

        # Housing length / filter depth
        if any(kw in missing for kw in ["housing_length", "filter_depth", "length"]):
            return "750mm housing length"
        if "depth" in question or "length" in question:
            return "750mm"

        # Material
        if "material" in missing:
            return "FZ standard galvanized"

        # Airflow
        if "airflow" in missing or "m³/h" in question:
            return "3400 m³/h"

        # Temperature
        if "temperature" in missing or "temperature" in question:
            return "-5 degrees Celsius"

        # Dimensions
        if "dimension" in missing or "size" in missing:
            return "600x600mm"

        # Connection type
        if "connection" in missing:
            return "PG standard connection"

        # ATEX zone
        if "atex" in missing or "zone" in question:
            return "Zone 22"

        # Generic: answer with a reasonable default
        return "Please proceed with the default option"

    # If system asked a question in text but no formal clarification
    text_lower = content.lower()
    if "housing length" in text_lower and "?" in content:
        return "750mm housing length"
    if "filter depth" in text_lower and "?" in content:
        return "292mm filter depth"
    if "which material" in text_lower and "?" in content:
        return "FZ standard galvanized"

    # If we have product cards and no clarification, conversation is done
    if product_cards or product_card:
        return None

    # If risk/warning detected but no clarification, ask to proceed
    if turn_response.get("risk_detected") and not clarification:
        return "Understood the risks. Please proceed with the recommended configuration."

    # Default: no follow-up needed
    return None


# ---------------------------------------------------------------------------
# API interaction
# ---------------------------------------------------------------------------
def get_auth_token() -> str:
    """Get JWT token from login endpoint."""
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json().get("access_token", "")
    raise RuntimeError(f"Login failed: {resp.status_code} {resp.text}")


def send_query(query: str, session_id: str, token: str) -> dict:
    """Send a query to the streaming endpoint and parse SSE events."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"query": query, "session_id": session_id}

    resp = requests.post(
        f"{BASE_URL}/consult/deep-explainable/stream",
        json=payload,
        headers=headers,
        stream=True,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()

    events = []
    complete_data = None

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
            events.append(data)
            if data.get("type") == "complete":
                complete_data = data
        except json.JSONDecodeError:
            continue

    if not complete_data:
        return {"error": "No complete event received", "events": events}

    return complete_data.get("response", complete_data)


def run_judge(question: str, response_data: dict, token: str) -> dict:
    """Call the judge endpoint to evaluate a response."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"question": question, "response_data": response_data}

    try:
        resp = requests.post(
            f"{BASE_URL}/judge/evaluate",
            json=payload,
            headers=headers,
            timeout=120,
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"error": f"Judge returned {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------
def run_single_test(test_case: dict, token: str) -> dict:
    """Run a single test case through multi-turn conversation with judges."""
    session_id = str(uuid.uuid4())
    test_id = test_case["id"]
    turns = []

    print(f"\n{'='*60}")
    print(f"  TEST: {test_id}")
    print(f"  {test_case['description']}")
    print(f"  Session: {session_id}")
    print(f"{'='*60}")

    current_query = test_case["query"]

    for turn_num in range(1, MAX_TURNS + 1):
        print(f"\n  Turn {turn_num}: Sending query...")
        print(f"    User: {current_query[:100]}{'...' if len(current_query) > 100 else ''}")

        t_start = time.time()

        # Send query
        try:
            response = send_query(current_query, session_id, token)
        except Exception as e:
            print(f"    ERROR: {e}")
            turns.append({
                "turn": turn_num,
                "role": "user",
                "content": current_query,
            })
            turns.append({
                "turn": turn_num,
                "role": "error",
                "content": str(e),
            })
            break

        query_time = time.time() - t_start

        # Extract key info from response
        content_text = response.get("content", "") or ""
        # If content is segmented, join segments
        if not content_text and response.get("content_segments"):
            content_text = " ".join(
                s.get("text", "") for s in response.get("content_segments", [])
                if isinstance(s, dict)
            )

        clarification = response.get("clarification")
        product_cards = response.get("product_cards", [])
        risk_severity = response.get("risk_severity")
        status_badges = response.get("status_badges", [])

        print(f"    Response: {content_text[:120]}{'...' if len(content_text) > 120 else ''}")
        print(f"    Time: {query_time:.1f}s | Risk: {risk_severity} | Cards: {len(product_cards)}")
        if clarification:
            print(f"    Clarification: {clarification.get('missing_info', '?')} — {clarification.get('question', '')[:80]}")

        # Store user turn
        turns.append({
            "turn": turn_num * 2 - 1,
            "role": "user",
            "content": current_query,
        })

        # Run judges
        print(f"    Running judges...")
        t_judge = time.time()
        judge_results = run_judge(current_query, response, token)
        judge_time = time.time() - t_judge

        # Extract judge scores summary
        for provider in ["gemini", "openai", "anthropic"]:
            j = judge_results.get(provider, {})
            score = j.get("overall_score", "?")
            rec = j.get("recommendation", "?")
            print(f"      {provider}: {score} ({rec})")

        print(f"    Judge time: {judge_time:.1f}s")

        # Store assistant turn
        turns.append({
            "turn": turn_num * 2,
            "role": "assistant",
            "content": content_text,
            "clarification": clarification,
            "clarification_needed": response.get("clarification_needed", False),
            "product_cards": product_cards,
            "product_card": response.get("product_card"),
            "risk_detected": response.get("risk_detected", False),
            "risk_severity": risk_severity,
            "status_badges": status_badges,
            "reasoning_steps": response.get("reasoning_steps", []),
            "timings": {
                "query_s": round(query_time, 2),
                "judge_s": round(judge_time, 2),
            },
            "judge": judge_results,
            "raw_response_keys": list(response.keys()),
        })

        # Decide if we continue the conversation
        human_reply = generate_human_response(response, test_case)
        if human_reply is None:
            print(f"    → Conversation complete (turn {turn_num})")
            break
        else:
            print(f"    → Human follow-up: {human_reply}")
            current_query = human_reply

    return {
        "test_id": test_id,
        "description": test_case["description"],
        "initial_query": test_case["query"],
        "expected": test_case["expected"],
        "session_id": session_id,
        "total_turns": len([t for t in turns if t["role"] == "assistant"]),
        "turns": turns,
    }


def main():
    parser = argparse.ArgumentParser(description="Batch multi-turn test runner with judges")
    parser.add_argument("--count", type=int, default=10, help="Number of tests to run")
    parser.add_argument("--parallel", type=int, default=1, help="Concurrent sessions (1=sequential)")
    parser.add_argument("--start", type=int, default=0, help="Start from test index")
    args = parser.parse_args()

    tests_to_run = TEST_CASES[args.start:args.start + args.count]

    print(f"Batch Test Runner — {len(tests_to_run)} tests, parallelism={args.parallel}")
    print(f"Backend: {BASE_URL}")
    print()

    # Authenticate
    print("Authenticating...")
    token = get_auth_token()
    print(f"Token: {token[:20]}...")

    t_total_start = time.time()
    results = []

    if args.parallel <= 1:
        # Sequential execution
        for i, tc in enumerate(tests_to_run):
            print(f"\n{'#'*60}")
            print(f"  [{i+1}/{len(tests_to_run)}]")
            print(f"{'#'*60}")
            result = run_single_test(tc, token)
            results.append(result)
    else:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futures = {pool.submit(run_single_test, tc, token): tc for tc in tests_to_run}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    tc = futures[future]
                    results.append({
                        "test_id": tc["id"],
                        "error": str(e),
                    })

    total_time = time.time() - t_total_start

    # Save results
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"batch_test_{timestamp}.json")

    output = {
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "base_url": BASE_URL,
            "test_count": len(results),
            "total_duration_s": round(total_time, 1),
            "parallelism": args.parallel,
        },
        "results": results,
    }

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  BATCH COMPLETE")
    print(f"  Tests: {len(results)}")
    print(f"  Total time: {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"  Output: {output_file}")
    print(f"{'='*60}")

    # Quick summary
    print(f"\n  {'Test':<45} {'Turns':>5}  {'Gemini':>8} {'OpenAI':>8} {'Claude':>8}")
    print(f"  {'-'*45} {'-'*5}  {'-'*8} {'-'*8} {'-'*8}")
    for r in results:
        tid = r.get("test_id", "?")[:44]
        turns = r.get("total_turns", 0)
        # Get last assistant turn's judge scores
        last_judge = {}
        for t in reversed(r.get("turns", [])):
            if t.get("role") == "assistant" and t.get("judge"):
                last_judge = t["judge"]
                break
        g = last_judge.get("gemini", {}).get("overall_score", "-")
        o = last_judge.get("openai", {}).get("overall_score", "-")
        a = last_judge.get("anthropic", {}).get("overall_score", "-")
        print(f"  {tid:<45} {turns:>5}  {g:>8} {o:>8} {a:>8}")


if __name__ == "__main__":
    main()
