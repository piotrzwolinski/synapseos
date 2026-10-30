#!/usr/bin/env python3
"""Companion V3 — batch B: quick graph fixes from M+H's answers to Q-01..Q-07 (2026-10-30).

Only the pure, low-risk GRAPH-DATA fixes go here. Engine-logic items from the
same answers (A-07 corrosion model, F-06 flange +50mm offset, F-05 door L/R,
F-07 PT/TT, F-09..F-12, F-14, and the Q-07 post-presentation override) need code
changes and are handled separately.

Fixes in this batch (idempotent, SET / DETACH-DELETE only — never touches Layer 4):
  A-08 (Q-05): GDP frame-depth default 50 -> 100 ("100 is most common", M+H).
               Deriving depth from the chosen filter is a follow-up, not here.
  F-15:        Remove the malformed duplicate GDMI housing-length VariableFeature
               (FEAT_HOUSING_LENGTH_GDMI, parameter_name = NULL) that perpetually
               surfaces as a length clarification. The canonical VF_GDMI_LENGTH
               (parameter_name='housing_length', same OPT_GDMI_LEN_600/850 options,
               SELECTION_DEPENDS_ON DISC_LENGTH) stays. Its now-orphan discriminator
               DISC_GDMI_LENGTH is cleaned up. Mirrors fix_polis_length_feature.py
               (node 791); this is the sibling node 790 left open there.
  F-06 (Q-02): GDMI FLEX had no connection_type feature at all, so the 40mm flange
               option (F) was never offered. Add FEAT_CONNECTION_GDMI_FLEX mirroring
               the other families, reusing the SHARED OPT_FEAT_CONN_PG/F option nodes
               (default PG, auto_resolve → no new clarification). The flange length
               offset is already correct: OPT_FEAT_CONN_F.length_offset_mm = 50 (Q-02
               confirmed +50, not +40), applied via get_connection_length_offset().
  F-14:        Insulation note per housing family (brochure "Övriga skåp isoleras på
               plats"): GDMI/GDMI FLEX = factory-insulated; GDP/GDB/GDC/GDC FLEX =
               insulated on site. Stored as pf.insulation + pf.insulation_note, injected
               into the HOUSING SPECIFICATION prompt block by retriever.py.
  F-05 (+F-06 non-FLEX): GDB/GDC/GDMI/GDP code_format hardcoded '-R-PG-'; replaced with
               '-{side}-{connection}-' (backward-compatible). Scribe door_hinge + retriever
               map to {side}; flange now expressible on all housings too.
  F-09:        pf.recommended_for on EXL (fine/higher classes) + Filter Profil (low classes).
  F-10:        pf.max_filter_class='F9' + pf.filter_class_note (HEPA guardrail) on GDB/GDMI/GDP.
  F-13:        Accessory audit vs brochure — verified EXL/BFF/PFF/Filter Profil correct;
               fixed Filter Profil corrosion_class (→C2) and BFF variant weights.

A-09 (Q-06, GDMI FLEX weights) and the other confirmations need no graph change.

Run:      cd backend && python database/fix_companion_v3b.py
Emit sh:  cd backend && python database/fix_companion_v3b.py --emit-sh ../deploy/fix_companion_v3b.sh
"""
import os
import sys

from falkordb import FalkorDB

