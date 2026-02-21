#!/usr/bin/env python3
"""
Generic Graph Database Initializer

Initializes the database schema for the Universal Reasoning Engine.
Uses FalkorDB as the graph database backend.
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


def main():
    """Main entry point - initializes FalkorDB schema."""
    print("📊 Using FalkorDB...")
    return init_falkordb()


if __name__ == "__main__":
    main()
