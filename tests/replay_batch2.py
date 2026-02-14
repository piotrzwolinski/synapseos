#!/usr/bin/env python3
"""Replay batch-2 test scenarios (5 new sessions) through the streaming API.

Each test is a multi-turn conversation via /consult/deep-explainable/stream.
Validates fixes for bugs A-M identified in the batch-2 audit.
"""
import json
import sys
import time
import uuid
import requests

BASE = "http://localhost:8000"

# ── Auth ─────────────────────────────────────────────────────────────────
def get_token():
    r = requests.post(f"{BASE}/auth/login", json={"username": "mh", "password": "MHFind@r2026"})
    r.raise_for_status()
    return r.json()["access_token"]

# ── SSE helper ───────────────────────────────────────────────────────────
def send_turn(query: str, session_id: str, token: str) -> dict:
    """Send one turn and collect ALL SSE events. Return the 'complete' payload."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"query": query, "session_id": session_id}

    r = requests.post(
        f"{BASE}/consult/deep-explainable/stream",
        json=payload,
        headers=headers,
        stream=True,
        timeout=180,
    )
    r.raise_for_status()

    complete_event = None
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:]
        try:
            evt = json.loads(data)
        except json.JSONDecodeError:
            continue
        if evt.get("type") == "complete":
            complete_event = evt
        elif evt.get("type") == "error":
            print(f"  !! ERROR: {evt.get('detail')}")
            return {"error": evt.get("detail")}

    return complete_event or {}


def extract_key_fields(evt: dict) -> dict:
    """Pull out the fields we care about for validation."""
    resp = evt.get("response", {})
    segments = resp.get("content_segments", [])
    warnings = resp.get("policy_warnings", [])
    cards = resp.get("product_cards", []) or []
    if not cards and resp.get("product_card"):
        cards = [resp["product_card"]]
    badges = resp.get("status_badges", []) or []

    ts = evt.get("technical_state", {})
    tags_dict = ts.get("tags", {})
    tags = list(tags_dict.values()) if isinstance(tags_dict, dict) else tags_dict

    # Get the full content text for keyword searches
    full_text = ""
    for s in segments:
        full_text += s.get("text", "") + " "
    full_text += json.dumps(cards)

    result = {
        "tags": tags,
        "entity_cards": cards,
        "policy_warnings": warnings,
        "badges": badges,
        "segment_count": len(segments),
        "segments_text": [s.get("text", "")[:300] for s in segments[:5]],
        "full_text": full_text,
        "full_event": evt,
    }
    return result


# ── Test definitions ─────────────────────────────────────────────────────
TESTS = [
    {
        "name": "B2-T1: Cruise ship exhaust, GDC 600x600 RF",
        "description": "Marine environment + GDC (indoor-only). Should flag environment mismatch.",
        "turns": [
            "Cruise ship exhaust. 2600 m³/h. GDC-600x600 in RF.",
            "900mm",
        ],
        "checks": {
            "detected_family": "GDC",
            "expect_risk": True,
            "corrosion_class_housing": "C2",
            "expect_no_c5m": True,  # Bug B: C5-M doesn't exist
        },
    },
    {
        "name": "B2-T2: 4x300x300 instead of 600x600, 3400 m³/h",
        "description": "Should detect quantity=4 and size=300x300. GDP detection was wrong (should be GDB).",
        "turns": [
            "We need 3400 m³/h. Instead of one 600x600 housing, we want four separate 300x300 housings.",
            "50",
        ],
        "checks": {
            # GDP-250mm-only or GDB, not GDP-550
            "expect_no_gdp_550": True,
        },
    },
    {
        "name": "B2-T3: Bag filters 600mm, GDB-550 blocked",
        "description": "GDB-550 max filter depth=450mm. Should block but suggest GDB-750 alternative.",
        "turns": [
            "We have bag filters 600 mm long. Please provide GDB-550 housing.",
        ],
        "checks": {
            "detected_family": "GDB",
            "expect_blocked": True,
            "expect_750_alternative": True,  # Bug H fix: should suggest GDB-750
        },
    },
    {
        "name": "B2-T4: Hospital rooftop kitchen, GDC FLEX 600x600 RF",
        "description": "Rooftop=outdoor, but GDC FLEX is indoor-only. Should flag environment.",
        "turns": [
            "Rooftop kitchen exhaust for a hospital. Marine climate. 3000 m³/h. We want GDC-FLEX RF 600x600.",
            "900",
        ],
        "checks": {
            "detected_family_contains": "GDC",
            "expect_risk": True,
            "expect_no_self_contradiction": True,  # Bug I fix
        },
    },
    {
        "name": "B2-T5: Ship GDMI-SF (material not available)",
        "description": "GDMI only available in AZ/ZM. SF not available. Marine=not indoor.",
        "turns": [
            "Ship installation. We require insulation and Syrafast stainless (SF). Please provide GDMI-SF.",
        ],
        "checks": {
            "detected_family": "GDMI",
            "expect_sf_blocked": True,  # Bug D: SF not available for GDMI
        },
    },
]


def run_test(test: dict, token: str):
    session_id = str(uuid.uuid4())
    print(f"\n{'='*70}")
    print(f"  {test['name']}")
    print(f"  {test['description']}")
    print(f"  Session: {session_id}")
    print(f"{'='*70}")

    last_result = None
    all_results = []
    for i, query in enumerate(test["turns"]):
        print(f"\n  ── Turn {i+1}: \"{query}\"")
        t0 = time.time()
        evt = send_turn(query, session_id, token)
        elapsed = time.time() - t0
        print(f"     ({elapsed:.1f}s)")

        if evt.get("error"):
            print(f"     FAILED: {evt['error']}")
            return {"test": test["name"], "status": "ERROR", "error": evt["error"]}

        fields = extract_key_fields(evt)
        last_result = fields
        all_results.append(fields)

        # Print tags
        for tag in fields["tags"]:
            print(f"     Tag: {tag.get('tag_id')} | fam={tag.get('product_family')} | "
                  f"size={tag.get('housing_width')}x{tag.get('housing_height')} | "
                  f"len={tag.get('housing_length')} | "
                  f"airflow={tag.get('airflow_m3h')} | "
                  f"weight={tag.get('weight_kg')} | modules={tag.get('modules_needed')} | "
                  f"code={tag.get('product_code')}")

        # Print badges
        for b in fields["badges"]:
            print(f"     Badge: {b}")

        # Print warnings
        for w in fields["policy_warnings"]:
            print(f"     Warning: {str(w)[:120]}")

        # Print first segments
        for s in fields["segments_text"][:3]:
            print(f"     Segment: {s[:180]}")

    # ── Validate ──
    checks_config = test["checks"]
    checks = []
    full_text = " ".join(r["full_text"] for r in all_results).lower()
    full_json = json.dumps([r["full_event"] for r in all_results]).lower()

    # Check detected_family
    if "detected_family" in checks_config:
        expected_fam = checks_config["detected_family"]
        ts = last_result["full_event"].get("technical_state", {})
        actual_fam = ts.get("detected_family", "")
        ok = actual_fam == expected_fam
        checks.append(("detected_family", ok, f"expected={expected_fam}, got={actual_fam}"))

    # Check detected_family_contains
    if "detected_family_contains" in checks_config:
        expected_substr = checks_config["detected_family_contains"]
        ts = last_result["full_event"].get("technical_state", {})
        actual_fam = ts.get("detected_family", "")
        ok = expected_substr in actual_fam
        checks.append(("detected_family_contains", ok, f"expected contains '{expected_substr}', got={actual_fam}"))

    # Check expect_risk
    if checks_config.get("expect_risk"):
        resp = last_result["full_event"].get("response", {})
        risk = resp.get("risk_detected", False)
        checks.append(("risk_detected", risk, f"risk_detected={risk}"))

    # Check expect_blocked
    if checks_config.get("expect_blocked"):
        badges = last_result["badges"]
        is_blocked = any("block" in str(b).lower() or "warning" in str(b).get("type", "").lower()
                         for b in badges) if badges else False
        # Also check content for block indicators
        has_block_text = "blocked" in full_text or "exceeds" in full_text or "constraint" in full_text
        ok = is_blocked or has_block_text
        checks.append(("blocked", ok, f"badges_blocked={is_blocked}, text_blocked={has_block_text}"))

    # Check GDB-750 alternative suggested (Bug H fix)
    if checks_config.get("expect_750_alternative"):
        has_750 = "750" in full_text
        checks.append(("750_alternative", has_750, f"mentions_750={has_750}"))

    # Check no C5-M (Bug B) — LLM must NOT hallucinate C5-M (anti-hallucination prompt added)
    if checks_config.get("expect_no_c5m"):
        has_c5m = "c5-m" in full_json or "c5m" in full_json
        checks.append(("no_c5m", not has_c5m, f"C5-M_hallucinated={has_c5m}"))

    # Check corrosion class of housing — LLM must cite housing corrosion class
    if "corrosion_class_housing" in checks_config:
        expected_cc = checks_config["corrosion_class_housing"]
        has_correct = expected_cc.lower() in full_text
        checks.append(("housing_corrosion", has_correct,
                       f"expected {expected_cc} in response, found={has_correct}"))

    # Check no GDP-550 (Bug G: GDP is 250mm only)
    if checks_config.get("expect_no_gdp_550"):
        has_gdp_550 = "gdp" in full_json and "550" in full_json
        # More specific: look for GDP product codes with 550
        tags = last_result["tags"]
        gdp_with_wrong_length = any(
            t.get("product_family") == "GDP" and t.get("housing_length") == 550
            for t in tags
        )
        ok = not gdp_with_wrong_length
        checks.append(("no_gdp_550", ok, f"gdp_550_tag={gdp_with_wrong_length}"))

    # Check SF blocked for GDMI
    if checks_config.get("expect_sf_blocked"):
        # SF should be mentioned as not available
        has_sf_block = ("not available" in full_text and "sf" in full_text) or \
                       ("ej" in full_text and "rostfri" in full_text) or \
                       ("stainless" in full_text and ("not" in full_text or "unavail" in full_text))
        checks.append(("sf_blocked", has_sf_block, f"sf_not_available_mentioned={has_sf_block}"))

    # Check no self-contradiction (Bug I)
    if checks_config.get("expect_no_self_contradiction"):
        # True contradiction: blocked product is also presented as a ready configuration
        # False positive: "recommend contacting..." or "proceed with alternatives" is fine
        has_block = "blocked" in full_text
        has_config_ready = ("complete" in str(last_result["badges"]).lower()
                           and has_block)
        checks.append(("no_contradiction", not has_config_ready,
                       f"block={has_block}, config_complete_badge={has_config_ready}"))

    # Print results
    print(f"\n  ── Validation ──")
    all_pass = True
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"     [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    if not checks:
        print(f"     [WARN] No checks could be performed")
        all_pass = False

    return {
        "test": test["name"],
        "status": "PASS" if all_pass else "FAIL",
        "checks": [(n, o, d) for n, o, d in checks],
        "turns_count": len(test["turns"]),
    }


def main():
    print("Authenticating...")
    token = get_token()
    print(f"Got token: {token[:20]}...")

    results = []
    for test in TESTS:
        result = run_test(test, token)
        results.append(result)

    # Summary
    print(f"\n\n{'='*70}")
    print(f"  SUMMARY — BATCH 2 REPLAY")
    print(f"{'='*70}")
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    for r in results:
        emoji = "✅" if r["status"] == "PASS" else "❌"
        print(f"  {emoji} {r['test']}: {r['status']}")
        if r.get("checks"):
            for name, ok, detail in r["checks"]:
                print(f"      {'✓' if ok else '✗'} {name}: {detail}")
    print(f"\n  {passed}/{total} passed")

    # Save results
    with open("tests/replay_batch2_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved to tests/replay_batch2_results.json")


if __name__ == "__main__":
    main()