STATEMENTS = [
    # A-08: GDP default frame depth 50 -> 100 (integer, matching the existing type).
    "MATCH (vf:VariableFeature {id: 'FEAT_FRAME_DEPTH_GDP'}) SET vf.default_value = 100",
    # F-15a: drop the malformed GDMI length feature (NULL parameter_name). Targeted
    # structurally via FAM_GDMI + NULL param so it is portable across reseeds (the
    # internal node id is not stable). Shared option nodes stay (held by VF_GDMI_LENGTH).
    "MATCH (:ProductFamily {id: 'FAM_GDMI'})-[:HAS_VARIABLE_FEATURE]->(f:VariableFeature) "
    "WHERE f.parameter_name IS NULL DETACH DELETE f",
    # F-15b: clean up the discriminator orphaned by F-15a (only the malformed node used it).
    "MATCH (d:Discriminator {id: 'DISC_GDMI_LENGTH'}) "
    "WHERE NOT ()-[:SELECTION_DEPENDS_ON]->(d) DETACH DELETE d",
    # F-06: give GDMI FLEX a connection_type feature with PG + flange (F) options,
    # reusing the shared option nodes (so OPT_FEAT_CONN_F's +50 offset applies).
    "MATCH (pf:ProductFamily {id: 'FAM_GDMI_FLEX'}) "
    "MERGE (f:VariableFeature {id: 'FEAT_CONNECTION_GDMI_FLEX'}) "
    "SET f.parameter_name = 'connection_type', f.name = 'Connection Type', "
    "f.default_value = 'PG', f.auto_resolve = true, f.is_variable = true, "
    "f.question = 'What duct connection type is needed?', f.applies_to = 'GDMI_FLEX' "
    "MERGE (pf)-[:HAS_VARIABLE_FEATURE]->(f) "
    "WITH f "
    "MATCH (pg:FeatureOption {id: 'OPT_FEAT_CONN_PG'}) "
    "MATCH (fl:FeatureOption {id: 'OPT_FEAT_CONN_F'}) "
    "MERGE (f)-[:HAS_OPTION]->(pg) "
    "MERGE (f)-[:HAS_OPTION]->(fl)",
    # F-14: insulation note per housing family (brochure "Övriga skåp isoleras på plats").
    # Kept as graph text so the engine only passes it through (domain-agnostic).
    "MATCH (pf:ProductFamily) WHERE pf.id IN ['FAM_GDMI', 'FAM_GDMI_FLEX'] "
    "SET pf.insulation = 'factory', "
    "pf.insulation_note = 'Factory-insulated (double-wall, heat + condensation).'",
    "MATCH (pf:ProductFamily) WHERE pf.id IN ['FAM_GDP', 'FAM_GDB', 'FAM_GDC', 'FAM_GDC_FLEX'] "
    "SET pf.insulation = 'on_site', "
    "pf.insulation_note = 'Not factory-insulated — the housing is insulated on site by the installer.'",
    # F-05 (+F-06 for non-FLEX): the GDB/GDC/GDMI code templates hardcoded the door
    # hand ('R') and connection ('PG'), so left-hinged doors and flange connections
    # could never appear in the code. Replace with {side}/{connection} placeholders.
    # Backward-compatible: build_product_code defaults side='R', connection='PG', so
    # an unspecified order yields the exact same code as before.
    "MATCH (pf:ProductFamily) WHERE pf.id IN ['FAM_GDB', 'FAM_GDC', 'FAM_GDMI'] "
    "SET pf.code_format = '{family}-{width}x{height}-{length}-{side}-{connection}-{material}'",
    "MATCH (pf:ProductFamily {id: 'FAM_GDP'}) "
    "SET pf.code_format = '{family}-{width}x{height}-{frame_depth}-{side}-{connection}-{material}'",
    # F-10: filter-class ceiling + HEPA guardrail (brochure "upp t.o.m. F9 enligt VVS
    # AMA QGB/1"). An H13 element may physically fit but the housing is not a certified
    # HEPA installation — surface this so the LLM does not present it as validated HEPA.
    "MATCH (pf:ProductFamily) WHERE pf.id IN ['FAM_GDB', 'FAM_GDMI', 'FAM_GDP'] "
    "SET pf.max_filter_class = 'F9', "
    "pf.filter_class_note = 'Rated up to filter class F9 (VVS AMA QGB/1, general ventilation). "
    "NOT a certified HEPA installation — if an H13/HEPA element is requested, do not present it "
    "as a validated HEPA setup; route to a specialist.'",
    # F-11: GDMI on a rooftop must NOT hard-block (Q-04: refer to specialist for the
    # extra-roof option). The SET_MEMBERSHIP env veto fired because ENV_OUTDOOR was
    # missing from GDMI.allowed_environments — inconsistent with the pivot logic that
    # routes GDB-outdoor → GDMI (the insulated option). Add ENV_OUTDOOR so the engine
    # does not hard-block; the retriever prompt note (indoor_only → "extra-roof via
    # specialist") supplies the caveat. indoor_only stays true.
    "MATCH (pf:ProductFamily {id: 'FAM_GDMI'}) SET pf.allowed_environments = "
    "CASE WHEN 'ENV_OUTDOOR' IN pf.allowed_environments THEN pf.allowed_environments "
    "ELSE pf.allowed_environments + 'ENV_OUTDOOR' END",
    # F-09: EXL vs Filter Profil recommendation by filter class (brochure Tillbehör).
    "MATCH (pf:ProductFamily {id: 'FAM_EXL'}) "
    "SET pf.recommended_for = 'fine filters and higher filter classes (e.g. ePM1 / fine filters)'",
    "MATCH (pf:ProductFamily {id: 'FAM_FILTER_PROFIL'}) "
    "SET pf.recommended_for = 'low filter classes only (coarse / ePM10)'",
    # F-09 (refine): the engine's accessory allow-list checks Accessory nodes, not
    # ProductFamily. Filter Profil had no ACC node → flagged "NOT compatible with GDB".
    # Create ACC_FILTER_PROFIL, link it to the bag housings that also carry EXL, and
    # put the by-class recommendation on both ACC nodes.
    "MERGE (a:Accessory {id: 'ACC_FILTER_PROFIL'}) "
    "SET a.name = 'Filter Profil', a.full_name = 'Filter Profil (filter rail)', "
    "a.category = 'Locking Mechanism', a.applies_to = 'Bag Filter Housings', "
    "a.description = 'Filter rail for locking bag/panel filters — recommended for low filter classes.', "
    "a.recommended_for = 'low filter classes only (coarse / ePM10)'",
    "MATCH (h:ProductFamily), (a:Accessory {id: 'ACC_FILTER_PROFIL'}) "
    "WHERE h.id IN ['FAM_GDB', 'FAM_GDMI', 'FAM_GDP'] "
    "MERGE (h)-[:HAS_COMPATIBLE_ACCESSORY]->(a)",
    "MATCH (a:Accessory {id: 'ACC_EXL'}) "
    "SET a.recommended_for = 'fine filters and higher filter classes (e.g. ePM1 / fine filters)', "
    "a.description = 'Quick-release eccentric locking for bag filter frames — recommended for fine filters and higher filter classes (e.g. ePM1).'",
    # F-13: accessory data audit vs brochure (Tillbehör / BFF / PFF pages). Verified
    # correct: EXL 8 widths 300-2400 (AZ/C4), BFF 5 sizes (FZ/C2), PFF 25 sizes
    # (FZ/C2, depths 25/50/100), Filter Profil 12 widths 200-1800 (D20/50/100, FZ).
    # Two gaps fixed:
    #   (1) Filter Profil had no corrosion_class — set C2 (galvanized, like BFF/PFF).
    "MATCH (pf:ProductFamily {id: 'FAM_FILTER_PROFIL'}) SET pf.corrosion_class = 'C2'",
    #   (2) BFF variants had no weight_kg — add the brochure Påsfilterram weights.
    "MATCH (v:ProductVariant {id: 'PV_BFF_305x305'}) SET v.weight_kg = 1",
    "MATCH (v:ProductVariant {id: 'PV_BFF_610x305'}) SET v.weight_kg = 1",
    "MATCH (v:ProductVariant {id: 'PV_BFF_910x305'}) SET v.weight_kg = 2",
    "MATCH (v:ProductVariant {id: 'PV_BFF_610x610'}) SET v.weight_kg = 2",
    "MATCH (v:ProductVariant {id: 'PV_BFF_910x610'}) SET v.weight_kg = 3",
]

