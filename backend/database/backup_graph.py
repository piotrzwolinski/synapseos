#!/usr/bin/env python3
"""
FalkorDB Graph Backup Script

Exports all nodes and relationships as Cypher statements to a timestamped file.
Run this BEFORE any schema migrations to ensure rollback capability.

Usage:
    cd backend && python -m database.backup_graph
"""

import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv
from db_result_helpers import result_to_dicts, result_single, result_value

load_dotenv(dotenv_path="../.env")


def export_nodes(graph):
    """Export all nodes with labels and properties."""
    result = graph.query("""
        MATCH (n)
        RETURN labels(n) AS labels, properties(n) AS props, id(n) AS eid
    """)
    nodes = []
    for record in result_to_dicts(result):
        nodes.append({
            "labels": record["labels"],
            "props": dict(record["props"]) if isinstance(record["props"], dict) else record["props"],
            "eid": record["eid"]
        })
    return nodes


def export_relationships(graph):
    """Export all relationships with types, properties, and endpoint IDs."""
    result = graph.query("""
        MATCH (a)-[r]->(b)
        RETURN labels(a) AS a_labels, properties(a) AS a_props,
               type(r) AS rel_type, properties(r) AS rel_props,
               labels(b) AS b_labels, properties(b) AS b_props
    """)
    rels = []
    for record in result_to_dicts(result):
        rels.append({
            "a_labels": record["a_labels"],
            "a_props": dict(record["a_props"]) if isinstance(record["a_props"], dict) else record["a_props"],
            "rel_type": record["rel_type"],
            "rel_props": dict(record["rel_props"]) if isinstance(record["rel_props"], dict) else record["rel_props"],
            "b_labels": record["b_labels"],
            "b_props": dict(record["b_props"]) if isinstance(record["b_props"], dict) else record["b_props"],
        })
    return rels


def get_counts(graph):
    """Get node and relationship counts by label/type."""
    node_result = graph.query("""
        MATCH (n)
        WITH labels(n) AS lbls
        UNWIND lbls AS label
        RETURN label, count(*) AS cnt
        ORDER BY cnt DESC
    """)
    rel_result = graph.query("""
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, count(*) AS cnt
        ORDER BY cnt DESC
    """)
    return (
        [(r["label"], r["cnt"]) for r in result_to_dicts(node_result)],
        [(r["rel_type"], r["cnt"]) for r in result_to_dicts(rel_result)]
    )


def main():
    from falkordb import FalkorDB

    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", 6379))
    password = os.getenv("FALKORDB_PASSWORD", None)
    graph_name = os.getenv("FALKORDB_GRAPH", "hvac")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(__file__), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"graph_backup_{timestamp}.json")

    print("=" * 60)
    print(f"FALKORDB GRAPH BACKUP -- {timestamp}")
    print("=" * 60)
    print(f"\nConnecting to FalkorDB at {host}:{port}...")

    db = FalkorDB(host=host, port=port, password=password)
    graph = db.select_graph(graph_name)

    try:
        # Verify connection
        result = graph.query("RETURN 1 AS test")
        if result_single(result)["test"] != 1:
            raise Exception("Connection test failed")
        print("Connected successfully!")

        # Get counts first
        print("\nCurrent graph statistics:")
        node_counts, rel_counts = get_counts(graph)
        total_nodes = 0
        for label, cnt in node_counts:
            print(f"  :{label} = {cnt} nodes")
            total_nodes += cnt
        total_rels = 0
        for rel_type, cnt in rel_counts:
            print(f"  [:{rel_type}] = {cnt} relationships")
            total_rels += cnt
        print(f"\n  Total: {total_nodes} nodes, {total_rels} relationships")

        # Export
        print("\nExporting nodes...")
        nodes = export_nodes(graph)
        print(f"  Exported {len(nodes)} nodes")

        print("Exporting relationships...")
        rels = export_relationships(graph)
        print(f"  Exported {len(rels)} relationships")

        # Write backup
        backup_data = {
            "timestamp": timestamp,
            "falkordb_host": f"{host}:{port}",
            "graph": graph_name,
            "stats": {
                "node_counts": {label: cnt for label, cnt in node_counts},
                "rel_counts": {rel_type: cnt for rel_type, cnt in rel_counts},
                "total_nodes": len(nodes),
                "total_relationships": len(rels)
            },
            "nodes": nodes,
            "relationships": rels
        }

        with open(backup_path, "w") as f:
            json.dump(backup_data, f, indent=2, default=str)

        file_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
        print(f"\n{'=' * 60}")
        print("BACKUP COMPLETE")
        print(f"{'=' * 60}")
        print(f"File: {backup_path}")
        print(f"Size: {file_size_mb:.2f} MB")
        print(f"Nodes: {len(nodes)}, Relationships: {len(rels)}")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
