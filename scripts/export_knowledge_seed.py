#!/usr/bin/env python3
"""Export the LOCAL FalkorDB knowledge graph (Layers 1-3) as a line-per-statement
Cypher file, EXCLUDING Layer-4 session/feedback nodes.

Output:
    deploy/knowledge.cypher       one Cypher statement per line (MERGE nodes, then MERGE rels)
    deploy/run_knowledge_seed.sh  runner: reads each line, feeds to redis-cli as ONE arg

The runner passes each line as "$line" (double-quoted var expansion) so the shell
never re-parses the statement's contents -> no fragile shell escaping. Cypher string
literals are single-quoted with ' \\ and newlines escaped.

Usage:
    python scripts/export_knowledge_seed.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from falkordb import FalkorDB  # noqa: E402

HOST = os.getenv("FALKORDB_HOST", "localhost")
PORT = int(os.getenv("FALKORDB_PORT", "6379"))
PASSWORD = os.getenv("FALKORDB_PASSWORD") or None
GRAPH = os.getenv("FALKORDB_GRAPH", "synapse")

# Layer-4 (runtime session state / feedbacks) — never shipped to the server seed.
EXCLUDE = {"Session", "ActiveProject", "ConversationTurn", "TagUnit",
           "ExpertReview", "UserComment"}

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy")


def cy_str(s: str) -> str:
    """Single-quoted Cypher string literal with safe escaping (single line)."""
    s = (s.replace("\\", "\\\\")
          .replace("'", "\\'")
          .replace("\r", "\\r")
          .replace("\n", "\\n"))
    return "'" + s + "'"


def cy_val(v):
    """Format a Python value as a Cypher literal."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(cy_val(x) for x in v) + "]"
    return cy_str(str(v))


def merge_key(props: dict):
    """Pick the identity property for MERGE. Prefer id, then name, then code.

    `code` recovers Accessory nodes (e.g. ACC_POLIS) that carry no id/name.
    Nodes with none of these (runtime-captured Requirements) are intentionally
    left out — they are session artifacts, not shippable knowledge.
    """
    for k in ("id", "name", "code"):
        if k in props and props[k] is not None:
            return k, props[k]
    return None, None


def props_set(var: str, props: dict, key: str) -> str:
    """SET clause for all non-key properties."""
    items = [f"{var}.{k} = {cy_val(val)}"
             for k, val in props.items() if k != key and val is not None]
    return (" SET " + ", ".join(items)) if items else ""


def main():
    db = FalkorDB(host=HOST, port=PORT, password=PASSWORD)
    g = db.select_graph(GRAPH)

    # ---- nodes ----
    res = g.query("MATCH (n) RETURN labels(n) AS labels, properties(n) AS props")
    node_lines = []
    skipped_nodes = 0
    kept_by_label = {}
    for row in res.result_set:
        labels, props = row[0], dict(row[1])
        if any(l in EXCLUDE for l in labels):
            continue
        key, kval = merge_key(props)
        if key is None:
            skipped_nodes += 1
            continue
        label_str = ":".join(labels) if labels else "Node"
        line = f"MERGE (n:{label_str} {{{key}: {cy_val(kval)}}})" + props_set("n", props, key)
        node_lines.append(line)
        for l in labels:
            kept_by_label[l] = kept_by_label.get(l, 0) + 1

    # ---- relationships (both endpoints must be kept) ----
    res = g.query(
        "MATCH (a)-[r]->(b) RETURN labels(a) AS al, properties(a) AS ap, "
        "type(r) AS t, labels(b) AS bl, properties(b) AS bp"
    )
    rel_lines = []
    skipped_rels = 0
    for row in res.result_set:
        al, ap, t, bl, bp = row[0], dict(row[1]), row[2], row[3], dict(row[4])
        if any(l in EXCLUDE for l in al) or any(l in EXCLUDE for l in bl):
            continue
        ak, akv = merge_key(ap)
        bk, bkv = merge_key(bp)
        if ak is None or bk is None:
            skipped_rels += 1
            continue
        a_lbl = ":".join(al) if al else "Node"
        b_lbl = ":".join(bl) if bl else "Node"
        line = (f"MATCH (a:{a_lbl} {{{ak}: {cy_val(akv)}}}), "
                f"(b:{b_lbl} {{{bk}: {cy_val(bkv)}}}) "
                f"MERGE (a)-[:{t}]->(b)")
        rel_lines.append(line)

    os.makedirs(OUT_DIR, exist_ok=True)
    cypher_path = os.path.join(OUT_DIR, "knowledge.cypher")
    with open(cypher_path, "w") as f:
        f.write("\n".join(node_lines))
        f.write("\n")
        f.write("\n".join(rel_lines))
        f.write("\n")

    runner_path = os.path.join(OUT_DIR, "run_knowledge_seed.sh")
    runner = f"""#!/bin/sh
# Auto-generated. Loads knowledge.cypher into FalkorDB graph '{GRAPH}'.
# Usage: sh run_knowledge_seed.sh <password>
# Reads each statement as a SINGLE redis-cli arg ("$line") -> no shell re-parsing.
PASS="$1"
if [ -z "$PASS" ]; then echo "Usage: sh run_knowledge_seed.sh <password>"; exit 1; fi
DIR="$(dirname "$0")"
OK=0; FAIL=0; N=0
while IFS= read -r line; do
  [ -z "$line" ] && continue
  N=$((N+1))
  if redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY {GRAPH} "$line" > /dev/null 2>&1; then
    OK=$((OK+1))
  else
    FAIL=$((FAIL+1)); echo "FAIL[$N]: $line" | cut -c1-160
  fi
done < "$DIR/knowledge.cypher"
echo "Done: $OK ok, $FAIL failed, $N total"
"""
    with open(runner_path, "w") as f:
        f.write(runner)

    print(f"nodes kept:  {len(node_lines)} (skipped no-key: {skipped_nodes})")
    print(f"rels kept:   {len(rel_lines)} (skipped no-key: {skipped_rels})")
    print(f"excluded labels: {sorted(EXCLUDE)}")
    print("kept labels:")
    for l, c in sorted(kept_by_label.items(), key=lambda x: -x[1]):
        print(f"  {l}: {c}")
    print(f"\nwrote {cypher_path}")
    print(f"wrote {runner_path}")


if __name__ == "__main__":
    main()
