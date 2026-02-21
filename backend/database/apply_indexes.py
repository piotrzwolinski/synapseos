#!/usr/bin/env python3
"""Apply FalkorDB indexes for performance optimization."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from database import db


def apply_indexes():
    """Apply all fulltext, vector, and range indexes."""
    graph = db.connect()

    # Fulltext indexes (FalkorDB syntax)
    fulltext_indexes = [
        ('ProductVariant', ['name', 'family', 'options_json']),
        ('FilterConsumable', ['part_number', 'model_name', 'filter_type']),
        ('MaterialSpecification', ['code', 'full_name', 'name', 'description']),
        ('Concept', ['name', 'description', 'text']),
        ('Keyword', ['name']),
    ]

    # Range indexes (FalkorDB syntax: CREATE INDEX FOR (n:Label) ON (n.prop))
    range_indexes = [
        ('ProductVariant', 'name'),
        ('ProductFamily', 'id'),
        ('ProductFamily', 'name'),
        ('Material', 'code'),
        ('Application', 'id'),
        ('Application', 'name'),
        ('Option', 'code'),
        ('VariableFeature', 'id'),
        ('Environment', 'id'),
        ('Environment', 'name'),
        ('DimensionModule', 'width'),
        ('DimensionModule', 'height'),
        ('Trait', 'name'),
        ('Stressor', 'name'),
        ('CausalRule', 'id'),
        ('CapacityRule', 'id'),
        ('InstallationConstraint', 'id'),
        ('SizeProperty', 'id'),
    ]

    print("Applying fulltext indexes...")
    for label, properties in fulltext_indexes:
        props_str = ', '.join(f"'{p}'" for p in properties)
        query = f"CALL db.idx.fulltext.createNodeIndex('{label}', {props_str})"
        try:
            graph.query(query)
            print(f"  + {label}[{', '.join(properties)}]")
        except Exception as e:
            err = str(e)
            if 'already indexed' in err.lower() or 'already exists' in err.lower():
                print(f"  = {label}[{', '.join(properties)}] (already exists)")
            else:
                print(f"  x {label}: {e}")

    print("\nApplying range indexes...")
    for label, prop in range_indexes:
        query = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
        try:
            graph.query(query)
            print(f"  + {label}.{prop}")
        except Exception as e:
            err = str(e)
            if 'already indexed' in err.lower() or 'already exists' in err.lower():
                print(f"  = {label}.{prop} (already exists)")
            else:
                print(f"  x {label}.{prop}: {e}")

    # Vector indexes (for semantic search)
    vector_indexes = [
        ('Concept', 'embedding', 3072),
        ('Keyword', 'embedding', 3072),
        ('Application', 'embedding', 3072),
    ]

    print("\nApplying vector indexes...")
    for label, prop, dim in vector_indexes:
        query = (
            f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.{prop}) "
            f"OPTIONS {{dimension: {dim}, similarityFunction: 'cosine'}}"
        )
        try:
            graph.query(query)
            print(f"  + {label}.{prop} (dim={dim})")
        except Exception as e:
            err = str(e)
            if 'already indexed' in err.lower() or 'already exists' in err.lower():
                print(f"  = {label}.{prop} (already exists)")
            else:
                print(f"  x {label}.{prop}: {e}")

    print("\nDone!")


if __name__ == "__main__":
    apply_indexes()
