#!/usr/bin/env python3
"""
Add Accessory Compatibility Schema to Neo4j

This script creates the accessory/option compatibility relationships
that enable the Strict Compatibility Validator to block invalid configurations.

The key principle: If there's no explicit relationship in the graph,
the combination is NOT allowed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(dotenv_path="../.env")


def create_accessory_nodes(driver, database: str):
    """Create accessory/option nodes with compatibility data."""

    print("\n" + "-" * 50)
    print("CREATING ACCESSORY NODES")
    print("-" * 50)

    with driver.session(database=database) as session:
        # EXL Eccentric Locking Mechanism
        print("\n🔧 Creating EXL accessory...")
        session.run("""
            MERGE (exl:Accessory {id: 'ACC_EXL'})
            SET exl.name = 'EXL',
                exl.full_name = 'Eccentric Locking Mechanism',
                exl.description = 'Quick-release eccentric locking for bag filter frames',
                exl.category = 'Locking Mechanism',
                exl.applies_to = 'Bag Filter Housings'
        """)

        # L (Left Hinge) Option
        print("🔧 Creating L (Left Hinge) accessory...")
        session.run("""
            MERGE (l:Accessory {id: 'ACC_L'})
            SET l.name = 'L',
                l.full_name = 'Left Hinge Door',
                l.description = 'Service door with left-side hinge (default is right)',
                l.category = 'Door Configuration'
        """)

        # Polysfilter Rail
        print("🔧 Creating Polis (Polysfilter Rail) accessory...")
        session.run("""
            MERGE (polis:Accessory {id: 'ACC_POLIS'})
            SET polis.name = 'Polis',
                polis.full_name = 'Polysfilter Rail',
                polis.description = 'Rail system for bag filter mounting',
                polis.category = 'Mounting System',
                polis.min_housing_length = 900
        """)

        # Bayonet Mount (GDC specific)
        print("🔧 Creating Bayonet mounting system...")
        session.run("""
            MERGE (bay:MountingSystem {id: 'MOUNT_BAYONET'})
            SET bay.name = 'Bayonet',
                bay.full_name = 'Bayonet Cylinder Mount',
                bay.description = 'Twist-lock mounting for carbon filter cylinders',
                bay.applies_to = 'Carbon Filter Housings'
        """)

        print("   ✓ Accessory nodes created")


def create_compatibility_relationships(driver, database: str):
    """Create explicit compatibility relationships between products and accessories."""

    print("\n" + "-" * 50)
    print("CREATING COMPATIBILITY RELATIONSHIPS")
    print("-" * 50)

    with driver.session(database=database) as session:
        # GDB is compatible with EXL, L, Polis
        print("\n🔗 Linking GDB to compatible accessories...")
        session.run("""
            MATCH (gdb:ProductFamily)
            WHERE gdb.id = 'FAM_GDB' OR gdb.name CONTAINS 'GDB Kanalfilterskåp'

            MATCH (exl:Accessory {id: 'ACC_EXL'})
            MERGE (gdb)-[:HAS_COMPATIBLE_ACCESSORY {note: 'Standard option for bag filter housings'}]->(exl)

            WITH gdb
            MATCH (l:Accessory {id: 'ACC_L'})
            MERGE (gdb)-[:HAS_COMPATIBLE_ACCESSORY {note: 'Door hinge option'}]->(l)

            WITH gdb
            MATCH (polis:Accessory {id: 'ACC_POLIS'})
            MERGE (gdb)-[:HAS_COMPATIBLE_ACCESSORY {note: 'Requires 900mm+ housing length'}]->(polis)
        """)
        print("   ✓ GDB compatibility set: EXL ✓, L ✓, Polis ✓")

        # GDMI is compatible with EXL, L, Polis
        print("\n🔗 Linking GDMI to compatible accessories...")
        session.run("""
            MATCH (gdmi:ProductFamily)
            WHERE gdmi.id = 'FAM_GDMI' OR gdmi.name CONTAINS 'GDMI'

            MATCH (exl:Accessory {id: 'ACC_EXL'})
            MERGE (gdmi)-[:HAS_COMPATIBLE_ACCESSORY {note: 'Standard option for insulated bag filter housings'}]->(exl)

            WITH gdmi
            MATCH (l:Accessory {id: 'ACC_L'})
            MERGE (gdmi)-[:HAS_COMPATIBLE_ACCESSORY {note: 'Door hinge option'}]->(l)

            WITH gdmi
            MATCH (polis:Accessory {id: 'ACC_POLIS'})
            MERGE (gdmi)-[:HAS_COMPATIBLE_ACCESSORY {note: 'Requires 850mm+ housing length'}]->(polis)
        """)
        print("   ✓ GDMI compatibility set: EXL ✓, L ✓, Polis ✓")

        # GDP is compatible with EXL, L (but NOT Polis - too short)
        print("\n🔗 Linking GDP to compatible accessories...")
        session.run("""
            MATCH (gdp:ProductFamily)
            WHERE gdp.id = 'FAM_GDP' OR gdp.name CONTAINS 'GDP'

            MATCH (exl:Accessory {id: 'ACC_EXL'})
            MERGE (gdp)-[:HAS_COMPATIBLE_ACCESSORY {note: 'Available for panel filter housings'}]->(exl)

            WITH gdp
            MATCH (l:Accessory {id: 'ACC_L'})
            MERGE (gdp)-[:HAS_COMPATIBLE_ACCESSORY {note: 'Door hinge option'}]->(l)
        """)
        print("   ✓ GDP compatibility set: EXL ✓, L ✓, Polis ✗ (too short)")

        # GDC uses Bayonet - explicitly NOT compatible with EXL
        print("\n🔗 Linking GDC to Bayonet system (NOT EXL)...")
        session.run("""
            MATCH (gdc:ProductFamily)
            WHERE gdc.id = 'FAM_GDC' OR gdc.name CONTAINS 'GDC'

            MATCH (bay:MountingSystem {id: 'MOUNT_BAYONET'})
            MERGE (gdc)-[:USES_MOUNTING_SYSTEM]->(bay)

            WITH gdc
            MATCH (l:Accessory {id: 'ACC_L'})
            MERGE (gdc)-[:HAS_COMPATIBLE_ACCESSORY {note: 'Door hinge option'}]->(l)
        """)
        print("   ✓ GDC compatibility set: Bayonet ✓, L ✓, EXL ✗ (incompatible)")

        # Create explicit INCOMPATIBLE relationships for validation
        print("\n⛔ Creating explicit INCOMPATIBLE relationships...")
        session.run("""
            MATCH (gdc:ProductFamily)
            WHERE gdc.id = 'FAM_GDC' OR gdc.name CONTAINS 'GDC'

            MATCH (exl:Accessory {id: 'ACC_EXL'})
            MERGE (gdc)-[:INCOMPATIBLE_WITH {
                reason: 'GDC uses Bayonet mounting system for carbon cylinders, not compatible with EXL eccentric locks designed for bag filter frames'
            }]->(exl)

            WITH gdc
            MATCH (polis:Accessory {id: 'ACC_POLIS'})
            MERGE (gdc)-[:INCOMPATIBLE_WITH {
                reason: 'Polysfilter rail is for bag filter mounting, not carbon cylinders'
            }]->(polis)
        """)
        print("   ✓ GDC incompatibilities set: EXL ✗, Polis ✗")


def verify_compatibility(driver, database: str):
    """Verify the compatibility relationships."""

    print("\n" + "-" * 50)
    print("VERIFYING COMPATIBILITY MATRIX")
    print("-" * 50)

    with driver.session(database=database) as session:
        # Check what each product is compatible with
        result = session.run("""
            MATCH (pf:ProductFamily)
            WHERE pf.name CONTAINS 'GDB' OR pf.name CONTAINS 'GDMI' OR pf.name CONTAINS 'GDC' OR pf.name CONTAINS 'GDP'
            OPTIONAL MATCH (pf)-[:HAS_COMPATIBLE_ACCESSORY]->(acc:Accessory)
            OPTIONAL MATCH (pf)-[:INCOMPATIBLE_WITH]->(incomp:Accessory)
            WITH pf,
                 collect(DISTINCT acc.name) AS compatible,
                 collect(DISTINCT incomp.name) AS incompatible
            RETURN pf.name AS product,
                   compatible,
                   incompatible
            ORDER BY pf.name
        """)

        print("\n📋 Compatibility Matrix:")
        for record in result:
            product = record['product']
            compat = record['compatible'] or []
            incompat = record['incompatible'] or []
            print(f"\n   {product}:")
            print(f"      ✅ Compatible: {', '.join(compat) if compat else 'None'}")
            print(f"      ❌ Incompatible: {', '.join(incompat) if incompat else 'None'}")


def main():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    if not all([uri, user, password]):
        print("Error: Missing Neo4j connection environment variables")
        sys.exit(1)

    print("=" * 60)
    print("ACCESSORY COMPATIBILITY SCHEMA")
    print("=" * 60)

    print(f"\nConnecting to Neo4j at {uri}...")
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session(database=database) as session:
            result = session.run("RETURN 1 AS test")
            if result.single()["test"] != 1:
                raise Exception("Connection test failed")
        print("Connected successfully!")

        create_accessory_nodes(driver, database)
        create_compatibility_relationships(driver, database)
        verify_compatibility(driver, database)

        print("\n" + "=" * 60)
        print("COMPATIBILITY SCHEMA COMPLETE")
        print("=" * 60)
        print("\nThe system will now BLOCK incompatible configurations like GDC+EXL.")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
