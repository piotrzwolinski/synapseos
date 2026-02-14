#!/usr/bin/env python3
"""
Add GDP Housing Length with auto_resolve=true to the graph.

GDP pre-filter housings always use the shortest standard length (250mm).
Instead of hardcoding this in Python, we store it as graph metadata:
  - auto_resolve = true  → engine skips asking the user
  - default_value = 250  → automatically applied value

This keeps the engine 100% domain-agnostic.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from neo4j import GraphDatabase

_script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(_script_dir, "..", "..", ".env"))


def add_gdp_auto_resolve(driver, database: str):
    """Add GDP housing length VariableFeature with auto_resolve flag."""

    print("\n" + "=" * 60)
    print("ADDING GDP AUTO-RESOLVE HOUSING LENGTH")
    print("=" * 60)

    with driver.session(database=database) as session:

        # Create GDP housing length feature with auto_resolve
        print("\n📦 Adding Housing Length feature to GDP (auto_resolve=true)...")

        session.run("""
            MATCH (gdp:ProductFamily)
            WHERE gdp.id = 'FAM_GDP' OR gdp.name CONTAINS 'GDP'

            MERGE (feat_len:VariableFeature {id: 'FEAT_HOUSING_LENGTH_GDP'})
            SET feat_len.name = 'Housing Length',
                feat_len.feature_name = 'Housing Length',
                feat_len.is_variable = true,
                feat_len.applies_to = 'GDP',
                feat_len.parameter_name = 'housing_length',
                feat_len.description = 'Panel filter housing depth - standard short length',
                feat_len.auto_resolve = true,
                feat_len.default_value = 250

            MERGE (gdp)-[:HAS_VARIABLE_FEATURE]->(feat_len)

            // Single option (auto-resolved, not shown to user)
            MERGE (opt:FeatureOption {id: 'OPT_GDP_LEN_250'})
            SET opt.name = '250mm (Standard)',
                opt.value = '250',
                opt.description = 'Standard panel filter housing depth',
                opt.is_default = true

            MERGE (feat_len)-[:HAS_OPTION]->(opt)

            MERGE (disc:Discriminator {id: 'DISC_GDP_LENGTH'})
            SET disc.question = 'Which housing length is required?',
                disc.why_needed = 'Panel filter housing depth',
                disc.parameter_name = 'housing_length'

            MERGE (feat_len)-[:SELECTION_DEPENDS_ON]->(disc)
        """)
        print("   ✓ GDP housing length feature added (auto_resolve=true, default=250mm)")

        # Verify
        print("\n🔍 Verifying...")
        result = session.run("""
            MATCH (pf:ProductFamily)-[:HAS_VARIABLE_FEATURE]->(f:VariableFeature)
            WHERE f.auto_resolve = true
            RETURN pf.name AS family, f.name AS feature,
                   f.default_value AS default_val, f.auto_resolve AS auto
        """)
        for record in result:
            print(f"   {record['family']}: {record['feature']} → "
                  f"default={record['default_val']}, auto_resolve={record['auto']}")


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
        add_gdp_auto_resolve(driver, database)
        print("\n✅ GDP auto-resolve seeded successfully")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
