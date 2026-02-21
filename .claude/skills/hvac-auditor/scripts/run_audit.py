#!/usr/bin/env python3
"""
HVAC Expert Auditor — Query Runner & Data Extractor

Executes a query against the Graph Reasoning streaming endpoint,
captures all SSE events, and extracts structured data for expert audit.

Usage:
    python run_audit.py "Your HVAC query here"
    python run_audit.py --file /path/to/query.txt
    python run_audit.py --test-case nanoclass_multi_tag

Output: JSON to stdout with all data needed for audit analysis.
Also saves raw events to /tmp/hvac-audit-latest.json
"""

import json
import os
import sys
import time
import uuid

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
USERNAME = os.getenv("TEST_USERNAME", "mh")
PASSWORD = os.getenv("TEST_PASSWORD", "MHFind@r2026")
TIMEOUT = int(os.getenv("TEST_TIMEOUT", "90"))

# Pre-defined complex test scenarios
SCENARIOS = {
    "nanoclass_multi_tag": (
        "I need a quote for the Nouryon project. We have two tags:\n"
        "Tag 5684: Nanoclass Deeppleat H13 - size 305x610x150 mm, SS frame, 25mm header.\n"
        "Tag 7889: Nanoclass Deeppleat E11 - size 610x610x292 mm, SS frame, 25mm header.\n"
        "Please recommend the correct GDB housings in Stainless Steel (RF) for both.\n"
        "Also, for the 305x610 model, can you confirm which dimension is vertical?\n"
        "Finally, what are the weights for the complete assemblies?"
    ),
    "kitchen_assembly_full": (
        "I'm designing a ventilation exhaust for a commercial kitchen at Stena Fastigheter. "
        "We need a GDC-FLEX carbon housing for 600x600mm duct in Stainless Steel (RF). "
        "Airflow is 2000 m³/h. The installation is indoors, wall-mounted. "
        "Please provide full product codes, weights, and any required pre-filtration."
    ),
    "hospital_chlorine_block": (
        "For the Huddinge Hospital project, I note that:\n"
        "- Environment: Hospital (sterile areas)\n"
        "- Product: GDB 600x600\n"
        "- Material: Standard Galvanized (FZ)\n"
        "- Airflow: 3400 m³/h\n"
        "Please confirm this is a suitable configuration."
    ),
    "outdoor_rooftop_pivot": (
        "I need a GDB housing for a rooftop installation on a building in Malmö. "
        "The unit is exposed to weather year-round. "
        "Size 600x600, airflow 3400 m³/h, standard Galvanized (FZ). "
        "Is GDB suitable for outdoor use?"
    ),
    "large_airflow_constrained": (
        "Industrial extraction system needs 25,000 m³/h airflow. "
        "Maximum available width is 1250mm, maximum available height is 1800mm. "
        "GDB in FZ material. Please recommend the configuration."
    ),
    "powder_coating_atex": (
        "I need an air filtration solution for a powder coating booth in our factory. "
        "The booth produces fine powder particles and organic solvents. "
        "We need to handle exhaust air from spray guns. "
        "Budget allows for GDC-FLEX 600x600 in standard material."
    ),
    "pharmaceutical_cleanroom": (
        "We are building a pharmaceutical cleanroom (GMP Class C). "
        "Need HEPA filtration capability. Environment is controlled indoor, "
        "with strict hygiene requirements. "
        "Product: GDB 600x600, material RF, airflow 3400 m³/h."
    ),
    "space_constraint_tight": (
        "We have a mechanical shaft that is exactly 650mm wide. "
        "Need to install a GDB 600x600 housing. "
        "The housing is 600mm, so it fits with 25mm on each side. "
        "Airflow is 3400 m³/h, FZ material. Is this installation feasible?"
    ),
    "multi_product_comparison": (
        "We need carbon odor filtration for a restaurant kitchen exhaust. "
        "Please compare GDC vs GDC-FLEX for 600x600 duct, "
        "considering ease of maintenance and total cost of ownership. "
        "Airflow is 2000 m³/h, material FZ."
    ),
    "assembly_with_dimensions": (
        "Kitchen extract system, 1200x600 duct, 6800 m³/h, "
        "need GDC-FLEX with grease pre-filter, "
        "RF material, max width 1300mm. "
        "What's the complete assembly configuration?"
    ),
}


def authenticate() -> str:
    """Login and return JWT token."""
    try:
        r = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception as e:
        print(json.dumps({"error": f"AUTH_FAILED: {e}"}))
        sys.exit(1)


