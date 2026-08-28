#!/usr/bin/env python3
"""Fix the GDP (Planfilterskåp) model to match the catalog.

Catalog (filter_housings_sweden.pdf, GDP page): GDP is a PANEL filter cabinet
with a FIXED 250 mm housing length and standard filter FRAME depths of 25/50/100
mm. It was mismodeled: the frame-depth VariableFeature had no options (so the LLM
invented non-deterministic depths like 48/292/450), and housing length was being
derived as 550/750 (bag-filter lengths) instead of the fixed 250.

This migration (idempotent):
  1. FEAT_FRAME_DEPTH_GDP: set property_key=filter_depth + 3 fixed options 25/50/100
     + a Discriminator (mirrors the working FEAT_HOUSING_LENGTH_GDB structure).
  2. FEAT_HOUSING_LENGTH_GDP: property_key=housing_length, auto_resolve=true,
     default_value=250 so length is fixed, not asked.

Run: cd backend && python -m database.fix_gdp_model
"""
import os
from falkordb import FalkorDB


DEPTH_OPTIONS = [
    ("OPT_GDP_DEPTH_25", 25, "25mm", "Shallow panel/pleat filter frame (25 mm).", False, False),
    ("OPT_GDP_DEPTH_50", 50, "50mm", "Standard panel filter frame depth (50 mm).", True, True),
    ("OPT_GDP_DEPTH_100", 100, "100mm", "Deep panel filter frame (100 mm) for higher dust capacity.", False, False),
]


def main():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    password = os.getenv("FALKORDB_PASSWORD") or None
    graph_name = os.getenv("FALKORDB_GRAPH", "synapse")
    g = FalkorDB(host=host, port=port, password=password).select_graph(graph_name)

    def q(cypher, params=None):
        return g.query(cypher, params=params or {})

    # 1. Frame-depth feature: get_variable_features reads f.parameter_name (not
    # property_key), and the tag reports missing 'filter_depth', so the feature
    # MUST use parameter_name='filter_depth' to attach its options to that
    # clarification. build_product_code maps the resolved filter_depth into the
    # code's {frame_depth} token.
    q("""
        MATCH (f:VariableFeature {id:'FEAT_FRAME_DEPTH_GDP'})
        SET f.parameter_name='filter_depth', f.property_key='filter_depth',
            f.feature_name='Filter Frame Depth', f.name='Filter Frame Depth',
            f.is_variable=true, f.inquiry_priority=25
    """)

    # 2. Frame-depth options 25/50/100
    for oid, val, label, desc, is_def, is_rec in DEPTH_OPTIONS:
        q("""
            MERGE (o:FeatureOption {id:$oid})
            SET o.value=$val, o.name=$label, o.display_label=$label,
                o.description=$desc, o.is_default=$is_def, o.is_recommended=$is_rec
        """, {"oid": oid, "val": val, "label": label, "desc": desc,
              "is_def": is_def, "is_rec": is_rec})
        q("""
            MATCH (f:VariableFeature {id:'FEAT_FRAME_DEPTH_GDP'}),
                  (o:FeatureOption {id:$oid})
            MERGE (f)-[:HAS_OPTION]->(o)
        """, {"oid": oid})

    # 3. Discriminator (question shown to the user)
    q("""
        MERGE (d:Discriminator {id:'DISC_GDP_DEPTH'})
        SET d.parameter_name='filter_depth',
            d.question='What is the filter frame depth?',
            d.why_needed='Panel filter frame depth (25/50/100 mm) sets the internal mounting frame. GDP housing length is fixed at 250 mm.'
    """)
    q("""
        MATCH (f:VariableFeature {id:'FEAT_FRAME_DEPTH_GDP'}),
              (d:Discriminator {id:'DISC_GDP_DEPTH'})
        MERGE (f)-[:SELECTION_DEPENDS_ON]->(d)
    """)

    # 4. Housing length feature: fixed 250, auto-resolve (never asked)
    q("""
        MATCH (f:VariableFeature {id:'FEAT_HOUSING_LENGTH_GDP'})
        SET f.property_key='housing_length', f.name='Housing Length',
            f.auto_resolve=true, f.default_value=250, f.is_variable=false
    """)

    # Verify
    res = g.query("""
        MATCH (f:VariableFeature {id:'FEAT_FRAME_DEPTH_GDP'})-[:HAS_OPTION]->(o)
        RETURN f.property_key AS pk, collect(o.value) AS opts
    """)
    row = res.result_set[0] if res.result_set else [None, []]
    print(f"FEAT_FRAME_DEPTH_GDP property_key={row[0]} options={sorted(row[1])}")
    res2 = g.query("""
        MATCH (f:VariableFeature {id:'FEAT_HOUSING_LENGTH_GDP'})
        RETURN f.property_key, f.auto_resolve, f.default_value
    """)
    print("FEAT_HOUSING_LENGTH_GDP:", res2.result_set[0] if res2.result_set else None)
    print("GDP model migration done.")


if __name__ == "__main__":
    main()
