#!/usr/bin/env python3
"""Apply Neo4j indexes for performance optimization."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neo4j import GraphDatabase

# Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "testpassword")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def apply_indexes():
    """Apply all fulltext and b-tree indexes."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    # Fulltext indexes for CONTAINS queries (critical for performance)
    fulltext_indexes = [
        # ProductVariant fulltext index (config_search was 6.48s)
        ('product_variant_fulltext', 'ProductVariant', ['name', 'family', 'options_json']),
        # FilterCartridge fulltext index
        ('filter_cartridge_fulltext', 'FilterCartridge', ['name', 'model_name']),
        # FilterConsumable fulltext index
        ('filter_consumable_fulltext', 'FilterConsumable', ['part_number', 'model_name', 'filter_type']),
        # MaterialSpecification fulltext index
        ('material_spec_fulltext', 'MaterialSpecification', ['code', 'full_name', 'name', 'description']),
        # Project fulltext index (project_search was 4.28s)
        ('project_fulltext', 'Project', ['name']),
        # Concept fulltext index (for hybrid retrieval)
        ('concept_fulltext', 'Concept', ['name', 'description', 'text']),
        # Keyword fulltext index
        ('keyword_fulltext', 'Keyword', ['name']),
    ]

    # B-tree indexes for exact lookups
    btree_indexes = [
        ('product_variant_name', 'ProductVariant', 'name'),
        ('product_family_id', 'ProductFamily', 'id'),
        ('product_family_name', 'ProductFamily', 'name'),
        ('material_code', 'Material', 'code'),
        ('application_id', 'Application', 'id'),
        ('application_name', 'Application', 'name'),
        ('option_code', 'Option', 'code'),
        ('variable_feature_id', 'VariableFeature', 'id'),
        ('project_name', 'Project', 'name'),
    ]

    with driver.session(database=NEO4J_DATABASE) as session:
        print("Applying fulltext indexes...")
        for idx_name, label, properties in fulltext_indexes:
            props_str = ', '.join([f'n.{p}' for p in properties])
            query = f"""
                CREATE FULLTEXT INDEX {idx_name} IF NOT EXISTS
                FOR (n:{label}) ON EACH [{props_str}]
            """
            try:
                session.run(query)
                print(f"  ✓ {idx_name} on {label}[{', '.join(properties)}]")
            except Exception as e:
                print(f"  ✗ {idx_name}: {e}")

        print("\nApplying b-tree indexes...")
        for idx_name, label, prop in btree_indexes:
            query = f"""
                CREATE INDEX {idx_name} IF NOT EXISTS FOR (n:{label}) ON (n.{prop})
            """
            try:
                session.run(query)
                print(f"  ✓ {idx_name} on {label}.{prop}")
            except Exception as e:
                print(f"  ✗ {idx_name}: {e}")

        print("\nListing all indexes:")
        result = session.run("SHOW INDEXES")
        for record in result:
            print(f"  - {record['name']}: {record['labelsOrTypes']} state={record['state']}")

    driver.close()
    print("\nDone! Indexes applied successfully.")


if __name__ == "__main__":
    apply_indexes()
