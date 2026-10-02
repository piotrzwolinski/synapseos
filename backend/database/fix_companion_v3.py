#!/usr/bin/env python3
"""Align Layer 1 data with the M+H Filter-Housing Selection Companion V3.

Source: "Filter Housing Selection Companion V3.docx" + Alexander Söderblom's
answers (2026-10): GDMI long = 850, short-housing max filter depth = 450,
GDMI material = ZM (no stainless, aluminium framing).

This migration (idempotent, MERGE/SET/DELETE-edge only — never touches Layer 4):
  1. GDMI + GDMI FLEX default material FZ -> ZM (Companion §2.3).
  2. GDMI FLEX: drop the FZ material edge — AZ and ZM only (§2.2).
  3. GDMI FLEX: it is an insulated CARTRIDGE housing, not a bag housing (§5.6).
  4. GDMI: remove ENV_HOSPITAL / ENV_PHARMACEUTICAL (node note already said
     REMOVED; §10 forbids committing to HEPA/pharma duty).
  5. SF corrosion class "C5.1" -> "C5-I" (§2.1: brochure typeface misprint).
  6. GDC FLEX: pull-out cartridge plate, not "rail-mounted" (§5.5).
  7. Close resolved source conflicts; drop unverified "Leakage Class L1" notes (§3.1, §10).

Run:      cd backend && python database/fix_companion_v3.py
Emit sh:  cd backend && python database/fix_companion_v3.py --emit-sh ../deploy/fix_companion_v3.sh
"""
import os
import sys

from falkordb import FalkorDB

SRC = "M+H Selection Companion V3 (2026-10)"

STATEMENTS = [
    # 1. Default materials
    "MATCH (pf:ProductFamily) WHERE pf.id IN ['FAM_GDMI', 'FAM_GDMI_FLEX'] "
    f"SET pf.default_material = 'ZM', pf.default_material_source = '{SRC}'",
    # 2. GDMI FLEX materials: AZ + ZM only
    "MATCH (:ProductFamily {id: 'FAM_GDMI_FLEX'})-[r:AVAILABLE_IN_MATERIAL]->(:Material {id: 'MAT_FZ'}) DELETE r",
    "MATCH (pf:ProductFamily {id: 'FAM_GDMI_FLEX'}) SET pf.available_materials = ['AZ', 'ZM'], "
    "pf.material_exclusions = ['FZ', 'RF', 'SF'], "
    "pf.material_exclusion_note = 'AZ and ZM only. Ej i rostfritt (aluminium-profile frame).'",
    # 3. GDMI FLEX is a cartridge housing
    "MATCH (pf:ProductFamily {id: 'FAM_GDMI_FLEX'}) SET "
    "pf.filter_type = 'cartridge', pf.media_type = 'activated_carbon_chemical', "
    "pf.desc = 'Insulated carbon cartridge housing with pull-out cartridge plate', "
    "pf.description = 'Insulated (heat + condensation) double-wall cartridge filter cabinet with "
    "aluminium-profile frame and pull-out cartridge plate. For ACTIVATED CARBON and CHEMICAL MEDIA "
    "cartridges (gas-phase / molecular filtration). Lengths 850mm (450mm cylinder) and 1100mm "
    "(600mm cylinder + downstream post carbon filter). Indoor use.', "
    "pf.filter_depth_note = 'Skap 850/900mm: 450mm cylinder. Skap 1100/1150mm: 600mm cylinder + polisfilter.', "
    "pf.max_filter_depth_short_mm = 450, pf.max_filter_depth_long_mm = 600, "
    "pf.service_warning = 'Pull-out cartridge plate: requires front clearance for the extracted plate.'",
    # 4. GDMI environments
    "MATCH (pf:ProductFamily {id: 'FAM_GDMI'}) SET pf.allowed_environments = "
    "[e IN pf.allowed_environments WHERE NOT e IN ['ENV_HOSPITAL', 'ENV_PHARMACEUTICAL']]",
    # 5. SF corrosion class spelling
    "MATCH (m) WHERE (m:Material OR m:MaterialSpecification) AND m.corrosion_class = 'C5.1' "
    "SET m.corrosion_class = 'C5-I'",
    "MATCH (n) WHERE n.corrosion_class = 'C5.1' SET n.corrosion_class = 'C5-I'",
    "MATCH (n) WHERE n.min_corrosion_class = 'C5.1' SET n.min_corrosion_class = 'C5-I'",
    "MATCH (n) WHERE n.id IN ['REQ_C5M', 'TRAIT_CORROSION_RESISTANCE_C5M'] "
    "SET n.name = replace(n.name, 'C5.1', 'C5-I'), "
    "n.description = CASE WHEN n.description IS NULL THEN NULL ELSE replace(n.description, 'C5.1', 'C5-I') END",
    # 6. GDC FLEX wording
    "MATCH (pf:ProductFamily {id: 'FAM_GDC_FLEX'}) SET "
    "pf.desc = 'Carbon cartridge housing with pull-out cartridge plate', "
    "pf.description = 'Cartridge filter cabinet with pull-out cartridge plate for easy service in "
    "confined rooms. For ACTIVATED CARBON and CHEMICAL MEDIA cartridges. Same duty and cartridges as "
    "GDC. Lengths 750mm (450mm cylinder) and 900mm (600mm cylinder, or 450mm cylinder + post carbon "
    "filter).'",
    # 7. Resolved conflicts + unverified notes
    "MATCH (pf:ProductFamily {id: 'FAM_GDMI'}) SET pf.source_conflicts = "
    "['RESOLVED by M+H 2026-10: lengths 600/850 per tables (brochure text 550/800 is wrong); "
    "default material ZM (example code AZ is also valid).'], "
    "pf.hospital_approval_note = 'Not offered for hospital/pharma/HEPA duty: housings are rated up to "
    "F9 per VVS AMA QGB/1 (general ventilation). Route to specialist review.'",
    "MATCH (pf:ProductFamily) WHERE pf.construction_type_note CONTAINS 'Leakage Class L1' "
    "SET pf.construction_type_note = 'Tested to EN 15727:2010 and EN 1886:2007. No numeric leakage "
    "class (A-D / L1-L3) is stated by the brochure - do not assign one.'",
]

