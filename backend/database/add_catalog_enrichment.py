#!/usr/bin/env python3
"""
Catalog Enrichment — Graph Data from PDF Catalog (filter_housings_sweden.pdf)

Fixes identified from expert review (Micael) test cases:
- TC1/TC2: Airflow not asked → add airflow as mandatory VariableFeature
- TC2: Connection type (PG/Flange) not configurable → add as VariableFeature
- TC5: GDMI linked to RF but "Ej i Rostfritt" → remove relationship
- TC6: No scope-of-delivery knowledge → add PT/TT transition piece data

Run ONCE: cd backend && python -m database.add_catalog_enrichment
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from db_result_helpers import result_to_dicts, result_single, result_value
from falkordb import FalkorDB

load_dotenv(dotenv_path="../.env")


# =========================================================================
# Product families that need airflow + connection VariableFeatures
# =========================================================================
AIRFLOW_FAMILIES = [
    {
        "family_id": "FAM_GDP",
        "family_code": "GDP",
        "why": "Housing size depends primarily on airflow. Reference: ~2000 m\u00b3/h per 600x600 module at 1.5 m/s face velocity.",
    },
    {
        "family_id": "FAM_GDB",
        "family_code": "GDB",
        "why": "Housing size depends primarily on airflow. Reference: 3400 m\u00b3/h per full module (592x592mm).",
    },
    {
        "family_id": "FAM_GDMI",
        "family_code": "GDMI",
        "why": "Housing size depends primarily on airflow. Reference: 3400 m\u00b3/h per full module (592x592mm).",
    },
    {
        "family_id": "FAM_GDC",
        "family_code": "GDC",
        "why": "Airflow determines carbon contact time, which is critical for adsorption efficiency. Reference: 2000 m\u00b3/h for 600x600 (16 cartridges).",
    },
    {
        "family_id": "FAM_GDC_FLEX",
        "family_code": "GDC_FLEX",
        "why": "Airflow determines carbon contact time, which is critical for adsorption efficiency. Reference: 1750 m\u00b3/h for 600x600 (14 cartridges).",
    },
]

# Families that support both PG and Flange connections
# GDC_FLEX excluded: only FZ material, simpler product
CONNECTION_FAMILIES = [
    "FAM_GDP",
    "FAM_GDB",
    "FAM_GDMI",
    "FAM_GDC",
    "FAM_GDC_FLEX",
]

# PT (Plan Transition) data from PDF — rectangular to round duct
PT_TRANSITIONS = [
    {"housing": "300x300", "w": 300, "h": 300, "duct_mm": 250, "std_length": 300},
    {"housing": "600x300", "w": 600, "h": 300, "duct_mm": 315, "std_length": 450},
    {"housing": "600x600", "w": 600, "h": 600, "duct_mm": 315, "std_length": 450},
    {"housing": "600x600", "w": 600, "h": 600, "duct_mm": 400, "std_length": 450},
    {"housing": "600x600", "w": 600, "h": 600, "duct_mm": 500, "std_length": 450},
]

# TT (Conical Transition) data from PDF — most common sizes
TT_TRANSITIONS = [
    {"housing": "300x300", "w": 300, "h": 300, "duct_mm": 250, "std_length": 300},
    {"housing": "300x600", "w": 300, "h": 600, "duct_mm": 315, "std_length": 450},
    {"housing": "600x300", "w": 600, "h": 300, "duct_mm": 315, "std_length": 450},
    {"housing": "600x600", "w": 600, "h": 600, "duct_mm": 500, "std_length": 450},
    {"housing": "600x900", "w": 600, "h": 900, "duct_mm": 630, "std_length": 600},
    {"housing": "600x1200", "w": 600, "h": 1200, "duct_mm": 630, "std_length": 600},
    {"housing": "600x1500", "w": 600, "h": 1500, "duct_mm": 630, "std_length": 600},
    {"housing": "600x1800", "w": 600, "h": 1800, "duct_mm": 630, "std_length": 600},
    {"housing": "900x600", "w": 900, "h": 600, "duct_mm": 630, "std_length": 600},
    {"housing": "900x900", "w": 900, "h": 900, "duct_mm": 800, "std_length": 600},
    {"housing": "900x1200", "w": 900, "h": 1200, "duct_mm": 800, "std_length": 600},
    {"housing": "900x1500", "w": 900, "h": 1500, "duct_mm": 800, "std_length": 600},
    {"housing": "900x1800", "w": 900, "h": 1800, "duct_mm": 800, "std_length": 600},
    {"housing": "1200x600", "w": 1200, "h": 600, "duct_mm": 630, "std_length": 600},
    {"housing": "1200x900", "w": 1200, "h": 900, "duct_mm": 800, "std_length": 600},
    {"housing": "1200x1200", "w": 1200, "h": 1200, "duct_mm": 1000, "std_length": 600},
    {"housing": "1200x1500", "w": 1200, "h": 1500, "duct_mm": 1000, "std_length": 600},
    {"housing": "1200x1800", "w": 1200, "h": 1800, "duct_mm": 1000, "std_length": 600},
    {"housing": "1500x600", "w": 1500, "h": 600, "duct_mm": 630, "std_length": 600},
    {"housing": "1500x900", "w": 1500, "h": 900, "duct_mm": 800, "std_length": 600},
    {"housing": "1500x1200", "w": 1500, "h": 1200, "duct_mm": 1000, "std_length": 600},
    {"housing": "1500x1500", "w": 1500, "h": 1500, "duct_mm": 1250, "std_length": 600},
    {"housing": "1500x1800", "w": 1500, "h": 1800, "duct_mm": 1250, "std_length": 600},
    {"housing": "1800x600", "w": 1800, "h": 600, "duct_mm": 630, "std_length": 600},
    {"housing": "1800x900", "w": 1800, "h": 900, "duct_mm": 800, "std_length": 600},
    {"housing": "1800x1200", "w": 1800, "h": 1200, "duct_mm": 1000, "std_length": 600},
    {"housing": "1800x1500", "w": 1800, "h": 1500, "duct_mm": 1250, "std_length": 600},
    {"housing": "1800x1800", "w": 1800, "h": 1800, "duct_mm": 1250, "std_length": 600},
]


def add_airflow_variable_features(graph):
    """Section 1a: Add airflow as mandatory VariableFeature on all product families."""

    print("\n" + "=" * 60)
    print("1a. AIRFLOW VARIABLE FEATURES")
    print("=" * 60)

    for fam in AIRFLOW_FAMILIES:
        feat_id = f"FEAT_AIRFLOW_{fam['family_code']}"
        print(f"\n   Adding {feat_id}...")

        graph.query("""
            MATCH (pf:ProductFamily {id: $family_id})

            MERGE (f:VariableFeature {id: $feat_id})
            SET f.name = 'Airflow',
                f.feature_name = 'Airflow',
                f.is_variable = true,
                f.applies_to = $family_code,
                f.parameter_name = 'airflow_m3h',
                f.question = 'What is the required airflow (m\u00b3/h)?',
                f.why_needed = $why_needed,
                f.auto_resolve = false,
                f.description = 'Required air volume flow rate for pressure drop and capacity calculation'

            MERGE (pf)-[:HAS_VARIABLE_FEATURE]->(f)
        """, feat_id=feat_id, family_id=fam["family_id"],
            family_code=fam["family_code"], why_needed=fam["why"])

        print(f"   \u2713 {feat_id} linked to {fam['family_id']}")


def add_connection_type_variable_features(graph):
    """Section 1b: Add connection type as auto-resolved VariableFeature (default PG)."""

    print("\n" + "=" * 60)
    print("1b. CONNECTION TYPE VARIABLE FEATURES")
    print("=" * 60)

    # Create shared FeatureOption nodes (PG and Flange)
    print("\n   Creating connection FeatureOption nodes...")
    graph.query("""
        MERGE (opt_pg:FeatureOption {id: 'OPT_FEAT_CONN_PG'})
        SET opt_pg.name = 'PG 20mm (Standard)',
            opt_pg.value = 'PG',
            opt_pg.description = 'Slip-in PG profile 20mm \u2014 standard duct connection',
            opt_pg.is_default = true,
            opt_pg.length_offset_mm = 0

        MERGE (opt_f:FeatureOption {id: 'OPT_FEAT_CONN_F'})
        SET opt_f.name = 'Flange 40mm',
            opt_f.value = 'F',
            opt_f.description = 'Flange connection 40mm \u2014 surcharge applies. Adds ~50mm to housing length.',
            opt_f.is_default = false,
            opt_f.length_offset_mm = 50
    """)
    print("   \u2713 FeatureOption nodes created (PG, F)")

    for fam_id in CONNECTION_FAMILIES:
        family_code = fam_id.replace("FAM_", "")
        feat_id = f"FEAT_CONNECTION_{family_code}"
        print(f"\n   Adding {feat_id}...")

        graph.query("""
            MATCH (pf:ProductFamily {id: $family_id})

            MERGE (f:VariableFeature {id: $feat_id})
            SET f.name = 'Connection Type',
                f.feature_name = 'Connection Type',
                f.is_variable = true,
                f.applies_to = $family_code,
                f.parameter_name = 'connection_type',
                f.question = 'What duct connection type is needed?',
                f.why_needed = 'PG 20mm slip-in is standard. Flange 40mm available as option (surcharge). Flange adds ~50mm to housing length.',
                f.auto_resolve = true,
                f.default_value = 'PG',
                f.description = 'Duct connection type affects housing length and product code'

            MERGE (pf)-[:HAS_VARIABLE_FEATURE]->(f)

            // Link shared options
            WITH f
            MATCH (opt_pg:FeatureOption {id: 'OPT_FEAT_CONN_PG'})
            MATCH (opt_f:FeatureOption {id: 'OPT_FEAT_CONN_F'})
            MERGE (f)-[:HAS_OPTION]->(opt_pg)
            MERGE (f)-[:HAS_OPTION]->(opt_f)
        """, feat_id=feat_id, family_id=fam_id, family_code=family_code)

        print(f"   \u2713 {feat_id} linked to {fam_id}")


def fix_gdmi_material(graph):
    """Section 1c: Remove RF (stainless steel) from GDMI — 'Ej i Rostfritt'."""

    print("\n" + "=" * 60)
    print("1c. FIX GDMI MATERIAL (remove RF)")
    print("=" * 60)

    result = graph.query("""
        MATCH (gdmi:ProductFamily {id: 'FAM_GDMI'})-[r:AVAILABLE_IN_MATERIAL]->(m:Material {id: 'MAT_RF'})
        DELETE r
        RETURN count(r) AS deleted
    """)
    record = result_single(result)
    deleted = record["deleted"] if record else 0
    if deleted > 0:
        print(f"   \u2713 Removed AVAILABLE_IN_MATERIAL relationship (FAM_GDMI -> MAT_RF)")
    else:
        print("   \u2139 No RF relationship found on GDMI (already clean)")

    # Verify remaining materials
    result = graph.query("""
        MATCH (gdmi:ProductFamily {id: 'FAM_GDMI'})-[:AVAILABLE_IN_MATERIAL]->(m:Material)
        RETURN collect(m.id) AS materials
    """)
    record = result_single(result)
    print(f"   GDMI materials now: {record['materials'] if record else '?'}")


def update_code_formats(graph):
    """Section 1d: Change hardcoded PG to {connection} placeholder in code_format."""

    print("\n" + "=" * 60)
    print("1d. UPDATE CODE_FORMAT TEMPLATES")
    print("=" * 60)

    result = graph.query("""
        MATCH (pf:ProductFamily)
        WHERE pf.code_format IS NOT NULL AND pf.code_format CONTAINS '-PG-'
        SET pf.code_format = replace(pf.code_format, '-PG-', '-{connection}-')
        RETURN pf.id AS family_id, pf.code_format AS new_format
    """)

    for record in result_to_dicts(result):
        print(f"   \u2713 {record['family_id']}: {record['new_format']}")


def update_option_nodes(graph):
    """Section 1e: Add length_offset_mm to existing Option nodes."""

    print("\n" + "=" * 60)
    print("1e. UPDATE OPTION NODES WITH LENGTH OFFSET")
    print("=" * 60)

    graph.query("""
        MATCH (opt:Option {id: 'OPT_CONN_PG'})
        SET opt.length_offset_mm = 0
    """)
    print("   \u2713 OPT_CONN_PG: length_offset_mm = 0")

    graph.query("""
        MATCH (opt:Option {id: 'OPT_CONN_FL'})
        SET opt.length_offset_mm = 50
    """)
    print("   \u2713 OPT_CONN_FL: length_offset_mm = 50")


def add_transition_pieces(graph):
    """Section 1f: Add PT/TT transition piece catalog data."""

    print("\n" + "=" * 60)
    print("1f. TRANSITION PIECE CATALOG (PT/TT)")
    print("=" * 60)

    # PT — Plan (flat) transitions
    print("\n   Adding PT (Plan) transitions...")
    for pt in PT_TRANSITIONS:
        node_id = f"PT-{pt['housing']}-{pt['duct_mm']}"
        graph.query("""
            MERGE (tp:TransitionPiece {id: $id})
            SET tp.name = $name,
                tp.type = 'PT',
                tp.transition_type = 'Plan (Flat)',
                tp.housing_size = $housing,
                tp.housing_width_mm = $w,
                tp.housing_height_mm = $h,
                tp.duct_diameter_mm = $duct,
                tp.standard_length_mm = $length,
                tp.standard_material = 'FZ',
                tp.ordered_separately = true,
                tp.note = 'Plan transition to round duct. Must be ordered separately from the housing.'
        """, id=node_id,
            name=f"PT {pt['housing']} \u2192 \u00d8{pt['duct_mm']}",
            housing=pt["housing"], w=pt["w"], h=pt["h"],
            duct=pt["duct_mm"], length=pt["std_length"])
    print(f"   \u2713 {len(PT_TRANSITIONS)} PT transitions added")

    # TT — Conical transitions
    print("   Adding TT (Conical) transitions...")
    for tt in TT_TRANSITIONS:
        node_id = f"TT-{tt['housing']}-{tt['duct_mm']}"
        graph.query("""
            MERGE (tp:TransitionPiece {id: $id})
            SET tp.name = $name,
                tp.type = 'TT',
                tp.transition_type = 'Conical (Tapered)',
                tp.housing_size = $housing,
                tp.housing_width_mm = $w,
                tp.housing_height_mm = $h,
                tp.duct_diameter_mm = $duct,
                tp.standard_length_mm = $length,
                tp.standard_material = 'FZ',
                tp.ordered_separately = true,
                tp.note = 'Conical transition to round duct. Must be ordered separately from the housing.'
        """, id=node_id,
            name=f"TT {tt['housing']} \u2192 \u00d8{tt['duct_mm']}",
            housing=tt["housing"], w=tt["w"], h=tt["h"],
            duct=tt["duct_mm"], length=tt["std_length"])
    print(f"   \u2713 {len(TT_TRANSITIONS)} TT transitions added")

    # Link transitions to compatible product families
    print("   Linking transitions to product families...")
    graph.query("""
        MATCH (tp:TransitionPiece)
        MATCH (pf:ProductFamily)
        WHERE pf.id IN ['FAM_GDP', 'FAM_GDB', 'FAM_GDMI', 'FAM_GDC', 'FAM_GDC_FLEX']
        MERGE (pf)-[:HAS_COMPATIBLE_TRANSITION]->(tp)
    """)
    print("   \u2713 All transitions linked to product families")


def verify_schema(graph):
    """Verify the complete schema after all changes."""

    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    # VariableFeatures per family
    result = graph.query("""
        MATCH (pf:ProductFamily)-[:HAS_VARIABLE_FEATURE]->(f:VariableFeature)
        OPTIONAL MATCH (f)-[:HAS_OPTION]->(o:FeatureOption)
        WITH pf, f, collect(o.value) AS options
        RETURN pf.id AS family,
               f.name AS feature,
               f.parameter_name AS param,
               f.auto_resolve AS auto_resolve,
               options
        ORDER BY pf.id, f.name
    """)
    print("\n   Variable Features:")
    for r in result_to_dicts(result):
        auto = " (auto-resolve)" if r["auto_resolve"] else " (MANDATORY)"
        opts = f" options={r['options']}" if r["options"] and r["options"][0] else ""
        print(f"   {r['family']}: {r['feature']} [{r['param']}]{auto}{opts}")

    # Code formats
    result = graph.query("""
        MATCH (pf:ProductFamily)
        WHERE pf.code_format IS NOT NULL
        RETURN pf.id AS family, pf.code_format AS fmt
        ORDER BY pf.id
    """)
    print("\n   Code Formats:")
    for r in result_to_dicts(result):
        print(f"   {r['family']}: {r['fmt']}")

    # GDMI materials
    result = graph.query("""
        MATCH (g:ProductFamily {id: 'FAM_GDMI'})-[r:AVAILABLE_IN_MATERIAL]->(m:Material)
        RETURN m.id AS material, r.is_default AS is_default
    """)
    print("\n   GDMI Materials:")
    for r in result_to_dicts(result):
        default = " (default)" if r["is_default"] else ""
        print(f"   {r['material']}{default}")

    # Transition pieces count
    result = graph.query("""
        MATCH (tp:TransitionPiece)
        RETURN tp.type AS type, count(tp) AS count
        ORDER BY tp.type
    """)
    print("\n   Transition Pieces:")
    for r in result_to_dicts(result):
        print(f"   {r['type']}: {r['count']} nodes")


def main():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", 6379))
    password = os.getenv("FALKORDB_PASSWORD", None)
    graph_name = os.getenv("FALKORDB_GRAPH", "hvac")

    # FalkorDB connects with defaults if env vars not set

    print(f"Connecting to FalkorDB at {host}:{port}...")
    db = FalkorDB(host=host, port=port, password=password)
    graph = db.select_graph(graph_name)

    try:
        result = graph.query("RETURN 1 AS test")
        if result_single(result)["test"] != 1:
            raise Exception("Connection test failed")
        print("Connected successfully!")

        add_airflow_variable_features(graph)
        add_connection_type_variable_features(graph)
        fix_gdmi_material(graph)
        update_code_formats(graph)
        update_option_nodes(graph)
        add_transition_pieces(graph)
        verify_schema(graph)

        print("\n" + "=" * 60)
        print("CATALOG ENRICHMENT COMPLETE")
        print("=" * 60)
        print("\nChanges applied:")
        print("  - Airflow: mandatory VariableFeature on 5 product families")
        print("  - Connection: auto-resolved VariableFeature (PG default) on 5 families")
        print("  - GDMI: RF material relationship removed")
        print("  - Code formats: PG replaced with {connection} placeholder")
        print("  - Transition pieces: PT + TT catalog with scope-of-delivery flag")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        pass  # FalkorDB connection auto-managed


if __name__ == "__main__":
    main()
