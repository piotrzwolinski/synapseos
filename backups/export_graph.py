#!/usr/bin/env python3
"""
Export FalkorDB graph to Cypher CREATE statements for backup/restore.
Exports all nodes (with labels + properties) and all relationships.
Skips Layer 4 session state (Session, ConversationTurn, ActiveProject, TagUnit).
"""

import json
import sys
import falkordb
from datetime import datetime

SKIP_LABELS = {"Session", "ConversationTurn", "ActiveProject", "TagUnit"}

def escape_cypher_value(val):
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        inner = ", ".join(escape_cypher_value(v) for v in val)
        return f"[{inner}]"
    # string
    s = str(val).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
    return f"'{s}'"

def props_to_cypher(props: dict) -> str:
    if not props:
        return ""
    pairs = []
    for k, v in sorted(props.items()):
        pairs.append(f"{k}: {escape_cypher_value(v)}")
    return " {" + ", ".join(pairs) + "}"

def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 16379
    graph_name = sys.argv[3] if len(sys.argv) > 3 else "synapse"

    db = falkordb.FalkorDB(host=host, port=port)
    g = db.select_graph(graph_name)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = f"backups/synapse_backup_{timestamp}.cypher"

    lines = []
    lines.append(f"// SynapseOS Graph Backup — {datetime.now().isoformat()}")
    lines.append(f"// Graph: {graph_name} @ {host}:{port}")
    lines.append(f"// Excludes Layer 4 session state: {SKIP_LABELS}")
    lines.append("")

    # --- Export nodes ---
    print("Exporting nodes...")
    # Get all labels
    label_result = g.query("MATCH (n) RETURN DISTINCT labels(n)[0] AS lbl")
    all_labels = [row[0] for row in label_result.result_set]

    node_id_map = {}  # internal_id -> cypher variable name
    var_counter = 0

    for label in sorted(all_labels):
        if label in SKIP_LABELS:
            print(f"  Skipping {label} (Layer 4 session state)")
            continue

        result = g.query(f"MATCH (n:{label}) RETURN ID(n) AS id, properties(n) AS props")
        if not result.result_set:
            continue

        lines.append(f"// --- {label} ({len(result.result_set)} nodes) ---")

        for row in result.result_set:
            node_id = row[0]
            props = row[1] if row[1] else {}

            var_name = f"n{var_counter}"
            var_counter += 1
            node_id_map[node_id] = var_name

            props_str = props_to_cypher(props)
            lines.append(f"CREATE (:{label}{props_str});")

        lines.append("")
        print(f"  {label}: {len(result.result_set)} nodes")

    # --- Export relationships ---
    print("\nExporting relationships...")

    # Get all relationship types
    rel_result = g.query("MATCH ()-[r]->() RETURN DISTINCT type(r) AS t")
    all_rel_types = [row[0] for row in rel_result.result_set]

    for rel_type in sorted(all_rel_types):
        # Skip session-related relationships
        if rel_type in ("HAS_TURN", "WORKING_ON", "HAS_UNIT", "SIZED_AS", "TARGETS_FAMILY"):
            print(f"  Skipping {rel_type} (Layer 4)")
            continue

        result = g.query(f"""
            MATCH (a)-[r:{rel_type}]->(b)
            RETURN labels(a)[0] AS a_label, properties(a) AS a_props,
                   type(r) AS rel, properties(r) AS r_props,
                   labels(b)[0] AS b_label, properties(b) AS b_props
        """)

        if not result.result_set:
            continue

        # Filter out rows involving Layer 4 nodes
        filtered = [row for row in result.result_set
                    if row[0] not in SKIP_LABELS and row[4] not in SKIP_LABELS]

        if not filtered:
            print(f"  Skipping {rel_type} (all rows involve Layer 4 nodes)")
            continue

        lines.append(f"// --- {rel_type} ({len(filtered)} relationships) ---")

        for row in filtered:
            a_label, a_props, rel, r_props, b_label, b_props = row

            # Build MATCH for source node using identifying properties
            a_match = _build_match_clause(a_label, a_props or {})
            b_match = _build_match_clause(b_label, b_props or {})
            r_props_str = props_to_cypher(r_props) if r_props else ""

            lines.append(
                f"MATCH (a:{a_label}{a_match}), (b:{b_label}{b_match}) "
                f"CREATE (a)-[:{rel_type}{r_props_str}]->(b);"
            )

        lines.append("")
        print(f"  {rel_type}: {len(filtered)} relationships")

    # Write file
    with open(out_file, "w") as f:
        f.write("\n".join(lines))

    total_lines = len([l for l in lines if l.startswith("CREATE") or l.startswith("MATCH")])
    print(f"\nBackup saved to: {out_file}")
    print(f"Total statements: {total_lines}")


def _build_match_clause(label: str, props: dict) -> str:
    """Build a minimal MATCH clause using the best identifying property."""
    # Priority: id > name > code > product_code > first non-empty string prop
    for key in ("id", "name", "code", "product_code", "family_id", "stressor_id",
                "trait_id", "gate_id", "rule_id", "constraint_id", "title"):
        if key in props and props[key] is not None:
            return f" {{{key}: {escape_cypher_value(props[key])}}}"

    # Fallback: use all properties
    if props:
        return props_to_cypher(props)
    return ""


if __name__ == "__main__":
    main()
