#!/usr/bin/env python3
"""Apply geometric constraint updates to the graph database.

This script adds the `min_required_housing_length` property to option nodes
that have physical space requirements, enabling the Physical Constraint Validator.

Source: PDF Catalog Page 14 - Polis after-filter rail requires 900mm housing.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from db_result_helpers import result_to_dicts, result_single


def apply_polis_constraint():
    """Add geometric constraint for Polis after-filter option."""
    graph = db.connect()

    # Step 1: Create/update Polis option with geometric constraint
    result = graph.query("""
        MERGE (o:FeatureOption {id: "OPT_POLIS"})
        SET o.name = "Polis",
            o.value = "polis",
            o.display_label = "Polis (After-filter Rail)",
            o.description = "Secondary polishing filter stage for enhanced air quality",
            o.min_required_housing_length = 900,
            o.physics_logic = "The after-filter rail (Polis) requires extra internal depth to accommodate the secondary filter stage. This additional space is only available in the 900/950mm housing variants.",
            o.use_case = "High air quality requirements, cleanroom adjacent spaces",
            o.benefit = "Additional filtration stage for polishing air after primary carbon treatment"
        RETURN o.id AS id, o.min_required_housing_length AS min_length
    """)
    row = result_single(result)
    if row:
        print(f"[OK] Created/updated Polis option: {row['id']} with min_length={row['min_length']}mm")

    # Step 2: Link to GDC housing length feature
    result = graph.query("""
        MATCH (pf:ProductFamily)
        WHERE pf.id = "FAM_GDC" OR pf.name = "GDC"
        MATCH (pf)-[:HAS_VARIABLE_FEATURE]->(f:VariableFeature)
        WHERE f.parameter_name CONTAINS "length" OR f.feature_name CONTAINS "Length"
        MATCH (o:FeatureOption {id: "OPT_POLIS"})
        MERGE (f)-[:HAS_OPTION]->(o)
        RETURN pf.name AS family, f.feature_name AS feature
    """)
    for row in result_to_dicts(result):
        print(f"[OK] Linked Polis to {row['family']} -> {row['feature']}")

    # Step 3: Set incompatibility with 750mm
    result = graph.query("""
        MATCH (o:FeatureOption {id: "OPT_POLIS"})
        MATCH (v:FeatureOption)
        WHERE (v.value = "750" OR v.value = "550" OR v.value = "600")
          AND (v.id CONTAINS "LENGTH" OR v.id CONTAINS "length")
        MERGE (o)-[r:INCOMPATIBLE_WITH_VARIANT]->(v)
        SET r.reason = "Insufficient internal depth for after-filter rail"
        RETURN o.name AS opt, v.value AS variant
    """)
    incompatible = result_to_dicts(result)
    if incompatible:
        for row in incompatible:
            print(f"[OK] Set incompatibility: {row['opt']} <-> {row['variant']}mm variant")
    else:
        print("[INFO] No existing length variants found to mark as incompatible")

    print("\n[DONE] Geometric constraint for Polis option applied successfully!")
    print("       The Physical Constraint Validator will now block configurations")
    print("       where Polis is requested with space limits under 900mm.")


if __name__ == "__main__":
    apply_polis_constraint()
