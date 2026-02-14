#!/usr/bin/env python3
"""
Add Variable Features Schema to Neo4j

This script adds the HAS_VARIABLE_FEATURE relationships to product families,
enabling the "Variance Check Loop" that ensures all configurable features
are resolved before giving a final answer.

Run this script ONCE to add the variable features schema.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(dotenv_path="../.env")


def add_variable_features(driver, database: str):
    """Add variable features to GDB, GDMI, and GDC product families."""

    print("\n" + "=" * 60)
    print("ADDING VARIABLE FEATURES SCHEMA")
    print("=" * 60)

    with driver.session(database=database) as session:

        # =====================================================================
        # 1. CREATE HOUSING LENGTH FEATURE FOR GDB
        # =====================================================================
        print("\n📦 Adding Housing Length feature to GDB...")

        session.run("""
            // Find or create the GDB product family
            MATCH (gdb:ProductFamily)
            WHERE gdb.id = 'FAM_GDB' OR gdb.name CONTAINS 'GDB'

            // Create the Variable Feature node
            MERGE (feat_len:VariableFeature {id: 'FEAT_HOUSING_LENGTH_GDB'})
            SET feat_len.name = 'Housing Length',
                feat_len.is_variable = true,
                feat_len.applies_to = 'GDB',
                feat_len.description = 'Housing depth to accommodate different filter sizes'

            // Link feature to product family
            MERGE (gdb)-[:HAS_VARIABLE_FEATURE]->(feat_len)

            // Create Options
            MERGE (opt_short:FeatureOption {id: 'OPT_GDB_LEN_550'})
            SET opt_short.name = '550mm (Short)',
                opt_short.value = '550',
                opt_short.description = 'Short housing for bag filters up to 450mm depth',
                opt_short.filter_depth_max = 450

            MERGE (opt_long:FeatureOption {id: 'OPT_GDB_LEN_750'})
            SET opt_long.name = '750mm (Long)',
                opt_long.value = '750',
                opt_long.description = 'Long housing for bag filters up to 650mm depth',
                opt_long.filter_depth_max = 650,
                opt_long.is_default = true

            // Link options to feature
            MERGE (feat_len)-[:HAS_OPTION]->(opt_short)
            MERGE (feat_len)-[:HAS_OPTION]->(opt_long)

            // Create Discriminator (the question to ask)
            MERGE (disc:Discriminator {id: 'DISC_GDB_LENGTH'})
            SET disc.question = 'Which housing length is required?',
                disc.why_needed = 'Longer housing allows for larger filter surface area and lower pressure drop',
                disc.parameter_name = 'housing_length'

            MERGE (feat_len)-[:SELECTION_DEPENDS_ON]->(disc)
        """)
        print("   ✓ GDB housing length feature added")

        # =====================================================================
        # 2. CREATE HOUSING LENGTH FEATURE FOR GDMI
        # =====================================================================
        print("\n📦 Adding Housing Length feature to GDMI...")

        session.run("""
            MATCH (gdmi:ProductFamily)
            WHERE gdmi.id = 'FAM_GDMI' OR gdmi.name CONTAINS 'GDMI'

            MERGE (feat_len:VariableFeature {id: 'FEAT_HOUSING_LENGTH_GDMI'})
            SET feat_len.name = 'Housing Length',
                feat_len.is_variable = true,
                feat_len.applies_to = 'GDMI',
                feat_len.description = 'Insulated housing depth for different filter sizes'

            MERGE (gdmi)-[:HAS_VARIABLE_FEATURE]->(feat_len)

            MERGE (opt_short:FeatureOption {id: 'OPT_GDMI_LEN_600'})
            SET opt_short.name = '600mm (Short)',
                opt_short.value = '600',
                opt_short.description = 'Short insulated housing for filters up to 450mm'

            MERGE (opt_long:FeatureOption {id: 'OPT_GDMI_LEN_850'})
            SET opt_long.name = '850mm (Long)',
                opt_long.value = '850',
                opt_long.description = 'Long insulated housing for filters up to 650mm',
                opt_long.is_default = true

            MERGE (feat_len)-[:HAS_OPTION]->(opt_short)
            MERGE (feat_len)-[:HAS_OPTION]->(opt_long)

            MERGE (disc:Discriminator {id: 'DISC_GDMI_LENGTH'})
            SET disc.question = 'Which housing length is required?',
                disc.why_needed = 'Must match your filter depth for proper installation',
                disc.parameter_name = 'housing_length'

            MERGE (feat_len)-[:SELECTION_DEPENDS_ON]->(disc)
        """)
        print("   ✓ GDMI housing length feature added")

        # =====================================================================
        # 3. CREATE HOUSING LENGTH FEATURE FOR GDC
        # =====================================================================
        print("\n📦 Adding Housing Length feature to GDC...")

        session.run("""
            MATCH (gdc:ProductFamily)
            WHERE gdc.id = 'FAM_GDC' OR gdc.name CONTAINS 'GDC'

            MERGE (feat_len:VariableFeature {id: 'FEAT_HOUSING_LENGTH_GDC'})
            SET feat_len.name = 'Housing Length',
                feat_len.is_variable = true,
                feat_len.applies_to = 'GDC',
                feat_len.description = 'Carbon housing depth for different cylinder configurations'

            MERGE (gdc)-[:HAS_VARIABLE_FEATURE]->(feat_len)

            MERGE (opt_short:FeatureOption {id: 'OPT_GDC_LEN_750'})
            SET opt_short.name = '750mm',
                opt_short.value = '750',
                opt_short.description = 'Standard carbon housing for 300mm cylinders'

            MERGE (opt_long:FeatureOption {id: 'OPT_GDC_LEN_900'})
            SET opt_long.name = '900mm',
                opt_long.value = '900',
                opt_long.description = 'Extended carbon housing for 450mm cylinders + polishing filter'

            MERGE (feat_len)-[:HAS_OPTION]->(opt_short)
            MERGE (feat_len)-[:HAS_OPTION]->(opt_long)

            MERGE (disc:Discriminator {id: 'DISC_GDC_LENGTH'})
            SET disc.question = 'Which housing length is required?',
                disc.why_needed = 'Depends on carbon cylinder depth and whether polishing filter is needed',
                disc.parameter_name = 'housing_length'

            MERGE (feat_len)-[:SELECTION_DEPENDS_ON]->(disc)
        """)
        print("   ✓ GDC housing length feature added")

        # =====================================================================
        # 4. VERIFY THE SCHEMA
        # =====================================================================
        print("\n🔍 Verifying schema...")

        result = session.run("""
            MATCH (pf:ProductFamily)-[:HAS_VARIABLE_FEATURE]->(f:VariableFeature)-[:HAS_OPTION]->(o:FeatureOption)
            RETURN pf.name AS product_family,
                   f.name AS feature,
                   collect(o.name) AS options
            ORDER BY pf.name
        """)

        for record in result:
            print(f"   {record['product_family']}: {record['feature']} → {record['options']}")


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
        with driver.session(database=database) as session:
            result = session.run("RETURN 1 AS test")
            if result.single()["test"] != 1:
                raise Exception("Connection test failed")
        print("Connected successfully!")

        add_variable_features(driver, database)

        print("\n" + "=" * 60)
        print("SCHEMA UPDATE COMPLETE")
        print("=" * 60)
        print("\nThe system will now ask about housing length before")
        print("giving a final recommendation for GDB/GDMI/GDC products.")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
