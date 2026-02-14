#!/usr/bin/env python3
"""Load the 3-layer graph schema into Neo4j.

This script reads graph_schema.cypher and executes it against Neo4j.
Run from the backend directory: python load_graph_schema.py
"""

import os
import sys
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path="../.env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

SCHEMA_FILE = "database/graph_schema.cypher"


def parse_cypher_statements(file_path: str) -> list[str]:
    """Parse Cypher file into individual statements.

    Handles:
    - Single-line comments (//)
    - Multi-statement blocks separated by ;
    - CALL procedures
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove single-line comments but keep the content structure
    lines = []
    for line in content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('//'):
            continue  # Skip comment-only lines
        # Remove inline comments
        if '//' in line and not line.strip().startswith('CALL'):
            line = line.split('//')[0]
        lines.append(line)

    content = '\n'.join(lines)

    # Split by semicolon, but be careful with CALL statements
    statements = []
    current_stmt = []

    for line in content.split('\n'):
        current_stmt.append(line)
        if line.strip().endswith(';'):
            stmt = '\n'.join(current_stmt).strip()
            if stmt and stmt != ';':
                # Remove trailing semicolon for execution
                stmt = stmt.rstrip(';').strip()
                if stmt:
                    statements.append(stmt)
            current_stmt = []

    # Don't forget the last statement if it doesn't end with ;
    if current_stmt:
        stmt = '\n'.join(current_stmt).strip()
        if stmt and stmt != ';':
            stmt = stmt.rstrip(';').strip()
            if stmt:
                statements.append(stmt)

    return statements


def load_schema():
    """Load the graph schema into Neo4j."""
    print(f"Connecting to Neo4j at {NEO4J_URI}...")

    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    try:
        # Verify connection
        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("RETURN 1 AS test")
            if result.single()["test"] == 1:
                print("Connected successfully!")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    # Parse schema file
    print(f"\nParsing {SCHEMA_FILE}...")
    statements = parse_cypher_statements(SCHEMA_FILE)
    print(f"Found {len(statements)} statements to execute.")

    # Execute statements
    print("\nExecuting schema statements...")
    success_count = 0
    error_count = 0

    with driver.session(database=NEO4J_DATABASE) as session:
        for i, stmt in enumerate(statements, 1):
            # Show progress
            if stmt.startswith('CREATE CONSTRAINT'):
                desc = f"Creating constraint..."
            elif stmt.startswith('CREATE INDEX'):
                desc = f"Creating index..."
            elif stmt.startswith('MERGE') and 'Material' in stmt:
                desc = f"Creating Material node..."
            elif stmt.startswith('MERGE') and 'Application' in stmt:
                desc = f"Creating Application node..."
            elif stmt.startswith('MERGE') and 'Risk' in stmt:
                desc = f"Creating Risk node..."
            elif stmt.startswith('MERGE') and 'ProductFamily' in stmt:
                desc = f"Creating ProductFamily node..."
            elif stmt.startswith('MERGE') and 'Parameter' in stmt:
                desc = f"Creating Parameter node..."
            elif stmt.startswith('MERGE') and 'Question' in stmt:
                desc = f"Creating Question node..."
            elif stmt.startswith('MERGE') and 'Strategy' in stmt:
                desc = f"Creating Strategy node..."
            elif stmt.startswith('MATCH'):
                desc = f"Creating relationship..."
            elif stmt.startswith('CALL'):
                desc = f"Calling procedure..."
            else:
                desc = stmt[:50] + "..." if len(stmt) > 50 else stmt

            try:
                session.run(stmt)
                success_count += 1
                print(f"  [{i}/{len(statements)}] ✓ {desc}")
            except Exception as e:
                error_count += 1
                error_msg = str(e)
                # Ignore "already exists" errors for constraints/indexes
                if "already exists" in error_msg.lower() or "equivalent" in error_msg.lower():
                    print(f"  [{i}/{len(statements)}] ⊘ {desc} (already exists)")
                    success_count += 1
                    error_count -= 1
                else:
                    print(f"  [{i}/{len(statements)}] ✗ {desc}")
                    print(f"      Error: {error_msg[:100]}")

    driver.close()

    print(f"\n{'='*50}")
    print(f"Schema loading complete!")
    print(f"  Successful: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"{'='*50}")

    # Verify by counting nodes
    print("\nVerifying loaded data...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session(database=NEO4J_DATABASE) as session:
        counts = session.run("""
            MATCH (n)
            WITH labels(n) AS labels, count(*) AS count
            UNWIND labels AS label
            RETURN label, sum(count) AS total
            ORDER BY total DESC
        """)
        print("\nNode counts by label:")
        for record in counts:
            print(f"  {record['label']}: {record['total']}")

    driver.close()
    print("\nDone!")


if __name__ == "__main__":
    load_schema()
