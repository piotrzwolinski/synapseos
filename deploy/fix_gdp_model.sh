#!/bin/sh
# Apply the GDP catalog-model fix to a FalkorDB graph (idempotent).
# Mirrors backend/database/fix_gdp_model.py. Run INSIDE the falkordb container:
#   sh /var/lib/falkordb/data/fix_gdp_model.sh <password>
PASS="$1"
if [ -z "$PASS" ]; then echo "Usage: sh fix_gdp_model.sh <password>"; exit 1; fi
G="synapse"
run() { redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY "$G" "$1" > /dev/null 2>&1 && echo "ok" || echo "FAIL: $1"; }

run "MATCH (f:VariableFeature {id:'FEAT_FRAME_DEPTH_GDP'}) SET f.parameter_name='filter_depth', f.property_key='filter_depth', f.feature_name='Filter Frame Depth', f.name='Filter Frame Depth', f.is_variable=true, f.inquiry_priority=25"

run "MERGE (o:FeatureOption {id:'OPT_GDP_DEPTH_25'}) SET o.value=25, o.name='25mm', o.display_label='25mm', o.description='Shallow panel/pleat filter frame (25 mm).', o.is_default=false, o.is_recommended=false"
run "MERGE (o:FeatureOption {id:'OPT_GDP_DEPTH_50'}) SET o.value=50, o.name='50mm', o.display_label='50mm', o.description='Standard panel filter frame depth (50 mm).', o.is_default=true, o.is_recommended=true"
run "MERGE (o:FeatureOption {id:'OPT_GDP_DEPTH_100'}) SET o.value=100, o.name='100mm', o.display_label='100mm', o.description='Deep panel filter frame (100 mm) for higher dust capacity.', o.is_default=false, o.is_recommended=false"

run "MATCH (f:VariableFeature {id:'FEAT_FRAME_DEPTH_GDP'}), (o:FeatureOption {id:'OPT_GDP_DEPTH_25'}) MERGE (f)-[:HAS_OPTION]->(o)"
run "MATCH (f:VariableFeature {id:'FEAT_FRAME_DEPTH_GDP'}), (o:FeatureOption {id:'OPT_GDP_DEPTH_50'}) MERGE (f)-[:HAS_OPTION]->(o)"
run "MATCH (f:VariableFeature {id:'FEAT_FRAME_DEPTH_GDP'}), (o:FeatureOption {id:'OPT_GDP_DEPTH_100'}) MERGE (f)-[:HAS_OPTION]->(o)"

run "MERGE (d:Discriminator {id:'DISC_GDP_DEPTH'}) SET d.parameter_name='filter_depth', d.question='What is the filter frame depth?', d.why_needed='Panel filter frame depth (25/50/100 mm) sets the internal mounting frame. GDP housing length is fixed at 250 mm.'"
run "MATCH (f:VariableFeature {id:'FEAT_FRAME_DEPTH_GDP'}), (d:Discriminator {id:'DISC_GDP_DEPTH'}) MERGE (f)-[:SELECTION_DEPENDS_ON]->(d)"

run "MATCH (f:VariableFeature {id:'FEAT_HOUSING_LENGTH_GDP'}) SET f.parameter_name='housing_length', f.property_key='housing_length', f.name='Housing Length', f.auto_resolve=true, f.default_value=250, f.is_variable=false"

echo "--- verify ---"
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY "$G" "MATCH (f:VariableFeature {id:'FEAT_FRAME_DEPTH_GDP'})-[:HAS_OPTION]->(o) RETURN f.parameter_name, collect(o.value)"
echo "GDP model fix applied. Run SAVE next to persist."
