#!/usr/bin/env python3
"""Fix: Polis after-filter rail leaking into GDC-FLEX housing-length clarification.

ROOT CAUSE
----------
A malformed `VariableFeature` node (parameter_name = NULL, feature_name = NULL)
was shared by FAM_GDC and FAM_GDC_FLEX and linked `[OPT_GDC_LEN_750,
OPT_GDC_LEN_900, OPT_POLIS]` via HAS_OPTION. Because its parameter_name is NULL,
`check_variable_features` computes an empty param_key that never matches a
resolved param, so it ALWAYS surfaced as an unresolved clarification — dragging
`OPT_POLIS` (an after-filter rail) into the housing-length option list.

Worse: `ACC_POLIS` is `INCOMPATIBLE_WITH` FAM_GDC and FAM_GDC_FLEX (it is only
HAS_COMPATIBLE_ACCESSORY with GDB/GDMI). So Polis was being offered exactly for
the families it is incompatible with, while GDB/GDMI (where it is valid) never
had it as a selectable option.

FIX
---
1. Add a proper housing_length VariableFeature for FAM_GDC_FLEX (it had none of
   its own — it depended entirely on the malformed shared node), linking the two
   real length options 750/900.
2. Copy the geometric constraint (min_required_housing_length=900 + physics text)
   from OPT_POLIS onto ACC_POLIS, so the constraint lives on the accessory (the
   canonical Polis representation) and is reachable via the accessory path.
3. Delete the malformed shared node (the VariableFeature that HAS_OPTION
   OPT_POLIS). This removes Polis from GDC/GDC_FLEX clarifications and removes the
   duplicate length feature for GDC (which keeps its proper VF_GDC_LENGTH).

Idempotent: safe to re-run.

NOTE (out of scope): a sibling malformed node exists for FAM_GDMI (NULL identity,
links GDMI length options, no Polis). It does not cause the Polis bug and is left
untouched here.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from db_result_helpers import result_to_dicts, result_single


def run(query, params=None):
    graph = db.connect()
    return graph.query(query, params or {})


def fix():
    # ── Step 1: proper housing_length feature for FAM_GDC_FLEX ────────────────
    result = run("""
        MATCH (pf:ProductFamily {id: 'FAM_GDC_FLEX'})
        MERGE (f:VariableFeature {id: 'VF_GDC_FLEX_LENGTH'})
          SET f.applies_to     = 'GDC_FLEX',
              f.feature_name    = 'Housing Length',
              f.parameter_name  = 'housing_length',
              f.is_variable     = true,
              f.question        = 'Which housing length do you need?',
              f.why_needed      = 'GDC FLEX carbon housings come in 750mm (for 450mm cylinders) or 900mm (for 600mm cylinders).'
        MERGE (pf)-[:HAS_VARIABLE_FEATURE]->(f)
        WITH f
        MATCH (o750:FeatureOption {id: 'OPT_GDC_LEN_750'})
        MATCH (o900:FeatureOption {id: 'OPT_GDC_LEN_900'})
        MERGE (f)-[:HAS_OPTION]->(o750)
        MERGE (f)-[:HAS_OPTION]->(o900)
        RETURN f.id AS fid
    """)
    row = result_single(result)
    print(f"[OK] Step 1: FAM_GDC_FLEX housing_length feature -> {row['fid'] if row else 'FAILED'}")

    # ── Step 2: move geometric constraint onto ACC_POLIS ──────────────────────
    result = run("""
        MATCH (opt:FeatureOption {id: 'OPT_POLIS'})
        MATCH (acc:Accessory {id: 'ACC_POLIS'})
        SET acc.min_required_housing_length = COALESCE(opt.min_required_housing_length, acc.min_housing_length, 900),
            acc.physics_logic = COALESCE(opt.physics_logic, acc.physics_logic),
            acc.value = COALESCE(acc.value, opt.value, 'polis')
        RETURN acc.id AS id, acc.min_required_housing_length AS min_len
    """)
    row = result_single(result)
    if row:
        print(f"[OK] Step 2: ACC_POLIS.min_required_housing_length = {row['min_len']}")
    else:
        print("[WARN] Step 2: OPT_POLIS or ACC_POLIS not found — constraint not copied")

    # ── Step 3: delete the malformed VariableFeature that carries OPT_POLIS ────
    # Identify it structurally (NULL param_name + HAS_OPTION OPT_POLIS) so we do
    # not depend on unstable internal node ids.
    result = run("""
        MATCH (f:VariableFeature)-[:HAS_OPTION]->(:FeatureOption {id: 'OPT_POLIS'})
        WHERE f.parameter_name IS NULL
        WITH f, id(f) AS nid
        DETACH DELETE f
        RETURN nid
    """)
    deleted = [r['nid'] for r in result_to_dicts(result)]
    print(f"[OK] Step 3: deleted malformed VariableFeature node(s): {deleted or 'none (already clean)'}")

    print("\n[DONE] Polis length-clarification defect fixed.")


if __name__ == "__main__":
    fix()
