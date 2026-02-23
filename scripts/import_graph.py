#!/usr/bin/env python3
"""Import Cypher statements into a FalkorDB instance.

Reads Cypher export file (from export_graph.py) and replays all statements
on the target FalkorDB instance.

Usage:
    python scripts/import_graph.py graph_dump.cypher
    python scripts/import_graph.py graph_dump.cypher --target-host localhost --target-port 6379

Environment variables for target (override with --target-* flags):
    FALKORDB_HOST, FALKORDB_PORT, FALKORDB_USERNAME, FALKORDB_PASSWORD, FALKORDB_GRAPH
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

from falkordb import FalkorDB


def connect(host, port, username, password, graph_name):
    kwargs = {"host": host, "port": port, "socket_timeout": 30}
    if username:
        kwargs["username"] = username
    if password:
        kwargs["password"] = password

    db = FalkorDB(**kwargs)
    graph = db.select_graph(graph_name)
    print(f"Connected to {host}:{port} graph={graph_name}")
    return graph


def import_cypher(graph, filepath, batch_size=50):
    """Import Cypher statements from file."""
    with open(filepath, "r") as f:
        lines = f.readlines()

    statements = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        # Remove trailing semicolon
        if line.endswith(";"):
            line = line[:-1]
        statements.append(line)

    total = len(statements)
    print(f"Importing {total} statements...")

    success = 0
    errors = 0
    t_start = time.time()

    for i, stmt in enumerate(statements):
        try:
            graph.query(stmt)
            success += 1
        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"  ERROR [{i+1}]: {e}")
                print(f"    Statement: {stmt[:200]}")
            elif errors == 11:
                print("  ... suppressing further errors")

        if (i + 1) % 100 == 0:
            elapsed = time.time() - t_start
            print(f"  Progress: {i+1}/{total} ({elapsed:.1f}s)")

    elapsed = time.time() - t_start
    print(f"\nDone in {elapsed:.1f}s: {success} succeeded, {errors} failed out of {total}")
    return success, errors


def main():
    parser = argparse.ArgumentParser(description="Import Cypher into FalkorDB")
    parser.add_argument("file", help="Cypher dump file to import")
    parser.add_argument("--target-host", default=os.getenv("FALKORDB_HOST", "localhost"))
    parser.add_argument("--target-port", type=int, default=int(os.getenv("FALKORDB_PORT", 6379)))
    parser.add_argument("--target-username", default=os.getenv("FALKORDB_USERNAME"))
    parser.add_argument("--target-password", default=os.getenv("FALKORDB_PASSWORD"))
    parser.add_argument("--target-graph", default=os.getenv("FALKORDB_GRAPH", "synapse"))
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: file not found: {args.file}")
        sys.exit(1)

    graph = connect(args.target_host, args.target_port,
                    args.target_username, args.target_password,
                    args.target_graph)

    # Test connection
    try:
        graph.query("RETURN 1")
        print("Connection OK")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    success, errors = import_cypher(graph, args.file)
    sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
