#!/usr/bin/env python3
"""Replay the 5 manual-judge test scenarios through the streaming API.

Each test is a multi-turn conversation via /consult/deep-explainable/stream.
Collects the final 'complete' event from each turn and extracts key fields
for validation.
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
        timeout=120,
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

    # Tags are in technical_state.tags (dict keyed by tag_id)
    ts = evt.get("technical_state", {})
    tags_dict = ts.get("tags", {})
    tags = list(tags_dict.values()) if isinstance(tags_dict, dict) else tags_dict

    result = {
        "tags": tags,
        "entity_cards": cards,
        "policy_warnings": warnings,
        "segment_count": len(segments),
        "segments_text": [s.get("text", "")[:200] for s in segments[:5]],
    }
    return result


# ── Test definitions ─────────────────────────────────────────────────────
TESTS = [
    {
        "name": "Test 1: GDB 1500x1200, 16000 m³/h, FZ, 550mm",
        "turns": [
            "I need a GDB housing 1500x1200 for 16000 m³/h airflow. FZ material.",
            "550mm",
        ],
        "expected": {
            "product_family": "GDB",
            "housing_size": "1500x1200",
            "catalog_weight_kg": 62,  # GDB 1500x1200, 550/600 column
            "catalog_airflow": 17000,  # Rek. flöde for 1500x1200
        },
    },
    {
        "name": "Test 2: GDB auto-sized, 15000 m³/h, max h=1500, FZ, 550mm",
        "turns": [
            "I need a GDB housing for 15000 m³/h airflow. The maximum height of the housing cannot exceed 1500mm. Standard Galvanized FZ.",
            "550mm",
        ],
        "expected": {
            "product_family": "GDB",
            "housing_size": "1800x900",  # auto-selected
            "catalog_weight_kg": 36,  # GDB 1800x900, 550/600 column
            "catalog_airflow": 15300,
        },
    },
    {
        "name": "Test 3: GDB 600x600, 3800 m³/h, FZ, 550mm",
        "turns": [
            "I need a GDB housing 600x600 for 3800 m³/h airflow. FZ material.",
            "550mm",
        ],
        "expected": {
            "product_family": "GDB",
            "housing_size": "600x600",
            "catalog_weight_kg": 27,  # GDB 600x600, 550/600 column
            "catalog_airflow": 3400,
            "needs_multi_module": True,  # 3800 > 3400
        },
    },
    {
        "name": "Test 4: GDB 600x600, 2500 m³/h, FZ, 550mm",
        "turns": [
            "I need a GDB housing, size 600x600, Galvanized FZ, airflow 2500 m³/h.",
            "550mm",
        ],
        "expected": {
            "product_family": "GDB",
            "housing_size": "600x600",
            "catalog_weight_kg": 27,
            "catalog_airflow": 3400,
        },
    },
    {
        "name": "Test 5: GDC 600x600, 2800 m³/h, indoor warehouse, 750mm",
        "turns": [
            "I need a GDC carbon housing 600x600 for 2800 m³/h airflow. Indoor warehouse ventilation.",
            "750mm",
        ],
        "expected": {
            "product_family": "GDC",
            "housing_size": "600x600",
            "catalog_weight_kg": 32,  # GDC 600x600, 750/800 column
            "catalog_airflow": 2000,
            "needs_multi_module": True,  # 2800 > 2000
            "no_humidity_stressor": True,
        },
    },
]


def run_test(test: dict, token: str):
    session_id = str(uuid.uuid4())
    print(f"\n{'='*70}")
    print(f"  {test['name']}")
    print(f"  Session: {session_id}")
    print(f"{'='*70}")

    last_result = None
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
        last_result = {"event": evt, "fields": fields}

        # Print tags
        for tag in fields["tags"]:
            print(f"     Tag: {tag.get('tag_id')} | fam={tag.get('product_family')} | "
                  f"size={tag.get('housing_width')}x{tag.get('housing_height')} | "
                  f"len={tag.get('housing_length')} | "
                  f"airflow={tag.get('airflow_m3h')} | rated={tag.get('rated_airflow_m3h')} | "
                  f"weight={tag.get('weight_kg')} | modules={tag.get('modules_needed')} | "
                  f"code={tag.get('product_code')}")

        # Print warnings
        for w in fields["policy_warnings"]:
            print(f"     Warning: {str(w)[:120]}")

        # Print first segments
        for s in fields["segments_text"][:2]:
            print(f"     Segment: {s[:150]}")

    # ── Validate ──
    exp = test["expected"]
    checks = []

    if last_result and last_result["fields"]["tags"]:
        tag = last_result["fields"]["tags"][0]

        # Weight check
        actual_weight = tag.get("weight_kg")
        if actual_weight and exp.get("catalog_weight_kg"):
            ok = actual_weight == exp["catalog_weight_kg"]
            checks.append(("weight", ok, f"expected={exp['catalog_weight_kg']}, got={actual_weight}"))

        # Rated airflow check
        actual_rated = tag.get("rated_airflow_m3h")
        if actual_rated and exp.get("catalog_airflow"):
            ok = actual_rated == exp["catalog_airflow"]
            checks.append(("rated_airflow", ok, f"expected={exp['catalog_airflow']}, got={actual_rated}"))

        # Size check
        actual_size = f"{tag.get('housing_width')}x{tag.get('housing_height')}"
        if exp.get("housing_size"):
            ok = actual_size == exp["housing_size"]
            checks.append(("size", ok, f"expected={exp['housing_size']}, got={actual_size}"))

        # Multi-module check
        if exp.get("needs_multi_module"):
            modules = tag.get("modules_needed", 1)
            ok = modules > 1
            checks.append(("multi_module", ok, f"modules_needed={modules}"))

        # No humidity check (Test 5) — humidity should not appear as a stressor
        if exp.get("no_humidity_stressor"):
            all_text = json.dumps(last_result["event"])
            has_humidity = "humidity" in all_text.lower()
            checks.append(("no_humidity", not has_humidity, f"humidity_in_response={has_humidity}"))

    # Print results
    print(f"\n  ── Validation ──")
    all_pass = True
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"     [{status}] {name}: {detail}")

    if not checks:
        print(f"     [WARN] No checks could be performed (no tags returned)")
        all_pass = False

    return {"test": test["name"], "status": "PASS" if all_pass else "FAIL", "checks": checks}


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
    print(f"  SUMMARY")
    print(f"{'='*70}")
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    for r in results:
        emoji = "✅" if r["status"] == "PASS" else "❌"
        print(f"  {emoji} {r['test']}: {r['status']}")
    print(f"\n  {passed}/{total} passed")

    # Save results
    with open("tests/replay_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved to tests/replay_results.json")


if __name__ == "__main__":
    main()