VERIFY = [
    "MATCH (pf:ProductFamily) WHERE pf.id IN ['FAM_GDMI','FAM_GDMI_FLEX','FAM_GDC_FLEX'] "
    "OPTIONAL MATCH (pf)-[:AVAILABLE_IN_MATERIAL]->(m) "
    "RETURN pf.id, pf.default_material, pf.filter_type, pf.allowed_environments, collect(m.id)",
    "MATCH (m) WHERE m.code = 'SF' RETURN labels(m)[0], m.corrosion_class",
]


def emit_sh(path: str) -> None:
    def q(s: str) -> str:
        return s.replace('"', '\\"')
    lines = [
        "#!/bin/sh",
        "# Align graph with M+H Selection Companion V3 (idempotent).",
        "# Generated by backend/database/fix_companion_v3.py --emit-sh. Run INSIDE the falkordb container:",
        "#   sh /var/lib/falkordb/data/fix_companion_v3.sh <password>",
        'PASS="$1"',
        'if [ -z "$PASS" ]; then echo "Usage: sh fix_companion_v3.sh <password>"; exit 1; fi',
        'G="synapse"',
        'run() { redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY "$G" "$1" > /dev/null 2>&1 && echo "ok" || echo "FAIL: $1"; }',
        "",
    ]
    lines += [f'run "{q(s)}"' for s in STATEMENTS]
    lines += ["", 'echo "--- verify ---"']
    lines += [f'redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY "$G" "{q(s)}"' for s in VERIFY]
    lines += ['echo "Companion V3 fix applied. Run SAVE next to persist."', ""]
    with open(path, "w") as f:
        f.write("\n".join(lines))
    os.chmod(path, 0o755)
    print(f"Wrote {path}")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--emit-sh":
        emit_sh(sys.argv[2])
        return
    db = FalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", 6379)),
        password=os.getenv("FALKORDB_PASSWORD") or None,
    )
    g = db.select_graph(os.getenv("FALKORDB_GRAPH", "synapse"))
    for s in STATEMENTS:
        g.query(s)
        print("ok:", s[:90])
    print("--- verify ---")
    for s in VERIFY:
        for row in g.query(s).result_set:
            print(row)


if __name__ == "__main__":
    main()
