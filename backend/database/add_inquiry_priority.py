#!/usr/bin/env python3
"""Add inquiry_priority to VariableFeature nodes for DETERMINISTIC clarification order.

When more than one variable feature is unresolved (e.g. a GDC 600x600 query needs
both airflow_m3h AND housing_length), the synthesis LLM previously chose which one
to ask arbitrarily -> non-deterministic parameter selection across identical runs.

This seeds a deterministic inquiry order on the graph (lower = asked first). The
prompt injection and get_variable_features ORDER BY read this, so the LLM is told
to clarify the FIRST unresolved feature. Domain-owned: adjust the mapping / per-node
values here to change which parameter is asked first.

Order rationale (HVAC housings): airflow drives capacity/sizing -> ask first; then
housing length (cylinder depth); connection_type is auto-resolved so it never
competes, but gets a value for completeness. Everything else defaults to 50.

Idempotent.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import db
from db_result_helpers import result_to_dicts

# parameter_name substring -> inquiry_priority (lower asked first)
PRIORITY_RULES = [
    ("airflow", 10),
    ("przepływ", 10),
    ("length", 20),
    ("długość", 20),
    ("connection", 30),
]
DEFAULT_PRIORITY = 50


def priority_for(param_name: str, feature_name: str) -> int:
    hay = f"{param_name or ''} {feature_name or ''}".lower()
    for needle, prio in PRIORITY_RULES:
        if needle in hay:
            return prio
    return DEFAULT_PRIORITY


def apply():
    graph = db.connect()
    rows = result_to_dicts(graph.query("""
        MATCH (f:VariableFeature)
        RETURN f.id AS id, f.parameter_name AS param, f.feature_name AS name
    """))
    updated = 0
    for r in rows:
        prio = priority_for(r.get("param"), r.get("name"))
        graph.query(
            "MATCH (f:VariableFeature {id: $id}) SET f.inquiry_priority = $prio",
            params={"id": r["id"], "prio": prio},
        )
        updated += 1
        print(f"  {r['id']}: param={r.get('param')} -> inquiry_priority={prio}")
    print(f"\n[DONE] Set inquiry_priority on {updated} VariableFeature node(s).")


if __name__ == "__main__":
    apply()
