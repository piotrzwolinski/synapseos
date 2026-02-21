"""Migrate all data from Neo4j Aura to FalkorDB Cloud.

Reads every node and relationship from Neo4j, recreates them in FalkorDB.
Uses a temporary _neo4j_eid property on nodes to map relationships.

Usage:
    cd backend && python database/migrate_neo4j_to_falkor.py [--skip-session]
"""
import os
import sys
import time
import argparse
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from neo4j import GraphDatabase
from falkordb import FalkorDB


# --- Config ---
BATCH_SIZE = 200

# Session-related labels to skip with --skip-session
SESSION_LABELS = {
    "Session", "ActiveProject", "ConversationTurn", "TagUnit", "ExpertReview",
}
SESSION_REL_TYPES = {
    "HAS_TURN", "HAS_UNIT", "TARGETS_FAMILY", "WORKING_ON", "SIZED_AS",
    "USES_MATERIAL", "HAS_REVIEW",
}


def connect_neo4j():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    return driver, database


def connect_falkor():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", 6379))
    username = os.getenv("FALKORDB_USERNAME")
    password = os.getenv("FALKORDB_PASSWORD")
    graph_name = os.getenv("FALKORDB_GRAPH", "hvac")

    kwargs = {
        "host": host,
        "port": port,
        "socket_timeout": 30,
        "socket_connect_timeout": 15,
    }
    if username:
        kwargs["username"] = username
    if password:
        kwargs["password"] = password

    db = FalkorDB(**kwargs)
    graph = db.select_graph(graph_name)
    return graph


def _sanitize_props(props: dict) -> dict:
    """Clean property values for FalkorDB compatibility."""
    clean = {}
    for k, v in props.items():
        if v is None:
            continue
        # Convert neo4j datetime/date to ISO string
        if hasattr(v, 'isoformat'):
            clean[k] = v.isoformat()
        # Convert neo4j duration to string
        elif hasattr(v, 'months') and hasattr(v, 'days'):
            clean[k] = str(v)
        # Lists: sanitize recursively
        elif isinstance(v, list):
            clean[k] = [
                x.isoformat() if hasattr(x, 'isoformat') else x
                for x in v
            ]
        else:
            clean[k] = v
    return clean


def export_nodes(driver, database, skip_session=False):
    """Export all nodes from Neo4j, grouped by label combination."""
    print("\n--- Exporting nodes from Neo4j ---")
    nodes_by_labels = defaultdict(list)

    with driver.session(database=database) as session:
        result = session.run(
            "MATCH (n) RETURN elementId(n) AS eid, labels(n) AS labels, properties(n) AS props"
        )
        for record in result:
            eid = record["eid"]
            labels = sorted(record["labels"])
            props = dict(record["props"])

            # Skip session nodes if requested
            if skip_session and any(l in SESSION_LABELS for l in labels):
                continue

            label_key = tuple(labels)
            nodes_by_labels[label_key].append((eid, _sanitize_props(props)))

    total = sum(len(v) for v in nodes_by_labels.values())
    print(f"  Exported {total} nodes across {len(nodes_by_labels)} label combinations")
    return nodes_by_labels


def export_relationships(driver, database, skip_session=False):
    """Export all relationships from Neo4j."""
    print("\n--- Exporting relationships from Neo4j ---")
    rels = []

    with driver.session(database=database) as session:
        result = session.run(
            "MATCH (a)-[r]->(b) "
            "RETURN elementId(a) AS src_eid, elementId(b) AS tgt_eid, "
            "type(r) AS rel_type, properties(r) AS props"
        )
        for record in result:
            rel_type = record["rel_type"]
            if skip_session and rel_type in SESSION_REL_TYPES:
                continue
            rels.append({
                "src": record["src_eid"],
                "tgt": record["tgt_eid"],
                "type": rel_type,
                "props": _sanitize_props(dict(record["props"])),
            })

    print(f"  Exported {len(rels)} relationships")
    return rels


def import_nodes(graph, nodes_by_labels):
    """Create nodes in FalkorDB with _neo4j_eid for relationship mapping."""
    print("\n--- Importing nodes to FalkorDB ---")
    total = sum(len(v) for v in nodes_by_labels.values())
    created = 0

    for label_combo, nodes in nodes_by_labels.items():
        label_str = ":".join(label_combo)
        batches = [nodes[i:i+BATCH_SIZE] for i in range(0, len(nodes), BATCH_SIZE)]

        for batch in batches:
            for eid, props in batch:
                props["_neo4j_eid"] = eid
                # Build SET clause from props
                cypher = f"CREATE (n:{label_str}) SET n = $props"
                try:
                    graph.query(cypher, params={"props": props})
                except Exception as e:
                    print(f"  WARN: Failed to create node {eid} ({label_str}): {e}")
                    continue
                created += 1

            print(f"  {created}/{total} nodes created ...", end="\r")

    print(f"  {created}/{total} nodes created       ")
    return created