VERIFY = [
    "MATCH (vf:VariableFeature {id: 'FEAT_FRAME_DEPTH_GDP'}) RETURN vf.id, vf.default_value",
    "MATCH (:ProductFamily {id: 'FAM_GDMI'})-[:HAS_VARIABLE_FEATURE]->(f:VariableFeature) "
    "WHERE f.parameter_name = 'housing_length' OR f.parameter_name IS NULL "
    "RETURN f.id, f.parameter_name",
    "MATCH (d:Discriminator {id: 'DISC_GDMI_LENGTH'}) RETURN count(d) AS orphan_discriminators",
    "MATCH (:ProductFamily {id: 'FAM_GDMI_FLEX'})-[:HAS_VARIABLE_FEATURE]->"
    "(f:VariableFeature {parameter_name: 'connection_type'})-[:HAS_OPTION]->(o:FeatureOption) "
    "RETURN f.id, collect(o.value), collect(o.length_offset_mm)",
    "MATCH (pf:ProductFamily) WHERE pf.insulation IS NOT NULL "
    "RETURN pf.id, pf.insulation ORDER BY pf.id",
]


def emit_sh(path: str) -> None:
    def q(s: str) -> str:
        return s.replace('"', '\\"')
    lines = [
        "#!/bin/sh",
        "# Companion V3 batch B (quick graph fixes). Idempotent.",
        "# Generated by backend/database/fix_companion_v3b.py --emit-sh. Run INSIDE the falkordb container:",
        "#   sh /var/lib/falkordb/data/fix_companion_v3b.sh <password>",
        'PASS="$1"',
        'if [ -z "$PASS" ]; then echo "Usage: sh fix_companion_v3b.sh <password>"; exit 1; fi',
        'G="synapse"',
        'run() { redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY "$G" "$1" > /dev/null 2>&1 && echo "ok" || echo "FAIL: $1"; }',
        "",
    ]
    lines += [f'run "{q(s)}"' for s in STATEMENTS]
    lines += ["", 'echo "--- verify ---"']
    lines += [f'redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY "$G" "{q(s)}"' for s in VERIFY]
    lines += ['echo "Companion V3 batch B applied. Run SAVE next to persist."', ""]
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
