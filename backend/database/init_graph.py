#!/usr/bin/env python3
"""
Generic Graph Database Initializer

Initializes the database schema for the Universal Reasoning Engine.
Supports both FalkorDB (preferred) and Neo4j (fallback).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(dotenv_path="../../.env")


def init_falkordb():
    """Initialize FalkorDB with generic schema."""
    from falkordb import FalkorDB

    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", 6379))

    print(f"🔗 Connecting to FalkorDB at {host}:{port}...")

    db = FalkorDB(host=host, port=port)
    graph = db.select_graph("hvac")

    print("📋 Creating schema...")

    # Layer 1: Inventory
    schema_queries = [
        # Constraints (unique IDs)
        "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Item) REQUIRE i.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Property) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Category) REQUIRE c.id IS UNIQUE",

        # Layer 2: Domain Rules
        "CREATE CONSTRAINT IF NOT EXISTS FOR (ctx:Context) REQUIRE ctx.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (con:Constraint) REQUIRE con.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Risk) REQUIRE r.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Solution) REQUIRE s.id IS UNIQUE",

        # Layer 3: Playbook
        "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Discriminator) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (o:Option) REQUIRE o.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (st:Strategy) REQUIRE st.id IS UNIQUE",

        # Indexes for performance
        "CREATE INDEX IF NOT EXISTS FOR (i:Item) ON (i.name)",
        "CREATE INDEX IF NOT EXISTS FOR (p:Property) ON (p.key)",
        "CREATE INDEX IF NOT EXISTS FOR (ctx:Context) ON (ctx.name)",
        "CREATE INDEX IF NOT EXISTS FOR (con:Constraint) ON (con.target_key)",
    ]

    for query in schema_queries:
        try:
            graph.query(query)
            print(f"   ✓ {query[:60]}...")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"   ⊘ Already exists: {query[:50]}...")
            else:
                print(f"   ⚠ {e}")

    # Create vector index for Context embeddings
    print("\n🔍 Creating vector index for Context embeddings...")
    try:
        # FalkorDB vector index syntax
        graph.query("""
            CALL db.idx.vector.createNodeIndex('Context', 'embedding', 768, 'cosine')
        """)
        print("   ✓ Vector index created")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("   ⊘ Vector index already exists")
        else:
            print(f"   ⚠ Vector index: {e}")

    print("\n✅ FalkorDB schema initialized!")
    return graph


def init_neo4j():
    """Initialize Neo4j with generic schema."""
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    print(f"🔗 Connecting to Neo4j at {uri}...")

    driver = GraphDatabase.driver(uri, auth=(user, password))

    print("📋 Creating schema...")

    schema_queries = [
        # Layer 1: Inventory
        "CREATE CONSTRAINT item_id IF NOT EXISTS FOR (i:Item) REQUIRE i.id IS UNIQUE",
        "CREATE CONSTRAINT property_id IF NOT EXISTS FOR (p:Property) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT category_id IF NOT EXISTS FOR (c:Category) REQUIRE c.id IS UNIQUE",

        # Layer 2: Domain Rules
        "CREATE CONSTRAINT context_id IF NOT EXISTS FOR (ctx:Context) REQUIRE ctx.id IS UNIQUE",
        "CREATE CONSTRAINT constraint_id IF NOT EXISTS FOR (con:Constraint) REQUIRE con.id IS UNIQUE",
        "CREATE CONSTRAINT risk_id IF NOT EXISTS FOR (r:Risk) REQUIRE r.id IS UNIQUE",
        "CREATE CONSTRAINT solution_id IF NOT EXISTS FOR (s:Solution) REQUIRE s.id IS UNIQUE",

        # Layer 3: Playbook
        "CREATE CONSTRAINT discriminator_id IF NOT EXISTS FOR (d:Discriminator) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT option_id IF NOT EXISTS FOR (o:Option) REQUIRE o.id IS UNIQUE",
        "CREATE CONSTRAINT strategy_id IF NOT EXISTS FOR (st:Strategy) REQUIRE st.id IS UNIQUE",

        # Indexes
        "CREATE INDEX item_name IF NOT EXISTS FOR (i:Item) ON (i.name)",
        "CREATE INDEX property_key IF NOT EXISTS FOR (p:Property) ON (p.key)",
        "CREATE INDEX context_name IF NOT EXISTS FOR (ctx:Context) ON (ctx.name)",
        "CREATE INDEX constraint_key IF NOT EXISTS FOR (con:Constraint) ON (con.target_key)",
    ]

    with driver.session(database=database) as session:
        for query in schema_queries:
            try:
                session.run(query)
                print(f"   ✓ {query[:60]}...")
            except Exception as e:
                if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                    print(f"   ⊘ Already exists: {query[:50]}...")
                else:
                    print(f"   ⚠ {e}")

    print("\n✅ Neo4j schema initialized!")
    return driver


def main():
    """Main entry point - tries FalkorDB first, then Neo4j."""
    try:
        import falkordb
        print("📊 Using FalkorDB...")
        return init_falkordb()
    except ImportError:
        print("FalkorDB not available, using Neo4j...")
        return init_neo4j()


if __name__ == "__main__":
    main()