def import_relationships(graph, rels):
    """Create relationships in FalkorDB using _neo4j_eid mapping."""
    print("\n--- Importing relationships to FalkorDB ---")
    total = len(rels)
    created = 0
    failed = 0

    for i, rel in enumerate(rels):
        cypher = (
            f"MATCH (a {{_neo4j_eid: $src}}), (b {{_neo4j_eid: $tgt}}) "
            f"CREATE (a)-[r:{rel['type']}]->(b)"
        )
        params = {"src": rel["src"], "tgt": rel["tgt"]}

        if rel["props"]:
            cypher = (
                f"MATCH (a {{_neo4j_eid: $src}}), (b {{_neo4j_eid: $tgt}}) "
                f"CREATE (a)-[r:{rel['type']}]->(b) SET r = $props"
            )
            params["props"] = rel["props"]

        try:
            graph.query(cypher, params=params)
            created += 1
        except Exception as e:
            failed += 1
            if failed <= 5:
                print(f"  WARN: Failed rel {rel['type']} ({rel['src']} -> {rel['tgt']}): {e}")

        if (i + 1) % 500 == 0:
            print(f"  {created}/{total} relationships created ({failed} failed) ...", end="\r")

    print(f"  {created}/{total} relationships created ({failed} failed)       ")
    return created, failed


def cleanup_temp_props(graph):
    """Remove _neo4j_eid temporary property from all nodes."""
    print("\n--- Cleaning up _neo4j_eid property ---")
    try:
        graph.query("MATCH (n) WHERE n._neo4j_eid IS NOT NULL SET n._neo4j_eid = NULL")
        # FalkorDB may not support REMOVE, try SET to NULL or just leave it
        print("  Done (set to NULL)")
    except Exception as e:
        print(f"  WARN: Cleanup failed: {e}")
        print("  You can clean up manually: MATCH (n) SET n._neo4j_eid = NULL")


def verify(graph):
    """Quick verification of imported data."""
    print("\n--- Verification ---")
    from db_result_helpers import result_to_dicts, result_value

    node_count = result_value(graph.query("MATCH (n) RETURN count(n) AS cnt"), "cnt", 0)
    rel_count = result_value(graph.query("MATCH ()-[r]->() RETURN count(r) AS cnt"), "cnt", 0)
    print(f"  FalkorDB now has: {node_count} nodes, {rel_count} relationships")

    # Sample labels
    labels = [
        "ProductFamily", "DimensionModule", "Material", "Environment",
        "Application", "Stressor", "CausalRule", "Trait",
    ]
    for label in labels:
        cnt = result_value(graph.query(f"MATCH (n:{label}) RETURN count(n) AS cnt"), "cnt", 0)
        if cnt > 0:
            print(f"  {label}: {cnt}")


def main():
    parser = argparse.ArgumentParser(description="Migrate Neo4j → FalkorDB")
    parser.add_argument("--skip-session", action="store_true",
                        help="Skip Layer 4 session state (Session, TagUnit, ConversationTurn, etc.)")
    parser.add_argument("--skip-cleanup", action="store_true",
                        help="Keep _neo4j_eid property on nodes (for debugging)")
    args = parser.parse_args()

    print("=" * 60)
    print("Neo4j → FalkorDB Migration")
    print("=" * 60)

    # Connect
    driver, database = connect_neo4j()
    print(f"Neo4j: {os.getenv('NEO4J_URI')}")

    graph = connect_falkor()
    print(f"FalkorDB: {os.getenv('FALKORDB_HOST')}:{os.getenv('FALKORDB_PORT')}/{os.getenv('FALKORDB_GRAPH')}")

    if args.skip_session:
        print("Skipping session state (Layer 4)")

    # Check if FalkorDB already has data
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from db_result_helpers import result_value
    existing = result_value(graph.query("MATCH (n) RETURN count(n) AS cnt"), "cnt", 0)
    if existing > 0:
        print(f"\n⚠ FalkorDB already has {existing} nodes!")
        resp = input("Clear and re-import? [y/N] ")
        if resp.lower() == 'y':
            print("Clearing FalkorDB graph...")
            graph.query("MATCH (n) DETACH DELETE n")
            print("  Cleared.")
        else:
            print("Aborting.")
            return

    start = time.time()

    # Export
    nodes_by_labels = export_nodes(driver, database, args.skip_session)
    rels = export_relationships(driver, database, args.skip_session)
    driver.close()

    export_time = time.time() - start
    print(f"\n  Export completed in {export_time:.1f}s")

    # Import
    import_start = time.time()
    import_nodes(graph, nodes_by_labels)
    import_relationships(graph, rels)

    import_time = time.time() - import_start
    print(f"\n  Import completed in {import_time:.1f}s")

    # Cleanup
    if not args.skip_cleanup:
        cleanup_temp_props(graph)

    # Verify
    verify(graph)

    total_time = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"Migration complete in {total_time:.1f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
