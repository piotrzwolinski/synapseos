#!/usr/bin/env python3
"""
Add Powder Coating Application to the graph.

Powder coating environments produce:
1. Combustible dust → STRESSOR_EXPLOSIVE_ATMOSPHERE → GATE_ATEX_ZONE
2. Fine particulates → STRESSOR_PARTICULATE_EXPOSURE → pre-filtration required
3. Chemical vapors (binders/solvents) → STRESSOR_CHEMICAL_VAPORS → carbon adsorption

Also adds "powder" to relevant stressor keyword lists so keyword detection fires.

Usage:
    cd backend && source venv/bin/activate && python database/add_powder_coating.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from neo4j import GraphDatabase

_script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(_script_dir, "..", "..", ".env"))


def add_powder_coating(driver, database: str):
    """Add APP_POWDER_COATING and related relationships."""

    print("\n" + "=" * 60)
    print("ADDING POWDER COATING APPLICATION")
    print("=" * 60)

    with driver.session(database=database) as session:

        # 1. Create APP_POWDER_COATING Application node
        print("\n📦 Creating APP_POWDER_COATING node...")
        session.run("""
            MERGE (app:Application {id: 'APP_POWDER_COATING'})
            SET app.name = 'Powder Coating Line',
                app.keywords = ['powder coating', 'powder', 'proszkowa',
                                'lakiernia proszkowa', 'pulverlackering',
                                'powder coat', 'coating line', 'spray booth']
        """)
        print("   ✓ APP_POWDER_COATING created")

        # 2. EXPOSES_TO relationships
        print("\n🔗 Creating EXPOSES_TO relationships...")
        stressor_links = [
            ("STRESSOR_EXPLOSIVE_ATMOSPHERE",
             "Powder coating booths create combustible dust clouds that can ignite"),
            ("STRESSOR_PARTICULATE_EXPOSURE",
             "Fine powder overspray requires mechanical pre-filtration"),
            ("STRESSOR_CHEMICAL_VAPORS",
             "Binders and solvents in powder coatings release VOC vapors"),
        ]
        for stressor_id, reason in stressor_links:
            session.run("""
                MATCH (app:Application {id: 'APP_POWDER_COATING'})
                MATCH (s:EnvironmentalStressor {id: $stressor_id})
                MERGE (app)-[r:EXPOSES_TO]->(s)
                SET r.reason = $reason
            """, stressor_id=stressor_id, reason=reason)
            print(f"   ✓ EXPOSES_TO → {stressor_id}")

        # 3. TRIGGERS_GATE → GATE_ATEX_ZONE
        print("\n🚦 Creating TRIGGERS_GATE relationship...")
        session.run("""
            MATCH (app:Application {id: 'APP_POWDER_COATING'})
            MATCH (g:LogicGate {id: 'GATE_ATEX_ZONE'})
            MERGE (app)-[:TRIGGERS_GATE]->(g)
        """)
        print("   ✓ TRIGGERS_GATE → GATE_ATEX_ZONE")

        # 4. Add "powder" keyword to relevant stressor nodes
        print("\n📝 Updating stressor keywords...")

        # Add to STRESSOR_PARTICULATE_EXPOSURE
        result = session.run("""
            MATCH (s:EnvironmentalStressor {id: 'STRESSOR_PARTICULATE_EXPOSURE'})
            WITH s, s.keywords AS existing
            WHERE NOT 'powder' IN existing
            SET s.keywords = existing + ['powder', 'powder coating']
            RETURN s.keywords AS updated
        """)
        record = result.single()
        if record:
            print(f"   ✓ STRESSOR_PARTICULATE_EXPOSURE keywords: {record['updated']}")
        else:
            print("   - STRESSOR_PARTICULATE_EXPOSURE already has 'powder'")

        # Add to STRESSOR_EXPLOSIVE_ATMOSPHERE
        result = session.run("""
            MATCH (s:EnvironmentalStressor {id: 'STRESSOR_EXPLOSIVE_ATMOSPHERE'})
            WITH s, s.keywords AS existing
            WHERE NOT 'powder' IN existing
            SET s.keywords = existing + ['powder', 'combustible dust']
            RETURN s.keywords AS updated
        """)
        record = result.single()
        if record:
            print(f"   ✓ STRESSOR_EXPLOSIVE_ATMOSPHERE keywords: {record['updated']}")
        else:
            print("   - STRESSOR_EXPLOSIVE_ATMOSPHERE already has 'powder'")

        # 5. Verify
        print("\n🔍 Verifying...")
        result = session.run("""
            MATCH (app:Application {id: 'APP_POWDER_COATING'})
            OPTIONAL MATCH (app)-[:EXPOSES_TO]->(s:EnvironmentalStressor)
            OPTIONAL MATCH (app)-[:TRIGGERS_GATE]->(g:LogicGate)
            RETURN app.name AS name,
                   app.keywords AS keywords,
                   collect(DISTINCT s.name) AS stressors,
                   collect(DISTINCT g.name) AS gates
        """)
        record = result.single()
        if record:
            print(f"   Name: {record['name']}")
            print(f"   Keywords: {record['keywords']}")
            print(f"   Stressors: {record['stressors']}")
            print(f"   Gates: {record['gates']}")


def main():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    if not all([uri, user, password]):
        print("Error: Missing Neo4j connection environment variables")
        sys.exit(1)

    print(f"Connecting to Neo4j at {uri}...")
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        add_powder_coating(driver, database)
        print("\n✅ Powder Coating application seeded successfully")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
