#!/usr/bin/env python3
"""
Add Physics-Based Mitigation Schema to Neo4j

This script creates the domain model for physics-based risk mitigation:
- Environment nodes (contexts that cause risks)
- Risk nodes (physical phenomena like Condensation)
- Feature nodes (mitigations like Insulation)
- Relationships that encode the physics logic

The key principle: If a Context CAUSES a Risk that is MITIGATED_BY a Feature,
and the Product lacks that Feature -> BLOCK the configuration.

This moves physics logic FROM the LLM (unreliable) TO the Graph (authoritative).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(dotenv_path="../.env")


def create_environment_nodes(driver, database: str):
    """Create Environment context nodes."""

    print("\n" + "-" * 50)
    print("CREATING ENVIRONMENT NODES")
    print("-" * 50)

    with driver.session(database=database) as session:
        # Outdoor Environment
        print("\n🌤️ Creating Outdoor environment...")
        session.run("""
            MERGE (env:Environment {id: 'ENV_OUTDOOR'})
            SET env.name = 'Outdoor Installation',
                env.description = 'Equipment installed outside, exposed to weather and temperature variations',
                env.keywords = ['outdoor', 'roof', 'rooftop', 'dach', 'zewnątrz', 'outside', 'exterior'],
                env.temperature_variation = 'High',
                env.humidity_exposure = 'Variable'
        """)

        # Indoor Environment (for contrast)
        print("🏢 Creating Indoor environment...")
        session.run("""
            MERGE (env:Environment {id: 'ENV_INDOOR'})
            SET env.name = 'Indoor Installation',
                env.description = 'Equipment installed inside climate-controlled spaces',
                env.keywords = ['indoor', 'inside', 'interior', 'wewnątrz', 'office', 'factory'],
                env.temperature_variation = 'Low',
                env.humidity_exposure = 'Controlled'
        """)

        print("   ✓ Environment nodes created")


def create_risk_nodes(driver, database: str):
    """Create Risk nodes representing physical phenomena."""

    print("\n" + "-" * 50)
    print("CREATING RISK NODES (PHYSICS)")
    print("-" * 50)

    with driver.session(database=database) as session:
        # Condensation Risk
        print("\n💧 Creating Condensation risk...")
        session.run("""
            MERGE (risk:Risk {id: 'RISK_COND'})
            SET risk.name = 'Condensation / Dew Point',
                risk.severity = 'CRITICAL',
                risk.category = 'Thermodynamics',
                risk.physics_explanation = 'When warm, humid air contacts a cold metal surface, ' +
                    'water vapor condenses into liquid water. This occurs when the surface temperature ' +
                    'drops below the dew point of the air. Warmer air actually INCREASES this risk ' +
                    'because it can hold more moisture, leading to greater condensation when cooled.',
                risk.consequence = 'Water accumulation inside housing causes filter damage, ' +
                    'accelerated corrosion, mold growth, and potential equipment failure',
                risk.user_misconception = 'Users often think warm air is safe, but warm air ' +
                    'holds MORE moisture and causes MORE condensation on cold surfaces'
        """)

        # Corrosion Risk (already exists, enhance it)
        print("🔩 Creating/enhancing Corrosion risk...")
        session.run("""
            MERGE (risk:Risk {id: 'RISK_CORR'})
            SET risk.name = 'Corrosion',
                risk.severity = 'WARNING',
                risk.category = 'Chemistry',
                risk.physics_explanation = 'Metal oxidation accelerated by moisture, ' +
                    'chemicals, or salt exposure. Different materials have different ' +
                    'corrosion resistance classes (C1-C5).',
                risk.consequence = 'Structural degradation, air leaks, shortened equipment lifespan'
        """)

        print("   ✓ Risk nodes created")


def create_feature_nodes(driver, database: str):
    """Create Feature nodes representing mitigations."""

    print("\n" + "-" * 50)
    print("CREATING FEATURE NODES (MITIGATIONS)")
    print("-" * 50)

    with driver.session(database=database) as session:
        # Thermal Insulation Feature
        print("\n🧱 Creating Thermal Insulation feature...")
        session.run("""
            MERGE (feat:Feature {id: 'FEAT_INSUL'})
            SET feat.name = 'Thermal Insulation',
                feat.description = 'Thermal break layer that prevents temperature differential ' +
                    'between internal air and external casing',
                feat.physics_function = 'Maintains surface temperature above dew point, ' +
                    'preventing condensation formation',
                feat.typical_material = 'Mineral wool, polyurethane foam',
                feat.thickness_mm = '25-50'
        """)

        # Corrosion Resistant Material Feature
        print("🛡️ Creating Corrosion Resistance feature...")
        session.run("""
            MERGE (feat:Feature {id: 'FEAT_CORR_RES'})
            SET feat.name = 'Corrosion Resistant Material',
                feat.description = 'Material with high corrosion class rating (C4/C5)',
                feat.physics_function = 'Passive oxide layer or noble metal prevents oxidation',
                feat.examples = 'Stainless Steel (RF), Aluminum (AL)'
        """)

        print("   ✓ Feature nodes created")


def create_physics_relationships(driver, database: str):
    """Create relationships encoding physics logic."""

    print("\n" + "-" * 50)
    print("CREATING PHYSICS RELATIONSHIPS")
    print("-" * 50)

    with driver.session(database=database) as session:
        # Environment CAUSES Risk
        print("\n🔗 Linking Outdoor -> Condensation (CAUSES)...")
        session.run("""
            MATCH (env:Environment {id: 'ENV_OUTDOOR'})
            MATCH (risk:Risk {id: 'RISK_COND'})
            MERGE (env)-[r:CAUSES]->(risk)
            SET r.certainty = 'High',
                r.note = 'Temperature differential between outdoor air and casing is inevitable',
                r.physics_basis = 'Second Law of Thermodynamics - heat flows from hot to cold'
        """)

        # Risk MITIGATED_BY Feature
        print("🔗 Linking Condensation -> Insulation (MITIGATED_BY)...")
        session.run("""
            MATCH (risk:Risk {id: 'RISK_COND'})
            MATCH (feat:Feature {id: 'FEAT_INSUL'})
            MERGE (risk)-[r:MITIGATED_BY]->(feat)
            SET r.mechanism = 'Insulation maintains casing temperature above dew point',
                r.effectiveness = 'High',
                r.mandatory = true
        """)

        print("🔗 Linking Corrosion -> Corrosion Resistance (MITIGATED_BY)...")
        session.run("""
            MATCH (risk:Risk {id: 'RISK_CORR'})
            MATCH (feat:Feature {id: 'FEAT_CORR_RES'})
            MERGE (risk)-[r:MITIGATED_BY]->(feat)
            SET r.mechanism = 'Resistant material prevents oxidation',
                r.effectiveness = 'High'
        """)

        print("   ✓ Physics relationships created")


def link_products_to_features(driver, database: str):
    """Link products to their features (HAS_FEATURE)."""

    print("\n" + "-" * 50)
    print("LINKING PRODUCTS TO FEATURES")
    print("-" * 50)

    with driver.session(database=database) as session:
        # GDMI HAS Thermal Insulation
        print("\n🔗 Linking GDMI -> Thermal Insulation...")
        session.run("""
            MATCH (gdmi:ProductFamily)
            WHERE gdmi.id = 'FAM_GDMI' OR gdmi.name CONTAINS 'GDMI'
            MATCH (feat:Feature {id: 'FEAT_INSUL'})
            MERGE (gdmi)-[r:HAS_FEATURE]->(feat)
            SET r.standard = true,
                r.note = 'GDMI is the insulated variant of modular filter housings'
        """)
        print("   ✓ GDMI has Thermal Insulation")

        # GDB does NOT have Thermal Insulation (no relationship = no feature)
        print("⚠️ GDB does NOT have Thermal Insulation (no relationship)")

        # GDC does NOT have Thermal Insulation
        print("⚠️ GDC does NOT have Thermal Insulation (no relationship)")

        # GDP does NOT have Thermal Insulation
        print("⚠️ GDP does NOT have Thermal Insulation (no relationship)")

        # Also link product vulnerabilities
        print("\n🔗 Linking non-insulated products -> Condensation vulnerability...")
        session.run("""
            MATCH (pf:ProductFamily)
            WHERE pf.id IN ['FAM_GDB', 'FAM_GDC', 'FAM_GDP']
               OR pf.name CONTAINS 'GDB Kanalfilterskåp'
               OR pf.name CONTAINS 'GDC'
               OR pf.name CONTAINS 'GDP'
            MATCH (risk:Risk {id: 'RISK_COND'})
            MERGE (pf)-[r:VULNERABLE_TO]->(risk)
            SET r.reason = 'Non-insulated housing - no thermal break',
                r.context = 'Outdoor installations'
        """)
        print("   ✓ GDB, GDC, GDP marked as VULNERABLE_TO Condensation")

        # GDMI PROTECTS_AGAINST Condensation
        print("\n🔗 Linking GDMI -> PROTECTS_AGAINST Condensation...")
        session.run("""
            MATCH (gdmi:ProductFamily)
            WHERE gdmi.id = 'FAM_GDMI' OR gdmi.name CONTAINS 'GDMI'
            MATCH (risk:Risk {id: 'RISK_COND'})
            MERGE (gdmi)-[r:PROTECTS_AGAINST]->(risk)
            SET r.mechanism = 'Built-in thermal insulation maintains surface temperature',
                r.effectiveness = 'High'
        """)
        print("   ✓ GDMI PROTECTS_AGAINST Condensation")


def verify_physics_model(driver, database: str):
    """Verify the physics model is correctly set up."""

    print("\n" + "-" * 50)
    print("VERIFYING PHYSICS MODEL")
    print("-" * 50)

    with driver.session(database=database) as session:
        # Test the unmitigated risk query
        print("\n📋 Testing Unmitigated Risk Query for GDB + Outdoor...")
        result = session.run("""
            MATCH (env:Environment {id: 'ENV_OUTDOOR'})
            MATCH (env)-[:CAUSES]->(risk:Risk)
            MATCH (prod:ProductFamily)
            WHERE prod.id = 'FAM_GDB' OR prod.name CONTAINS 'GDB Kanalfilterskåp'

            // Check for mitigation via feature
            OPTIONAL MATCH (prod)-[:HAS_FEATURE]->(feat:Feature)<-[:MITIGATED_BY]-(risk)
            // Check for direct protection
            OPTIONAL MATCH (prod)-[protects:PROTECTS_AGAINST]->(risk)

            // Only return if NO mitigation exists
            WITH env, risk, prod, feat, protects
            WHERE feat IS NULL AND protects IS NULL

            RETURN risk.name AS risk_name,
                   risk.severity AS severity,
                   risk.physics_explanation AS physics,
                   prod.name AS product
            LIMIT 1
        """)

        record = result.single()
        if record:
            print(f"   ✅ Unmitigated Risk Detected:")
            print(f"      Product: {record['product']}")
            print(f"      Risk: {record['risk_name']} ({record['severity']})")
            print(f"      Physics: {record['physics'][:80]}...")
        else:
            print("   ⚠️ No unmitigated risk found (check relationships)")

        # Test that GDMI is safe
        print("\n📋 Testing Unmitigated Risk Query for GDMI + Outdoor...")
        result2 = session.run("""
            MATCH (env:Environment {id: 'ENV_OUTDOOR'})
            MATCH (env)-[:CAUSES]->(risk:Risk)
            MATCH (prod:ProductFamily)
            WHERE prod.id = 'FAM_GDMI' OR prod.name CONTAINS 'GDMI'

            // Check for mitigation via feature
            OPTIONAL MATCH (prod)-[:HAS_FEATURE]->(feat:Feature)<-[:MITIGATED_BY]-(risk)
            // Check for direct protection
            OPTIONAL MATCH (prod)-[protects:PROTECTS_AGAINST]->(risk)

            // Only return if NO mitigation exists
            WITH risk, prod, feat, protects
            WHERE feat IS NULL AND protects IS NULL

            RETURN risk.name AS risk_name
            LIMIT 1
        """)

        record2 = result2.single()
        if record2:
            print(f"   ❌ GDMI shows unmitigated risk: {record2['risk_name']} (BUG!)")
        else:
            print("   ✅ GDMI has no unmitigated risks (correctly protected)")

        # Show the mitigation path
        print("\n📋 Mitigation Path:")
        result3 = session.run("""
            MATCH (env:Environment {id: 'ENV_OUTDOOR'})-[:CAUSES]->(risk:Risk)
            MATCH (risk)-[:MITIGATED_BY]->(feat:Feature)
            MATCH (prod:ProductFamily)-[:HAS_FEATURE]->(feat)
            RETURN env.name AS context,
                   risk.name AS risk,
                   feat.name AS mitigation,
                   prod.name AS safe_product
        """)
        for record in result3:
            print(f"   {record['context']} -> {record['risk']} -> {record['mitigation']} -> {record['safe_product']}")


def main():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    if not all([uri, user, password]):
        print("Error: Missing Neo4j connection environment variables")
        sys.exit(1)

    print("=" * 60)
    print("PHYSICS-BASED MITIGATION SCHEMA")
    print("=" * 60)
    print("\nThis creates the Domain Model for physics-based risk mitigation.")
    print("Logic moves FROM the LLM (unreliable) TO the Graph (authoritative).")

    print(f"\nConnecting to Neo4j at {uri}...")
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session(database=database) as session:
            result = session.run("RETURN 1 AS test")
            if result.single()["test"] != 1:
                raise Exception("Connection test failed")
        print("Connected successfully!")

        create_environment_nodes(driver, database)
        create_risk_nodes(driver, database)
        create_feature_nodes(driver, database)
        create_physics_relationships(driver, database)
        link_products_to_features(driver, database)
        verify_physics_model(driver, database)

        print("\n" + "=" * 60)
        print("PHYSICS SCHEMA COMPLETE")
        print("=" * 60)
        print("\n✅ Environment -> CAUSES -> Risk")
        print("✅ Risk -> MITIGATED_BY -> Feature")
        print("✅ Product -> HAS_FEATURE -> Feature")
        print("✅ Product -> VULNERABLE_TO / PROTECTS_AGAINST -> Risk")
        print("\nThe system will now BLOCK configurations with unmitigated physics risks.")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