def execute_query(query: str, session_id: str, token: str) -> list:
    """Execute streaming query and collect all SSE events."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "session_id": session_id}

    events = []
    try:
        r = requests.post(
            f"{BASE_URL}/consult/deep-explainable/stream",
            json=payload,
            headers=headers,
            stream=True,
            timeout=TIMEOUT,
        )
        r.raise_for_status()

        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                try:
                    event = json.loads(line[6:])
                    events.append(event)
                except json.JSONDecodeError:
                    pass
    except requests.exceptions.Timeout:
        events.append({"type": "error", "detail": f"Timeout after {TIMEOUT}s"})
    except Exception as e:
        events.append({"type": "error", "detail": str(e)})

    return events


def extract_audit_data(events: list) -> dict:
    """Extract structured data from SSE events for expert audit."""
    audit = {
        "query": "",
        "session_id": "",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "errors": [],
        "inference_steps": [],
        "response": {},
        "graph_report": {},
        "technical_state": {},
        "timings": {},
        # Derived audit fields
        "product_cards": [],
        "clarification": None,
        "content_text": "",
        "risk_severity": None,
        "tags_detected": 0,
        "application_detected": "",
        "material_detected": "",
        "assembly_detected": False,
    }

    for event in events:
        etype = event.get("type", event.get("step", ""))

        if etype == "error":
            audit["errors"].append(event.get("detail", "unknown"))

        elif event.get("type") == "inference":
            audit["inference_steps"].append({
                "step": event.get("step"),
                "status": event.get("status"),
                "detail": event.get("detail", ""),
            })

        elif event.get("type") == "complete" or event.get("step") == "complete":
            resp = event.get("response", {})
            if isinstance(resp, str):
                try:
                    resp = json.loads(resp)
                except json.JSONDecodeError:
                    resp = {"raw": resp}

            audit["response"] = resp
            audit["graph_report"] = event.get("graph_report", {})
            audit["technical_state"] = event.get("technical_state", {})
            audit["timings"] = event.get("timings", {})

            # Extract derived fields
            segments = resp.get("content_segments", [])
            text_parts = []
            for seg in segments:
                if isinstance(seg, dict):
                    text_parts.append(seg.get("text", ""))
                elif isinstance(seg, str):
                    text_parts.append(seg)
            audit["content_text"] = " ".join(text_parts)

            # Product cards
            cards = resp.get("product_cards", [])
            if not cards and resp.get("product_card"):
                cards = [resp["product_card"]]
            audit["product_cards"] = cards

            # Clarification
            if resp.get("clarification_needed"):
                audit["clarification"] = resp.get("clarification_data", {})

            # Risk
            audit["risk_severity"] = resp.get("risk_severity")

            # Graph report fields
            gr = audit["graph_report"]
            audit["application_detected"] = gr.get("application", "")
            audit["tags_detected"] = gr.get("tags_count", 0)

            # Assembly detection
            ts = audit["technical_state"]
            if isinstance(ts, dict):
                tags = ts.get("tags", {})
                if isinstance(tags, dict):
                    audit["assembly_detected"] = any(
                        "stage" in str(k) for k in tags.keys()
                    )

    return audit


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage: python run_audit.py <query|--test-case NAME|--list>")
        print(f"\nAvailable scenarios: {', '.join(SCENARIOS.keys())}")
        sys.exit(1)

    # Handle --list
    if args[0] == "--list":
        print("\nAvailable audit scenarios:")
        for name, query in SCENARIOS.items():
            first_line = query.split("\n")[0][:80]
            print(f"  {name:<30} {first_line}...")
        sys.exit(0)

    # Handle --test-case
    if args[0] == "--test-case" and len(args) > 1:
        scenario = args[1]
        matches = [k for k in SCENARIOS if scenario.lower() in k.lower()]
        if not matches:
            print(f"Unknown scenario '{scenario}'. Available: {', '.join(SCENARIOS.keys())}")
            sys.exit(1)
        query = SCENARIOS[matches[0]]
        scenario_name = matches[0]
    elif args[0] == "--file" and len(args) > 1:
        with open(args[1]) as f:
            query = f.read().strip()
        scenario_name = "custom_file"
    else:
        query = " ".join(args)
        scenario_name = "custom_query"

    session_id = f"audit-{scenario_name}-{uuid.uuid4().hex[:8]}"

    # Authenticate
    print(f"Authenticating...", file=sys.stderr)
    token = authenticate()

    # Clear session
    try:
        requests.delete(
            f"{BASE_URL}/session/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except Exception:
        pass

    # Execute
    print(f"Executing query ({len(query)} chars)...", file=sys.stderr)
    start = time.time()
    events = execute_query(query, session_id, token)
    duration = time.time() - start
    print(f"Done in {duration:.1f}s ({len(events)} events)", file=sys.stderr)

    # Extract
    audit = extract_audit_data(events)
    audit["query"] = query
    audit["session_id"] = session_id
    audit["scenario"] = scenario_name
    audit["duration_s"] = round(duration, 1)

    # Save raw events
    raw_file = "/tmp/hvac-audit-latest.json"
    with open(raw_file, "w") as f:
        json.dump(events, f, indent=2, default=str)
    print(f"Raw events saved to {raw_file}", file=sys.stderr)

    # Save audit data
    audit_file = "/tmp/hvac-audit-data.json"
    with open(audit_file, "w") as f:
        json.dump(audit, f, indent=2, default=str)
    print(f"Audit data saved to {audit_file}", file=sys.stderr)

    # Output summary to stdout (for Claude to read)
    summary = {
        "scenario": audit["scenario"],
        "duration_s": audit["duration_s"],
        "errors": audit["errors"],
        "application_detected": audit["application_detected"],
        "tags_detected": audit["tags_detected"],
        "risk_severity": audit["risk_severity"],
        "assembly_detected": audit["assembly_detected"],
        "product_cards_count": len(audit["product_cards"]),
        "has_clarification": audit["clarification"] is not None,
        "clarification_param": (
            audit["clarification"].get("missing_attribute", "")
            if audit["clarification"]
            else ""
        ),
        "inference_steps_count": len(audit["inference_steps"]),
        "content_text_length": len(audit["content_text"]),
        "files": {
            "raw_events": raw_file,
            "audit_data": audit_file,
        },
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
