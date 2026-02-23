#!/usr/bin/env python3
"""Export FalkorDB graph data as Cypher CREATE statements.

Connects to the source FalkorDB instance (via env vars) and exports
all nodes and relationships as Cypher statements that can be replayed
on a fresh instance.

Usage:
    python scripts/export_graph.py > graph_dump.cypher
    python scripts/export_graph.py --output graph_dump.cypher

Environment variables (reads from .env):
    FALKORDB_HOST, FALKORDB_PORT, FALKORDB_USERNAME, FALKORDB_PASSWORD, FALKORDB_GRAPH
"""

import argparse
import json
import os
import sys

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

from falkordb import FalkorDB


def connect():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", 6379))
    username = os.getenv("FALKORDB_USERNAME")
    password = os.getenv("FALKORDB_PASSWORD")
    graph_name = os.getenv("FALKORDB_GRAPH", "synapse")

    kwargs = {"host": host, "port": port, "socket_timeout": 30}
    if username:
        kwargs["username"] = username
    if password:
        kwargs["password"] = password

    db = FalkorDB(**kwargs)
    graph = db.select_graph(graph_name)
    print(f"// Connected to {host}:{port} graph={graph_name}", file=sys.stderr)
    return graph


def escape_cypher_string(val):
    """Escape a string for Cypher."""
    if val is None:
        return "null"
    s = str(val)
    s = s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
    return f"'{s}'"


def format_value(val):
    """Format a Python value as a Cypher literal."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        items = ", ".join(format_value(v) for v in val)
        return f"[{items}]"
    return escape_cypher_string(val)


def format_props(props: dict) -> str:
    """Format a dict as Cypher property map."""
    if not props:
        return ""
    parts = []
    for k, v in props.items():
        if v is not None:
            parts.append(f"{k}: {format_value(v)}")
    return "{" + ", ".join(parts) + "}"


def export_nodes(graph, out):
    """Export all nodes as CREATE statements."""
    result = graph.query("MATCH (n) RETURN n, labels(n) AS labels, ID(n) AS id")
    count = 0
    for row in result.result_set:
        node = row[0]
        labels = row[1]
        node_id = row[2]

        # Get properties
        props = {}
        if hasattr(node, 'properties'):
            props = dict(node.properties)

        label_str = ":".join(labels) if labels else "Node"
        prop_str = format_props(props)

        # Use MERGE on id/name for idempotency
        id_key = None
        id_val = None
        for key in ("id", "name", "session_id"):
            if key in props:
                id_key = key
                id_val = props[key]
                break

        if id_key:
            merge_prop = format_props({id_key: id_val})
            set_props = {k: v for k, v in props.items() if k != id_key}
            line = f"MERGE (n:{label_str} {merge_prop})"
            if set_props:
                set_parts = ", ".join(f"n.{k} = {format_value(v)}" for k, v in set_props.items())
                line += f" SET {set_parts}"
        else:
            line = f"CREATE (:{label_str} {prop_str})"

        out.write(line + ";\n")
        count += 1

    print(f"// Exported {count} nodes", file=sys.stderr)
    return count


def export_relationships(graph, out):
    """Export all relationships as MATCH + CREATE statements."""
    result = graph.query("""
        MATCH (a)-[r]->(b)
        RETURN labels(a) AS a_labels, properties(a) AS a_props,
               type(r) AS rel_type, properties(r) AS r_props,
               labels(b) AS b_labels, properties(b) AS b_props
    """)
    count = 0
    for row in result.result_set:
        a_labels = row[0]
        a_props = row[1] if row[1] else {}
        rel_type = row[2]
        r_props = row[3] if row[3] else {}
        b_labels = row[4]
        b_props = row[5] if row[5] else {}

        a_label = ":".join(a_labels) if a_labels else "Node"
        b_label = ":".join(b_labels) if b_labels else "Node"

        # Find id key for source node
        a_id_key = None
        for key in ("id", "name", "session_id"):
            if key in a_props:
                a_id_key = key
                break

        # Find id key for target node
        b_id_key = None
        for key in ("id", "name", "session_id"):
            if key in b_props:
                b_id_key = key
                break

        if not a_id_key or not b_id_key:
            # Skip relationships where nodes can't be identified
            continue

        a_match = f"(a:{a_label} {{{a_id_key}: {format_value(a_props[a_id_key])}}})"
        b_match = f"(b:{b_label} {{{b_id_key}: {format_value(b_props[b_id_key])}}})"

        rel_prop_str = ""
        if r_props:
            rel_prop_str = f" {format_props(r_props)}"

        line = f"MATCH {a_match}, {b_match} MERGE (a)-[:{rel_type}{rel_prop_str}]->(b)"
        out.write(line + ";\n")
        count += 1

    print(f"// Exported {count} relationships", file=sys.stderr)
    return count


def export_indexes(graph, out):
    """Export index definitions."""
    try:
        result = graph.query("CALL db.indexes()")
        count = 0
        for row in result.result_set:
            # FalkorDB index format varies, output as comments
            out.write(f"// INDEX: {row}\n")
            count += 1
        print(f"// Found {count} indexes (manual recreation may be needed)", file=sys.stderr)
    except Exception as e:
        print(f"// Could not export indexes: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Export FalkorDB graph as Cypher")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()

    graph = connect()

    if args.output:
        out = open(args.output, "w")
    else:
        out = sys.stdout

    out.write("// FalkorDB Graph Export\n")
    out.write(f"// Graph: {os.getenv('FALKORDB_GRAPH', 'synapse')}\n\n")

    # Export indexes first (as comments for reference)
    out.write("// === INDEXES ===\n")
    export_indexes(graph, out)
    out.write("\n")

    # Export nodes
    out.write("// === NODES ===\n")
    node_count = export_nodes(graph, out)
    out.write("\n")

    # Export relationships
    out.write("// === RELATIONSHIPS ===\n")
    rel_count = export_relationships(graph, out)

    out.write(f"\n// Total: {node_count} nodes, {rel_count} relationships\n")

    if args.output:
        out.close()
        print(f"// Written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
