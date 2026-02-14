#!/usr/bin/env python3
"""
Neo4j Graph Backup Script

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

load_dotenv(dotenv_path="../.env")


def export_nodes(session):
    """Export all nodes with labels and properties."""
    result = session.run("""
        MATCH (n)
        RETURN labels(n) AS labels, properties(n) AS props, elementId(n) AS eid
    """)
    nodes = []
    for record in result:
        nodes.append({
            "labels": record["labels"],
            "props": dict(record["props"]),
            "eid": record["eid"]
        })
    return nodes


def export_relationships(session):
    """Export all relationships with types, properties, and endpoint IDs."""
    result = session.run("""
        MATCH (a)-[r]->(b)
        RETURN labels(a) AS a_labels, properties(a) AS a_props,
               type(r) AS rel_type, properties(r) AS rel_props,
               labels(b) AS b_labels, properties(b) AS b_props
    """)
    rels = []
    for record in result:
        rels.append({
            "a_labels": record["a_labels"],
            "a_props": dict(record["a_props"]),
            "rel_type": record["rel_type"],
            "rel_props": dict(record["rel_props"]),
            "b_labels": record["b_labels"],
            "b_props": dict(record["b_props"])
        })
    return rels


def get_counts(session):
    """Get node and relationship counts by label/type."""
    node_counts = session.run("""
        MATCH (n)
        WITH labels(n) AS lbls
        UNWIND lbls AS label
        RETURN label, count(*) AS cnt
        ORDER BY cnt DESC
    """)
    rel_counts = session.run("""
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, count(*) AS cnt
        ORDER BY cnt DESC
    """)
    return (
        [(r["label"], r["cnt"]) for r in node_counts],
        [(r["rel_type"], r["cnt"]) for r in rel_counts]
    )


def main():
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    if not all([uri, user, password]):
        print("Error: Missing Neo4j connection environment variables")
        print("Required: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(__file__), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"graph_backup_{timestamp}.json")

    print("=" * 60)
    print(f"NEO4J GRAPH BACKUP — {timestamp}")
    print("=" * 60)
    print(f"\nConnecting to Neo4j at {uri}...")

    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session(database=database) as session:
            # Verify connection
            result = session.run("RETURN 1 AS test")
            if result.single()["test"] != 1:
                raise Exception("Connection test failed")
            print("Connected successfully!")

            # Get counts first
            print("\nCurrent graph statistics:")
            node_counts, rel_counts = get_counts(session)
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
            print(f"\nExporting nodes...")
            nodes = export_nodes(session)
            print(f"  Exported {len(nodes)} nodes")

            print(f"Exporting relationships...")
            rels = export_relationships(session)
            print(f"  Exported {len(rels)} relationships")

        # Write backup
        backup_data = {
            "timestamp": timestamp,
            "neo4j_uri": uri,
            "database": database,
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
        print(f"BACKUP COMPLETE")
        print(f"{'=' * 60}")
        print(f"File: {backup_path}")
        print(f"Size: {file_size_mb:.2f} MB")
        print(f"Nodes: {len(nodes)}, Relationships: {len(rels)}")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
