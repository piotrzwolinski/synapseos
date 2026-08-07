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
    """Add geometric constraint for the Polis after-filter rail.

    MODELING RULE: Polis is an ACCESSORY (ACC_POLIS), NOT a housing-length
    option. The geometric constraint (min 900mm) lives on the Accessory node
    and is read via the HAS_COMPATIBLE_ACCESSORY path in
    database.get_option_geometric_constraints. Polis must NEVER be linked to a
    housing_length VariableFeature via HAS_OPTION — that pollutes the
    length-selection clarification with a non-length item (see
    database/fix_polis_length_feature.py for the repair migration).
    """
    graph = db.connect()

    # Step 1: Put the geometric constraint on the Polis ACCESSORY node.
    result = graph.query("""
        MERGE (a:Accessory {id: "ACC_POLIS"})
        SET a.name = "Polis",
            a.value = "polis",
            a.min_required_housing_length = 900,
            a.min_housing_length = 900,
            a.physics_logic = "The after-filter rail (Polis) requires extra internal depth to accommodate the secondary filter stage. This additional space is only available in the 900/950mm housing variants."
        RETURN a.id AS id, a.min_required_housing_length AS min_length
    """)
    row = result_single(result)
    if row:
        print(f"[OK] Set geometric constraint on accessory {row['id']}: min_length={row['min_length']}mm")

    print("\n[DONE] Geometric constraint for Polis applied to ACC_POLIS.")
    print("       The Physical Constraint Validator reads it via the accessory")
    print("       path and blocks Polis on compatible families (GDB/GDMI) below 900mm.")
    print("       Polis is NOT added as a housing-length option (that was the bug).")


if __name__ == "__main__":
    apply_polis_constraint()
