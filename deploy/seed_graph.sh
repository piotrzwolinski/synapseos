#!/bin/sh
# Auto-generated FalkorDB seed script
# 243 Cypher statements from graph_schema.cypher

PASS="$1"
if [ -z "$PASS" ]; then echo "Usage: sh seed_graph.sh <password>"; exit 1; fi

echo "Starting graph seed..."
ERRORS=0
OK=0

redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (m:Material) REQUIRE m.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [1]: CREATE CONSTRAINT IF NOT EXISTS FOR (m:Material) REQUIRE m.i..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (p:ProductFamily) REQUIRE p.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [2]: CREATE CONSTRAINT IF NOT EXISTS FOR (p:ProductFamily) REQUIR..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (d:DimensionModule) REQUIRE d.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [3]: CREATE CONSTRAINT IF NOT EXISTS FOR (d:DimensionModule) REQU..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (o:Option) REQUIRE o.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [4]: CREATE CONSTRAINT IF NOT EXISTS FOR (o:Option) REQUIRE o.id ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (mat_fz:Material {id: '"'"'MAT_FZ'"'"'})
SET mat_fz.code = '"'"'FZ'"'"',
    mat_fz.name = '"'"'Förzinkat (Ocynk)'"'"',
    mat_fz.corrosion_class = '"'"'C3'"'"',
    mat_fz.desc = '"'"'Standard steel core with zinc coating Z275'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [5]: MERGE (mat_fz:Material {id: '"'"'MAT_FZ'"'"'})
SET mat_fz.co..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (mat_az:Material {id: '"'"'MAT_AZ'"'"'})
SET mat_az.code = '"'"'AZ'"'"',
    mat_az.name = '"'"'Aluzink'"'"',
    mat_az.corrosion_class = '"'"'C4'"'"',
    mat_az.desc = '"'"'Coated with mix of zinc, aluminium, silicon'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [6]: MERGE (mat_az:Material {id: '"'"'MAT_AZ'"'"'})
SET mat_az.co..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (mat_rf:Material {id: '"'"'MAT_RF'"'"'})
SET mat_rf.code = '"'"'RF'"'"',
    mat_rf.name = '"'"'Rostfri (Nierdzewna)'"'"',
    mat_rf.corrosion_class = '"'"'C5'"'"',
    mat_rf.desc = '"'"'Stainless Steel EN 1.4301 (SS 2333)'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [7]: MERGE (mat_rf:Material {id: '"'"'MAT_RF'"'"'})
SET mat_rf.co..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (mat_sf:Material {id: '"'"'MAT_SF'"'"'})
SET mat_sf.code = '"'"'SF'"'"',
    mat_sf.name = '"'"'Syrafast (Kwasoodporna)'"'"',
    mat_sf.corrosion_class = '"'"'C5.1'"'"',
    mat_sf.desc = '"'"'Acid-proof Stainless Steel EN 1.4404 (SS 2348)'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [8]: MERGE (mat_sf:Material {id: '"'"'MAT_SF'"'"'})
SET mat_sf.co..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (mat_zm:Material {id: '"'"'MAT_ZM'"'"'})
SET mat_zm.code = '"'"'ZM'"'"',
    mat_zm.name = '"'"'Zinkmagnesium'"'"',
    mat_zm.corrosion_class = '"'"'C5'"'"',
    mat_zm.desc = '"'"'Zinc-Magnesium ZM310'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [9]: MERGE (mat_zm:Material {id: '"'"'MAT_ZM'"'"'})
SET mat_zm.co..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_door_r:Option {id: '"'"'OPT_DOOR_R'"'"'})
SET opt_door_r.code = '"'"'R'"'"',
    opt_door_r.name = '"'"'Högerhängd (Right)'"'"',
    opt_door_r.type = '"'"'Hinging'"'"',
    opt_door_r.is_standard = true' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [10]: MERGE (opt_door_r:Option {id: '"'"'OPT_DOOR_R'"'"'})
SET opt..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_door_l:Option {id: '"'"'OPT_DOOR_L'"'"'})
SET opt_door_l.code = '"'"'L'"'"',
    opt_door_l.name = '"'"'Vänsterhängd (Left)'"'"',
    opt_door_l.type = '"'"'Hinging'"'"',
    opt_door_l.is_standard = false' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [11]: MERGE (opt_door_l:Option {id: '"'"'OPT_DOOR_L'"'"'})
SET opt..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_conn_pg:Option {id: '"'"'OPT_CONN_PG'"'"'})
SET opt_conn_pg.code = '"'"'PG'"'"',
    opt_conn_pg.name = '"'"'PG-profil 20mm'"'"',
    opt_conn_pg.type = '"'"'Connection'"'"',
    opt_conn_pg.is_standard = true' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [12]: MERGE (opt_conn_pg:Option {id: '"'"'OPT_CONN_PG'"'"'})
SET o..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_conn_fl:Option {id: '"'"'OPT_CONN_FL'"'"'})
SET opt_conn_fl.code = '"'"'F'"'"',
    opt_conn_fl.name = '"'"'Fläns (Flange) 40mm'"'"',
    opt_conn_fl.type = '"'"'Connection'"'"',
    opt_conn_fl.is_standard = false' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [13]: MERGE (opt_conn_fl:Option {id: '"'"'OPT_CONN_FL'"'"'})
SET o..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_lock_exl:Option {id: '"'"'OPT_LOCK_EXL'"'"'})
SET opt_lock_exl.code = '"'"'EXL'"'"',
    opt_lock_exl.name = '"'"'Excenterlåsning'"'"',
    opt_lock_exl.desc = '"'"'Eccentric locking mechanism'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [14]: MERGE (opt_lock_exl:Option {id: '"'"'OPT_LOCK_EXL'"'"'})
SET..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_nipple:Option {id: '"'"'OPT_NIPPLE'"'"'})
SET opt_nipple.name = '"'"'Mätuttag'"'"',
    opt_nipple.desc = '"'"'Measurement nipples included'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [15]: MERGE (opt_nipple:Option {id: '"'"'OPT_NIPPLE'"'"'})
SET opt..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (feat_insul:Feature {id: '"'"'FEAT_INSUL'"'"'})
SET feat_insul.name = '"'"'Thermal Insulation'"'"',
    feat_insul.desc = '"'"'Double-walled, condensation protected'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [16]: MERGE (feat_insul:Feature {id: '"'"'FEAT_INSUL'"'"'})
SET fe..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (feat_rail:Feature {id: '"'"'FEAT_RAIL'"'"'})
SET feat_rail.name = '"'"'Extractable Rail'"'"',
    feat_rail.desc = '"'"'Slide-out rail for heavy filters'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [17]: MERGE (feat_rail:Feature {id: '"'"'FEAT_RAIL'"'"'})
SET feat..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'})
SET gdp.name = '"'"'GDP Planfilterskåp'"'"',
    gdp.type = '"'"'Panel Filter Housing'"'"',
    gdp.page_ref = 5,
    gdp.selection_priority = 10,
    gdp.code_format = '"'"'{family}-{width}x{height}-{length}-R-PG-{material}'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [18]: MERGE (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'})
SET gdp.na..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (mat:Material {id: '"'"'MAT_FZ'"'"'})
MERGE (gdp)-[:AVAILABLE_IN_MATERIAL {is_default: true}]->(mat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [19]: MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (mat:Mate..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (mat:Material {id: '"'"'MAT_AZ'"'"'})
MERGE (gdp)-[:AVAILABLE_IN_MATERIAL]->(mat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [20]: MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (mat:Mate..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (mat:Material {id: '"'"'MAT_RF'"'"'})
MERGE (gdp)-[:AVAILABLE_IN_MATERIAL]->(mat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [21]: MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (mat:Mate..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (opt:Option {id: '"'"'OPT_DOOR_R'"'"'})
MERGE (gdp)-[:HAS_DEFAULT_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [22]: MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (opt:Option {id: '"'"'OPT_DOOR_L'"'"'})
MERGE (gdp)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [23]: MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (opt:Option {id: '"'"'OPT_CONN_PG'"'"'})
MERGE (gdp)-[:HAS_DEFAULT_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [24]: MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (opt:Option {id: '"'"'OPT_CONN_FL'"'"'})
MERGE (gdp)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [25]: MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (opt:Option {id: '"'"'OPT_NIPPLE'"'"'})
MERGE (gdp)-[:INCLUDES_FEATURE]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [26]: MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'})
SET gdb.name = '"'"'GDB Kanalfilterskåp'"'"',
    gdb.type = '"'"'Bag Filter Housing'"'"',
    gdb.desc = '"'"'Uninsulated housing for bag/compact filters'"'"',
    gdb.page_ref = 8,
    gdb.selection_priority = 15,
    gdb.code_format = '"'"'{family}-{width}x{height}-{length}-R-PG-{material}'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [27]: MERGE (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'})
SET gdb.na..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (mat:Material {id: '"'"'MAT_FZ'"'"'})
MERGE (gdb)-[:AVAILABLE_IN_MATERIAL {is_default: true}]->(mat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [28]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (mat:Mate..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (mat:Material {id: '"'"'MAT_AZ'"'"'})
MERGE (gdb)-[:AVAILABLE_IN_MATERIAL]->(mat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [29]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (mat:Mate..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (mat:Material {id: '"'"'MAT_RF'"'"'})
MERGE (gdb)-[:AVAILABLE_IN_MATERIAL]->(mat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [30]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (mat:Mate..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Option {id: '"'"'OPT_DOOR_R'"'"'})
MERGE (gdb)-[:HAS_DEFAULT_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [31]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Option {id: '"'"'OPT_DOOR_L'"'"'})
MERGE (gdb)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [32]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Option {id: '"'"'OPT_CONN_PG'"'"'})
MERGE (gdb)-[:HAS_DEFAULT_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [33]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Option {id: '"'"'OPT_CONN_FL'"'"'})
MERGE (gdb)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [34]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Option {id: '"'"'OPT_NIPPLE'"'"'})
MERGE (gdb)-[:INCLUDES_FEATURE]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [35]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Option {id: '"'"'OPT_LOCK_EXL'"'"'})
MERGE (gdb)-[:INCLUDES_FEATURE]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [36]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'})
SET gdmi.name = '"'"'GDMI Modulfilterskåp'"'"',
    gdmi.type = '"'"'Insulated Filter Housing'"'"',
    gdmi.desc = '"'"'Double-walled insulated housing'"'"',
    gdmi.page_ref = 11,
    gdmi.selection_priority = 25,
    gdmi.code_format = '"'"'{family}-{width}x{height}-{length}-R-PG-{material}'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [37]: MERGE (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'})
SET gdmi..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (mat:Material {id: '"'"'MAT_ZM'"'"'})
MERGE (gdmi)-[:AVAILABLE_IN_MATERIAL {is_default: true}]->(mat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [38]: MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (mat:Ma..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (feat:Feature {id: '"'"'FEAT_INSUL'"'"'})
MERGE (gdmi)-[:INCLUDES_FEATURE]->(feat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [39]: MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (feat:F..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (opt:Option {id: '"'"'OPT_LOCK_EXL'"'"'})
MERGE (gdmi)-[:INCLUDES_FEATURE]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [40]: MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (opt:Op..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'})
SET gdc.name = '"'"'GDC Patronfilterskåp'"'"',
    gdc.type = '"'"'Carbon Cartridge Housing'"'"',
    gdc.desc = '"'"'Housing for carbon cartridges with bayonet mount'"'"',
    gdc.page_ref = 14,
    gdc.selection_priority = 20,
    gdc.code_format = '"'"'{family}-{width}x{height}-{length}-R-PG-{material}'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [41]: MERGE (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'})
SET gdc.na..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (mat:Material {id: '"'"'MAT_FZ'"'"'})
MERGE (gdc)-[:AVAILABLE_IN_MATERIAL {is_default: true}]->(mat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [42]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (mat:Mate..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (mat:Material {id: '"'"'MAT_AZ'"'"'})
MERGE (gdc)-[:AVAILABLE_IN_MATERIAL]->(mat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [43]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (mat:Mate..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (mat:Material {id: '"'"'MAT_RF'"'"'})
MERGE (gdc)-[:AVAILABLE_IN_MATERIAL]->(mat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [44]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (mat:Mate..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (opt:Option {id: '"'"'OPT_DOOR_L'"'"'})
MERGE (gdc)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [45]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (opt:Option {id: '"'"'OPT_NIPPLE'"'"'})
MERGE (gdc)-[:INCLUDES_FEATURE]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [46]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (gdc_flex:ProductFamily {id: '"'"'FAM_GDC_FLEX'"'"'})
SET gdc_flex.name = '"'"'GDC FLEX'"'"',
    gdc_flex.type = '"'"'Carbon Housing with Rail'"'"',
    gdc_flex.desc = '"'"'Carbon housing with extractable rail'"'"',
    gdc_flex.page_ref = 16,
    gdc_flex.selection_priority = 22,
    gdc_flex.code_format = '"'"'{family}-{width}x{height}-{length}-R-PG-{material}'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [47]: MERGE (gdc_flex:ProductFamily {id: '"'"'FAM_GDC_FLEX'"'"'})
..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc_flex:ProductFamily {id: '"'"'FAM_GDC_FLEX'"'"'}), (mat:Material {id: '"'"'MAT_FZ'"'"'})
MERGE (gdc_flex)-[:AVAILABLE_IN_MATERIAL]->(mat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [48]: MATCH (gdc_flex:ProductFamily {id: '"'"'FAM_GDC_FLEX'"'"'}),..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc_flex:ProductFamily {id: '"'"'FAM_GDC_FLEX'"'"'}), (feat:Feature {id: '"'"'FEAT_RAIL'"'"'})
MERGE (gdc_flex)-[:INCLUDES_FEATURE]->(feat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [49]: MATCH (gdc_flex:ProductFamily {id: '"'"'FAM_GDC_FLEX'"'"'}),..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (pff:ProductFamily {id: '"'"'FAM_PFF'"'"'})
SET pff.name = '"'"'PFF Planfilterram'"'"',
    pff.type = '"'"'Mounting Frame'"'"',
    pff.selection_priority = 50,
    pff.code_format = '"'"'{family}-{width}x{height}'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [50]: MERGE (pff:ProductFamily {id: '"'"'FAM_PFF'"'"'})
SET pff.na..."; fi
echo "Progress: 50/243"
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (len_gdp:VariantLength {id: '"'"'LEN_GDP_250'"'"'})
SET len_gdp.mm = 250, len_gdp.desc = '"'"'Standard length'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [51]: MERGE (len_gdp:VariantLength {id: '"'"'LEN_GDP_250'"'"'})
SE..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (len:VariantLength {id: '"'"'LEN_GDP_250'"'"'})
MERGE (gdp)-[:HAS_LENGTH_VARIANT {is_default: true}]->(len)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [52]: MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (len:Vari..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (len_gdb_s:VariantLength {id: '"'"'LEN_GDB_550'"'"'})
SET len_gdb_s.mm = 550, len_gdb_s.desc = '"'"'For short bag filters'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [53]: MERGE (len_gdb_s:VariantLength {id: '"'"'LEN_GDB_550'"'"'})
..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (len_gdb_l:VariantLength {id: '"'"'LEN_GDB_750'"'"'})
SET len_gdb_l.mm = 750, len_gdb_l.desc = '"'"'For long bag filters/compact'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [54]: MERGE (len_gdb_l:VariantLength {id: '"'"'LEN_GDB_750'"'"'})
..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (len:VariantLength {id: '"'"'LEN_GDB_550'"'"'})
MERGE (gdb)-[:HAS_LENGTH_VARIANT]->(len)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [55]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (len:Vari..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (len:VariantLength {id: '"'"'LEN_GDB_750'"'"'})
MERGE (gdb)-[:HAS_LENGTH_VARIANT {is_default: true}]->(len)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [56]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (len:Vari..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (len_gdmi_s:VariantLength {id: '"'"'LEN_GDMI_600'"'"'})
SET len_gdmi_s.mm = 600, len_gdmi_s.desc = '"'"'For short filters (Insulated)'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [57]: MERGE (len_gdmi_s:VariantLength {id: '"'"'LEN_GDMI_600'"'"'}..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (len_gdmi_l:VariantLength {id: '"'"'LEN_GDMI_850'"'"'})
SET len_gdmi_l.mm = 850, len_gdmi_l.desc = '"'"'For long filters (Insulated)'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [58]: MERGE (len_gdmi_l:VariantLength {id: '"'"'LEN_GDMI_850'"'"'}..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (len:VariantLength {id: '"'"'LEN_GDMI_600'"'"'})
MERGE (gdmi)-[:HAS_LENGTH_VARIANT]->(len)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [59]: MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (len:Va..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (len:VariantLength {id: '"'"'LEN_GDMI_850'"'"'})
MERGE (gdmi)-[:HAS_LENGTH_VARIANT]->(len)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [60]: MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (len:Va..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (len_gdc_s:VariantLength {id: '"'"'LEN_GDC_750'"'"'})
SET len_gdc_s.mm = 750, len_gdc_s.desc = '"'"'For 450mm cylinders'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [61]: MERGE (len_gdc_s:VariantLength {id: '"'"'LEN_GDC_750'"'"'})
..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (len_gdc_l:VariantLength {id: '"'"'LEN_GDC_900'"'"'})
SET len_gdc_l.mm = 900, len_gdc_l.desc = '"'"'For 450mm cylinders + Police Filter OR 600mm cylinders'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [62]: MERGE (len_gdc_l:VariantLength {id: '"'"'LEN_GDC_900'"'"'})
..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (len:VariantLength {id: '"'"'LEN_GDC_750'"'"'})
MERGE (gdc)-[:HAS_LENGTH_VARIANT]->(len)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [63]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (len:Vari..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (len:VariantLength {id: '"'"'LEN_GDC_900'"'"'})
MERGE (gdc)-[:HAS_LENGTH_VARIANT]->(len)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [64]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (len:Vari..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d1:DimensionModule {id: '"'"'DIM_300x300'"'"'})
SET d1.width_mm = 300, d1.height_mm = 300, d1.reference_airflow_m3h = 850, d1.label = '"'"'300x300 mm'"'"',
    d1.unit_weight_kg = 13, d1.weight_per_mm_length = 0.01, d1.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [65]: MERGE (d1:DimensionModule {id: '"'"'DIM_300x300'"'"'})
SET d..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d2:DimensionModule {id: '"'"'DIM_300x600'"'"'})
SET d2.width_mm = 300, d2.height_mm = 600, d2.reference_airflow_m3h = 1700, d2.label = '"'"'300x600 mm'"'"',
    d2.unit_weight_kg = 20, d2.weight_per_mm_length = 0.02, d2.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [66]: MERGE (d2:DimensionModule {id: '"'"'DIM_300x600'"'"'})
SET d..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d3:DimensionModule {id: '"'"'DIM_600x300'"'"'})
SET d3.width_mm = 600, d3.height_mm = 300, d3.reference_airflow_m3h = 1700, d3.label = '"'"'600x300 mm'"'"',
    d3.unit_weight_kg = 20, d3.weight_per_mm_length = 0.02, d3.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [67]: MERGE (d3:DimensionModule {id: '"'"'DIM_600x300'"'"'})
SET d..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d4:DimensionModule {id: '"'"'DIM_600x600'"'"'})
SET d4.width_mm = 600, d4.height_mm = 600, d4.reference_airflow_m3h = 3400, d4.label = '"'"'600x600 mm'"'"',
    d4.unit_weight_kg = 27, d4.weight_per_mm_length = 0.03, d4.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [68]: MERGE (d4:DimensionModule {id: '"'"'DIM_600x600'"'"'})
SET d..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d5:DimensionModule {id: '"'"'DIM_600x900'"'"'})
SET d5.width_mm = 600, d5.height_mm = 900, d5.reference_airflow_m3h = 5100, d5.label = '"'"'600x900 mm'"'"',
    d5.unit_weight_kg = 34, d5.weight_per_mm_length = 0.04, d5.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [69]: MERGE (d5:DimensionModule {id: '"'"'DIM_600x900'"'"'})
SET d..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d6:DimensionModule {id: '"'"'DIM_900x600'"'"'})
SET d6.width_mm = 900, d6.height_mm = 600, d6.reference_airflow_m3h = 5100, d6.label = '"'"'900x600 mm'"'"',
    d6.unit_weight_kg = 34, d6.weight_per_mm_length = 0.04, d6.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [70]: MERGE (d6:DimensionModule {id: '"'"'DIM_900x600'"'"'})
SET d..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d7:DimensionModule {id: '"'"'DIM_600x1200'"'"'})
SET d7.width_mm = 600, d7.height_mm = 1200, d7.reference_airflow_m3h = 6800, d7.label = '"'"'600x1200 mm'"'"',
    d7.unit_weight_kg = 40, d7.weight_per_mm_length = 0.05, d7.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [71]: MERGE (d7:DimensionModule {id: '"'"'DIM_600x1200'"'"'})
SET ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d8:DimensionModule {id: '"'"'DIM_1200x600'"'"'})
SET d8.width_mm = 1200, d8.height_mm = 600, d8.reference_airflow_m3h = 6800, d8.label = '"'"'1200x600 mm'"'"',
    d8.unit_weight_kg = 40, d8.weight_per_mm_length = 0.05, d8.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [72]: MERGE (d8:DimensionModule {id: '"'"'DIM_1200x600'"'"'})
SET ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d9:DimensionModule {id: '"'"'DIM_900x900'"'"'})
SET d9.width_mm = 900, d9.height_mm = 900, d9.reference_airflow_m3h = 7650, d9.label = '"'"'900x900 mm'"'"',
    d9.unit_weight_kg = 45, d9.weight_per_mm_length = 0.06, d9.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [73]: MERGE (d9:DimensionModule {id: '"'"'DIM_900x900'"'"'})
SET d..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d10:DimensionModule {id: '"'"'DIM_900x1200'"'"'})
SET d10.width_mm = 900, d10.height_mm = 1200, d10.reference_airflow_m3h = 10200, d10.label = '"'"'900x1200 mm'"'"',
    d10.unit_weight_kg = 55, d10.weight_per_mm_length = 0.07, d10.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [74]: MERGE (d10:DimensionModule {id: '"'"'DIM_900x1200'"'"'})
SET..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d11:DimensionModule {id: '"'"'DIM_1200x900'"'"'})
SET d11.width_mm = 1200, d11.height_mm = 900, d11.reference_airflow_m3h = 10200, d11.label = '"'"'1200x900 mm'"'"',
    d11.unit_weight_kg = 55, d11.weight_per_mm_length = 0.07, d11.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [75]: MERGE (d11:DimensionModule {id: '"'"'DIM_1200x900'"'"'})
SET..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d12:DimensionModule {id: '"'"'DIM_1200x1200'"'"'})
SET d12.width_mm = 1200, d12.height_mm = 1200, d12.reference_airflow_m3h = 13600, d12.label = '"'"'1200x1200 mm'"'"',
    d12.unit_weight_kg = 70, d12.weight_per_mm_length = 0.09, d12.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [76]: MERGE (d12:DimensionModule {id: '"'"'DIM_1200x1200'"'"'})
SE..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d13:DimensionModule {id: '"'"'DIM_1500x600'"'"'})
SET d13.width_mm = 1500, d13.height_mm = 600, d13.reference_airflow_m3h = 8500, d13.label = '"'"'1500x600 mm'"'"',
    d13.unit_weight_kg = 48, d13.weight_per_mm_length = 0.06, d13.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [77]: MERGE (d13:DimensionModule {id: '"'"'DIM_1500x600'"'"'})
SET..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (d14:DimensionModule {id: '"'"'DIM_1800x600'"'"'})
SET d14.width_mm = 1800, d14.height_mm = 600, d14.reference_airflow_m3h = 10200, d14.label = '"'"'1800x600 mm'"'"',
    d14.unit_weight_kg = 55, d14.weight_per_mm_length = 0.07, d14.reference_length_mm = 550' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [78]: MERGE (d14:DimensionModule {id: '"'"'DIM_1800x600'"'"'})
SET..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (d:DimensionModule), (f:ProductFamily)
WHERE f.id IN ['"'"'FAM_GDP'"'"', '"'"'FAM_GDB'"'"', '"'"'FAM_GDC'"'"', '"'"'FAM_GDMI'"'"', '"'"'FAM_GDC_FLEX'"'"']
MERGE (f)-[:AVAILABLE_IN_SIZE]->(d)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [79]: MATCH (d:DimensionModule), (f:ProductFamily)
WHERE f.id IN [..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (d:DimensionModule), (pff:ProductFamily {id: '"'"'FAM_PFF'"'"'})
WHERE d.width_mm <= 1500 AND d.height_mm <= 1500
MERGE (pff)-[:AVAILABLE_IN_SIZE]->(d)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [80]: MATCH (d:DimensionModule), (pff:ProductFamily {id: '"'"'FAM_..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_polisfilter:Option {id: '"'"'OPT_POLISFILTER'"'"'})
SET opt_polisfilter.name = '"'"'Förmonterad filterskena för polisfilter'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [81]: MERGE (opt_polisfilter:Option {id: '"'"'OPT_POLISFILTER'"'"'..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (opt:Option {id: '"'"'OPT_POLISFILTER'"'"'})
MERGE (gdc)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [82]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (opt:Opti..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (opt:Option {id: '"'"'OPT_POLISFILTER'"'"'}), (len:VariantLength {id: '"'"'LEN_GDC_900'"'"'})
MERGE (opt)-[:REQUIRES_VARIANT]->(len)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [83]: MATCH (opt:Option {id: '"'"'OPT_POLISFILTER'"'"'}), (len:Var..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (a:Application) REQUIRE a.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [84]: CREATE CONSTRAINT IF NOT EXISTS FOR (a:Application) REQUIRE ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (r:Risk) REQUIRE r.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [85]: CREATE CONSTRAINT IF NOT EXISTS FOR (r:Risk) REQUIRE r.id IS..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (reg:Regulation) REQUIRE reg.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [86]: CREATE CONSTRAINT IF NOT EXISTS FOR (reg:Regulation) REQUIRE..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (s:Substance) REQUIRE s.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [87]: CREATE CONSTRAINT IF NOT EXISTS FOR (s:Substance) REQUIRE s...."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (req:Requirement) REQUIRE req.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [88]: CREATE CONSTRAINT IF NOT EXISTS FOR (req:Requirement) REQUIR..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (app_hosp:Application {id: '"'"'APP_HOSPITAL'"'"'})
SET app_hosp.name = '"'"'Hospital'"'"',
    app_hosp.keywords = ['"'"'hospital'"'"', '"'"'szpital'"'"', '"'"'medical'"'"', '"'"'clinic'"'"', '"'"'surgery'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [89]: MERGE (app_hosp:Application {id: '"'"'APP_HOSPITAL'"'"'})
SE..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (app_pool:Application {id: '"'"'APP_POOL'"'"'})
SET app_pool.name = '"'"'Swimming Pool'"'"',
    app_pool.keywords = ['"'"'pool'"'"', '"'"'basen'"'"', '"'"'aquapark'"'"', '"'"'chlorine'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [90]: MERGE (app_pool:Application {id: '"'"'APP_POOL'"'"'})
SET ap..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (app_paint:Application {id: '"'"'APP_PAINT'"'"'})
SET app_paint.name = '"'"'Paint Shop'"'"',
    app_paint.keywords = ['"'"'paint shop'"'"', '"'"'lakiernia'"'"', '"'"'malarnia'"'"', '"'"'spray booth'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [91]: MERGE (app_paint:Application {id: '"'"'APP_PAINT'"'"'})
SET ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (app_kitchen:Application {id: '"'"'APP_KITCHEN'"'"'})
SET app_kitchen.name = '"'"'Commercial Kitchen'"'"',
    app_kitchen.keywords = ['"'"'kitchen'"'"', '"'"'kuchnia'"'"', '"'"'restaurant'"'"', '"'"'fryer'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [92]: MERGE (app_kitchen:Application {id: '"'"'APP_KITCHEN'"'"'})
..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (app_marine:Application {id: '"'"'APP_MARINE'"'"'})
SET app_marine.name = '"'"'Marine/Offshore'"'"',
    app_marine.keywords = ['"'"'marine'"'"', '"'"'ship'"'"', '"'"'offshore'"'"', '"'"'sea'"'"', '"'"'salt'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [93]: MERGE (app_marine:Application {id: '"'"'APP_MARINE'"'"'})
SE..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (app_office:Application {id: '"'"'APP_OFFICE'"'"'})
SET app_office.name = '"'"'Office/Commercial'"'"',
    app_office.keywords = ['"'"'office'"'"', '"'"'biuro'"'"', '"'"'school'"'"', '"'"'shop'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [94]: MERGE (app_office:Application {id: '"'"'APP_OFFICE'"'"'})
SE..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (app_lab:Application {id: '"'"'APP_LAB'"'"'})
SET app_lab.name = '"'"'Laboratory'"'"',
    app_lab.keywords = ['"'"'lab'"'"', '"'"'pharma'"'"', '"'"'cleanroom'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [95]: MERGE (app_lab:Application {id: '"'"'APP_LAB'"'"'})
SET app_..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (env_out:Environment {id: '"'"'ENV_OUTDOOR'"'"'})
SET env_out.name = '"'"'Outdoor/Rooftop'"'"',
    env_out.keywords = ['"'"'outdoor'"'"', '"'"'roof'"'"', '"'"'dach'"'"', '"'"'zewnątrz'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [96]: MERGE (env_out:Environment {id: '"'"'ENV_OUTDOOR'"'"'})
SET ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (env_atex:Environment {id: '"'"'ENV_ATEX'"'"'})
SET env_atex.name = '"'"'ATEX Zone'"'"',
    env_atex.keywords = ['"'"'atex'"'"', '"'"'explosion'"'"', '"'"'ex zone'"'"', '"'"'wybuch'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [97]: MERGE (env_atex:Environment {id: '"'"'ENV_ATEX'"'"'})
SET en..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (env_indoor:Environment {id: '"'"'ENV_INDOOR'"'"'})
SET env_indoor.name = '"'"'Indoor'"'"',
    env_indoor.keywords = ['"'"'indoor'"'"', '"'"'inside'"'"', '"'"'interior'"'"', '"'"'wewnątrz'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [98]: MERGE (env_indoor:Environment {id: '"'"'ENV_INDOOR'"'"'})
SE..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (env_kitchen:Environment {id: '"'"'ENV_KITCHEN'"'"'})
SET env_kitchen.name = '"'"'Commercial Kitchen'"'"',
    env_kitchen.keywords = ['"'"'kitchen'"'"', '"'"'kuchnia'"'"', '"'"'restaurant'"'"', '"'"'fryer'"'"', '"'"'cooking'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [99]: MERGE (env_kitchen:Environment {id: '"'"'ENV_KITCHEN'"'"'})
..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (kitchen:Environment {id: '"'"'ENV_KITCHEN'"'"'})
MATCH (indoor:Environment {id: '"'"'ENV_INDOOR'"'"'})
MERGE (kitchen)-[:IS_A]->(indoor)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [100]: MATCH (kitchen:Environment {id: '"'"'ENV_KITCHEN'"'"'})
MATC..."; fi
echo "Progress: 100/243"
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (risk_grease:Risk {id: '"'"'RISK_GREASE'"'"'})
SET risk_grease.name = '"'"'Grease Contamination'"'"',
    risk_grease.description = '"'"'Lipid-laden exhaust permanently coats porous media'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [101]: MERGE (risk_grease:Risk {id: '"'"'RISK_GREASE'"'"'})
SET ris..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (kitchen:Environment {id: '"'"'ENV_KITCHEN'"'"'})
MATCH (risk:Risk {id: '"'"'RISK_GREASE'"'"'})
MERGE (kitchen)-[:HAS_RISK]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [102]: MATCH (kitchen:Environment {id: '"'"'ENV_KITCHEN'"'"'})
MATC..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (kitchen:Environment {id: '"'"'ENV_KITCHEN'"'"'})
MATCH (s:EnvironmentalStressor {id: '"'"'STRESSOR_GREASE_EXPOSURE'"'"'})
MERGE (kitchen)-[:EXPOSES_TO]->(s)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [103]: MATCH (kitchen:Environment {id: '"'"'ENV_KITCHEN'"'"'})
MATC..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (kitchen:Environment {id: '"'"'ENV_KITCHEN'"'"'})
MATCH (s:EnvironmentalStressor {id: '"'"'STRESSOR_CHEMICAL_VAPORS'"'"'})
MERGE (kitchen)-[:EXPOSES_TO]->(s)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [104]: MATCH (kitchen:Environment {id: '"'"'ENV_KITCHEN'"'"'})
MATC..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (sub_dust:Substance {id: '"'"'SUB_DUST'"'"'})
SET sub_dust.name = '"'"'Dust/Particulates'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [105]: MERGE (sub_dust:Substance {id: '"'"'SUB_DUST'"'"'})
SET sub_..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (sub_gas:Substance {id: '"'"'SUB_GAS'"'"'})
SET sub_gas.name = '"'"'Gas/Odors/VOCs'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [106]: MERGE (sub_gas:Substance {id: '"'"'SUB_GAS'"'"'})
SET sub_ga..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (sub_mist:Substance {id: '"'"'SUB_MIST'"'"'})
SET sub_mist.name = '"'"'Paint Overspray/Mist'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [107]: MERGE (sub_mist:Substance {id: '"'"'SUB_MIST'"'"'})
SET sub_..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (sub_grease:Substance {id: '"'"'SUB_GREASE'"'"'})
SET sub_grease.name = '"'"'Grease/Oil'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [108]: MERGE (sub_grease:Substance {id: '"'"'SUB_GREASE'"'"'})
SET ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (sub_water:Substance {id: '"'"'SUB_WATER'"'"'})
SET sub_water.name = '"'"'Condensation/Water'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [109]: MERGE (sub_water:Substance {id: '"'"'SUB_WATER'"'"'})
SET su..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (sub_salt:Substance {id: '"'"'SUB_SALT'"'"'})
SET sub_salt.name = '"'"'Salt Spray'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [110]: MERGE (sub_salt:Substance {id: '"'"'SUB_SALT'"'"'})
SET sub_..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (risk_clog:Risk {id: '"'"'RISK_CLOG'"'"'})
SET risk_clog.name = '"'"'Rapid Clogging'"'"',
    risk_clog.severity = '"'"'CRITICAL'"'"',
    risk_clog.desc = '"'"'Pores blocked immediately'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [111]: MERGE (risk_clog:Risk {id: '"'"'RISK_CLOG'"'"'})
SET risk_cl..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (risk_corr:Risk {id: '"'"'RISK_CORR'"'"'})
SET risk_corr.name = '"'"'Corrosion'"'"',
    risk_corr.severity = '"'"'HIGH'"'"',
    risk_corr.desc = '"'"'Structural failure due to rust'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [112]: MERGE (risk_corr:Risk {id: '"'"'RISK_CORR'"'"'})
SET risk_co..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (risk_hyg:Risk {id: '"'"'RISK_HYG'"'"'})
SET risk_hyg.name = '"'"'Hygiene Failure'"'"',
    risk_hyg.severity = '"'"'CRITICAL'"'"',
    risk_hyg.desc = '"'"'Bacterial growth/Contamination'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [113]: MERGE (risk_hyg:Risk {id: '"'"'RISK_HYG'"'"'})
SET risk_hyg...."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (risk_cond:Risk {id: '"'"'RISK_COND'"'"'})
SET risk_cond.name = '"'"'Condensation Damage'"'"',
    risk_cond.severity = '"'"'HIGH'"'"',
    risk_cond.desc = '"'"'Water damage inside housing'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [114]: MERGE (risk_cond:Risk {id: '"'"'RISK_COND'"'"'})
SET risk_co..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (risk_explo:Risk {id: '"'"'RISK_EXPLO'"'"'})
SET risk_explo.name = '"'"'Explosion'"'"',
    risk_explo.severity = '"'"'CRITICAL'"'"',
    risk_explo.desc = '"'"'Ignition of dust/gas mixture'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [115]: MERGE (risk_explo:Risk {id: '"'"'RISK_EXPLO'"'"'})
SET risk_..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (reg_vdi:Regulation {id: '"'"'REG_VDI6022'"'"'})
SET reg_vdi.name = '"'"'VDI 6022'"'"',
    reg_vdi.desc = '"'"'Hygiene requirements for HVAC systems'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [116]: MERGE (reg_vdi:Regulation {id: '"'"'REG_VDI6022'"'"'})
SET r..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (req_c5:Requirement {id: '"'"'REQ_C5'"'"'})
SET req_c5.name = '"'"'Corrosion Class C5'"'"',
    req_c5.desc = '"'"'High resistance for aggressive envs'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [117]: MERGE (req_c5:Requirement {id: '"'"'REQ_C5'"'"'})
SET req_c5..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (req_c5m:Requirement {id: '"'"'REQ_C5M'"'"'})
SET req_c5m.name = '"'"'Corrosion Class C5-M'"'"',
    req_c5m.desc = '"'"'Marine resistance'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [118]: MERGE (req_c5m:Requirement {id: '"'"'REQ_C5M'"'"'})
SET req_..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (req_cond:Requirement {id: '"'"'REQ_CONDUCTIVE'"'"'})
SET req_cond.name = '"'"'Conductive/Grounded'"'"',
    req_cond.desc = '"'"'Prevent static buildup'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [119]: MERGE (req_cond:Requirement {id: '"'"'REQ_CONDUCTIVE'"'"'})
..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (sol_prefilter:Solution {id: '"'"'SOL_PREFILTER'"'"'})
SET sol_prefilter.name = '"'"'Pre-filtration (F7/F9)'"'"',
    sol_prefilter.desc = '"'"'Protects carbon from dust/mist'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [120]: MERGE (sol_prefilter:Solution {id: '"'"'SOL_PREFILTER'"'"'})..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (sol_grease_sep:Solution {id: '"'"'SOL_GREASE_SEP'"'"'})
SET sol_grease_sep.name = '"'"'Grease Separator'"'"',
    sol_grease_sep.desc = '"'"'Removes oil mist before filters'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [121]: MERGE (sol_grease_sep:Solution {id: '"'"'SOL_GREASE_SEP'"'"'..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (sol_heater:Solution {id: '"'"'SOL_HEATER'"'"'})
SET sol_heater.name = '"'"'Pre-heater / Dehumidifier'"'"',
    sol_heater.desc = '"'"'Reduces relative humidity < 70%'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [122]: MERGE (sol_heater:Solution {id: '"'"'SOL_HEATER'"'"'})
SET s..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (sol_grounding:Solution {id: '"'"'SOL_GROUNDING'"'"'})
SET sol_grounding.name = '"'"'Grounding / ATEX Certification'"'"',
    sol_grounding.desc = '"'"'Prevents static sparks'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [123]: MERGE (sol_grounding:Solution {id: '"'"'SOL_GROUNDING'"'"'})..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (rule_vel:SizingRule {id: '"'"'RULE_VELOCITY'"'"'})
SET rule_vel.name = '"'"'Face Velocity Check'"'"',
    rule_vel.formula = '"'"'airflow_m3h / (width_m * height_m * 3600)'"'"',
    rule_vel.unit = '"'"'m/s'"'"',
    rule_vel.optimal_max = 2.5,
    rule_vel.warning_threshold = 3.0,
    rule_vel.critical_limit = 3.5,
    rule_vel.consequence = '"'"'High pressure drop, energy loss, filter damage risk'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [124]: MERGE (rule_vel:SizingRule {id: '"'"'RULE_VELOCITY'"'"'})
SE..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_HOSPITAL'"'"'}), (reg:Regulation {id: '"'"'REG_VDI6022'"'"'})
MERGE (app)-[:REQUIRES_COMPLIANCE]->(reg)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [125]: MATCH (app:Application {id: '"'"'APP_HOSPITAL'"'"'}), (reg:R..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_HOSPITAL'"'"'}), (req:Requirement {id: '"'"'REQ_C5'"'"'})
MERGE (app)-[:REQUIRES_RESISTANCE]->(req)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [126]: MATCH (app:Application {id: '"'"'APP_HOSPITAL'"'"'}), (req:R..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_HOSPITAL'"'"'}), (risk:Risk {id: '"'"'RISK_HYG'"'"'})
MERGE (app)-[:HAS_RISK]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [127]: MATCH (app:Application {id: '"'"'APP_HOSPITAL'"'"'}), (risk:..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_POOL'"'"'}), (sub:Substance {id: '"'"'SUB_SALT'"'"'})
MERGE (app)-[:GENERATES]->(sub)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [128]: MATCH (app:Application {id: '"'"'APP_POOL'"'"'}), (sub:Subst..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_POOL'"'"'}), (risk:Risk {id: '"'"'RISK_CORR'"'"'})
MERGE (app)-[:HAS_RISK]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [129]: MATCH (app:Application {id: '"'"'APP_POOL'"'"'}), (risk:Risk..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_POOL'"'"'}), (req:Requirement {id: '"'"'REQ_C5'"'"'})
MERGE (app)-[:REQUIRES_RESISTANCE]->(req)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [130]: MATCH (app:Application {id: '"'"'APP_POOL'"'"'}), (req:Requi..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_MARINE'"'"'}), (risk:Risk {id: '"'"'RISK_CORR'"'"'})
MERGE (app)-[:HAS_RISK]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [131]: MATCH (app:Application {id: '"'"'APP_MARINE'"'"'}), (risk:Ri..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_MARINE'"'"'}), (req:Requirement {id: '"'"'REQ_C5M'"'"'})
MERGE (app)-[:REQUIRES_RESISTANCE]->(req)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [132]: MATCH (app:Application {id: '"'"'APP_MARINE'"'"'}), (req:Req..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_PAINT'"'"'}), (sub:Substance {id: '"'"'SUB_MIST'"'"'})
MERGE (app)-[:GENERATES]->(sub)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [133]: MATCH (app:Application {id: '"'"'APP_PAINT'"'"'}), (sub:Subs..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_PAINT'"'"'}), (sub:Substance {id: '"'"'SUB_GAS'"'"'})
MERGE (app)-[:GENERATES]->(sub)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [134]: MATCH (app:Application {id: '"'"'APP_PAINT'"'"'}), (sub:Subs..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_PAINT'"'"'}), (env:Environment {id: '"'"'ENV_ATEX'"'"'})
MERGE (app)-[:MAY_BE_ENVIRONMENT]->(env)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [135]: MATCH (app:Application {id: '"'"'APP_PAINT'"'"'}), (env:Envi..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_KITCHEN'"'"'}), (sub:Substance {id: '"'"'SUB_GREASE'"'"'})
MERGE (app)-[:GENERATES]->(sub)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [136]: MATCH (app:Application {id: '"'"'APP_KITCHEN'"'"'}), (sub:Su..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (app:Application {id: '"'"'APP_KITCHEN'"'"'}), (sub:Substance {id: '"'"'SUB_WATER'"'"'})
MERGE (app)-[:GENERATES]->(sub)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [137]: MATCH (app:Application {id: '"'"'APP_KITCHEN'"'"'}), (sub:Su..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (env:Environment {id: '"'"'ENV_OUTDOOR'"'"'}), (sub:Substance {id: '"'"'SUB_WATER'"'"'})
MERGE (env)-[:GENERATES]->(sub)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [138]: MATCH (env:Environment {id: '"'"'ENV_OUTDOOR'"'"'}), (sub:Su..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (env:Environment {id: '"'"'ENV_OUTDOOR'"'"'}), (risk:Risk {id: '"'"'RISK_COND'"'"'})
MERGE (env)-[:HAS_RISK]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [139]: MATCH (env:Environment {id: '"'"'ENV_OUTDOOR'"'"'}), (risk:R..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (sub:Substance {id: '"'"'SUB_MIST'"'"'})
MERGE (gdc)-[r:VULNERABLE_TO]->(sub)
SET r.reason = '"'"'Pores blocked by particulates'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [140]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (sub:Subs..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (sub:Substance {id: '"'"'SUB_GREASE'"'"'})
MERGE (gdc)-[r:VULNERABLE_TO]->(sub)
SET r.reason = '"'"'Pores blocked by lipids'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [141]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (sub:Subs..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (risk:Risk {id: '"'"'RISK_CLOG'"'"'})
MERGE (gdc)-[:PRONE_TO]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [142]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (risk:Ris..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (sub:Substance {id: '"'"'SUB_GAS'"'"'})
MERGE (gdb)-[:INEFFECTIVE_AGAINST]->(sub)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [143]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (sub:Subs..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (risk:Risk {id: '"'"'RISK_COND'"'"'})
MERGE (gdmi)-[:PROTECTS_AGAINST]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [144]: MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (risk:R..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (env:Environment {id: '"'"'ENV_OUTDOOR'"'"'})
MERGE (gdmi)-[:SUITABLE_FOR]->(env)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [145]: MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (env:En..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (risk:Risk {id: '"'"'RISK_COND'"'"'})
MERGE (gdb)-[:VULNERABLE_TO]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [146]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (risk:Ris..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (risk:Risk {id: '"'"'RISK_COND'"'"'})
MERGE (gdp)-[:VULNERABLE_TO]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [147]: MATCH (gdp:ProductFamily {id: '"'"'FAM_GDP'"'"'}), (risk:Ris..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (risk:Risk {id: '"'"'RISK_COND'"'"'})
MERGE (gdc)-[:VULNERABLE_TO]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [148]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (risk:Ris..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (rf:Material {id: '"'"'MAT_RF'"'"'}), (req:Requirement {id: '"'"'REQ_C5'"'"'})
MERGE (rf)-[:MEETS_REQUIREMENT]->(req)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [149]: MATCH (rf:Material {id: '"'"'MAT_RF'"'"'}), (req:Requirement..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (sf:Material {id: '"'"'MAT_SF'"'"'}), (req:Requirement {id: '"'"'REQ_C5'"'"'})
MERGE (sf)-[:MEETS_REQUIREMENT]->(req)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [150]: MATCH (sf:Material {id: '"'"'MAT_SF'"'"'}), (req:Requirement..."; fi
echo "Progress: 150/243"
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (sf:Material {id: '"'"'MAT_SF'"'"'}), (req:Requirement {id: '"'"'REQ_C5M'"'"'})
MERGE (sf)-[:MEETS_REQUIREMENT]->(req)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [151]: MATCH (sf:Material {id: '"'"'MAT_SF'"'"'}), (req:Requirement..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (rf:Material {id: '"'"'MAT_RF'"'"'}), (reg:Regulation {id: '"'"'REG_VDI6022'"'"'})
MERGE (rf)-[:COMPLIES_WITH]->(reg)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [152]: MATCH (rf:Material {id: '"'"'MAT_RF'"'"'}), (reg:Regulation ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (fz:Material {id: '"'"'MAT_FZ'"'"'}), (risk:Risk {id: '"'"'RISK_CORR'"'"'})
MERGE (fz)-[:VULNERABLE_TO]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [153]: MATCH (fz:Material {id: '"'"'MAT_FZ'"'"'}), (risk:Risk {id: ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (sub:Substance {id: '"'"'SUB_MIST'"'"'}), (risk:Risk {id: '"'"'RISK_CLOG'"'"'})
MERGE (sub)-[:CAUSES]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [154]: MATCH (sub:Substance {id: '"'"'SUB_MIST'"'"'}), (risk:Risk {..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (sub:Substance {id: '"'"'SUB_GREASE'"'"'}), (risk:Risk {id: '"'"'RISK_CLOG'"'"'})
MERGE (sub)-[:CAUSES]->(risk)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [155]: MATCH (sub:Substance {id: '"'"'SUB_GREASE'"'"'}), (risk:Risk..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (risk:Risk {id: '"'"'RISK_CLOG'"'"'}), (sol:Solution {id: '"'"'SOL_PREFILTER'"'"'})
MERGE (risk)-[:MITIGATED_BY]->(sol)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [156]: MATCH (risk:Risk {id: '"'"'RISK_CLOG'"'"'}), (sol:Solution {..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (risk:Risk {id: '"'"'RISK_CLOG'"'"'}), (sol:Solution {id: '"'"'SOL_GREASE_SEP'"'"'})
MERGE (risk)-[:MITIGATED_BY]->(sol)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [157]: MATCH (risk:Risk {id: '"'"'RISK_CLOG'"'"'}), (sol:Solution {..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (risk:Risk {id: '"'"'RISK_EXPLO'"'"'}), (sol:Solution {id: '"'"'SOL_GROUNDING'"'"'})
MERGE (risk)-[:MITIGATED_BY]->(sol)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [158]: MATCH (risk:Risk {id: '"'"'RISK_EXPLO'"'"'}), (sol:Solution ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (p:ProductFamily), (rule:SizingRule {id: '"'"'RULE_VELOCITY'"'"'})
WHERE p.id IN ['"'"'FAM_GDB'"'"', '"'"'FAM_GDC'"'"', '"'"'FAM_GDMI'"'"', '"'"'FAM_GDP'"'"']
MERGE (p)-[:HAS_SIZING_RULE]->(rule)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [159]: MATCH (p:ProductFamily), (rule:SizingRule {id: '"'"'RULE_VEL..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (q:Question) REQUIRE q.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [160]: CREATE CONSTRAINT IF NOT EXISTS FOR (q:Question) REQUIRE q.i..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (param:Parameter) REQUIRE param.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [161]: CREATE CONSTRAINT IF NOT EXISTS FOR (param:Parameter) REQUIR..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (strat:Strategy) REQUIRE strat.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [162]: CREATE CONSTRAINT IF NOT EXISTS FOR (strat:Strategy) REQUIRE..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (rule:ClarificationRule) REQUIRE rule.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [163]: CREATE CONSTRAINT IF NOT EXISTS FOR (rule:ClarificationRule)..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (param_flow:Parameter {id: '"'"'PARAM_AIRFLOW'"'"'})
SET param_flow.name = '"'"'Airflow'"'"',
    param_flow.type = '"'"'Numeric'"'"',
    param_flow.unit = '"'"'m3/h'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [164]: MERGE (param_flow:Parameter {id: '"'"'PARAM_AIRFLOW'"'"'})
S..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (q_flow:Question {id: '"'"'Q_AIRFLOW'"'"'})
SET q_flow.text = '"'"'What is the required airflow capacity (m³/h)?'"'"',
    q_flow.intent = '"'"'sizing'"'"',
    q_flow.priority = 1' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [165]: MERGE (q_flow:Question {id: '"'"'Q_AIRFLOW'"'"'})
SET q_flow..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (p:Parameter {id: '"'"'PARAM_AIRFLOW'"'"'}), (q:Question {id: '"'"'Q_AIRFLOW'"'"'})
MERGE (p)-[:ASKED_VIA]->(q)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [166]: MATCH (p:Parameter {id: '"'"'PARAM_AIRFLOW'"'"'}), (q:Questi..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (param_dim:Parameter {id: '"'"'PARAM_DIMS'"'"'})
SET param_dim.name = '"'"'Duct Dimensions'"'"',
    param_dim.type = '"'"'Dimensions'"'"',
    param_dim.unit = '"'"'mm'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [167]: MERGE (param_dim:Parameter {id: '"'"'PARAM_DIMS'"'"'})
SET p..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (q_dim:Question {id: '"'"'Q_DIMS'"'"'})
SET q_dim.text = '"'"'What are the duct connection dimensions (Width x Height)?'"'"',
    q_dim.intent = '"'"'sizing'"'"',
    q_dim.priority = 1' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [168]: MERGE (q_dim:Question {id: '"'"'Q_DIMS'"'"'})
SET q_dim.text..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (p:Parameter {id: '"'"'PARAM_DIMS'"'"'}), (q:Question {id: '"'"'Q_DIMS'"'"'})
MERGE (p)-[:ASKED_VIA]->(q)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [169]: MATCH (p:Parameter {id: '"'"'PARAM_DIMS'"'"'}), (q:Question ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (param_atex:Parameter {id: '"'"'PARAM_ATEX'"'"'})
SET param_atex.name = '"'"'ATEX Zone'"'"',
    param_atex.type = '"'"'Selection'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [170]: MERGE (param_atex:Parameter {id: '"'"'PARAM_ATEX'"'"'})
SET ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (q_atex:Question {id: '"'"'Q_ATEX'"'"'})
SET q_atex.text = '"'"'Is this installation located in an ATEX explosion zone? If so, which zone?'"'"',
    q_atex.intent = '"'"'safety'"'"',
    q_atex.priority = 10' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [171]: MERGE (q_atex:Question {id: '"'"'Q_ATEX'"'"'})
SET q_atex.te..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (p:Parameter {id: '"'"'PARAM_ATEX'"'"'}), (q:Question {id: '"'"'Q_ATEX'"'"'})
MERGE (p)-[:ASKED_VIA]->(q)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [172]: MATCH (p:Parameter {id: '"'"'PARAM_ATEX'"'"'}), (q:Question ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (param_chem:Parameter {id: '"'"'PARAM_CHEM'"'"'})
SET param_chem.name = '"'"'Contaminant Type'"'"',
    param_chem.type = '"'"'Text'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [173]: MERGE (param_chem:Parameter {id: '"'"'PARAM_CHEM'"'"'})
SET ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (q_chem:Question {id: '"'"'Q_CHEM'"'"'})
SET q_chem.text = '"'"'To select the correct carbon media, what specific solvents or gases need to be filtered?'"'"',
    q_chem.intent = '"'"'engineering'"'"',
    q_chem.priority = 5' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [174]: MERGE (q_chem:Question {id: '"'"'Q_CHEM'"'"'})
SET q_chem.te..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (p:Parameter {id: '"'"'PARAM_CHEM'"'"'}), (q:Question {id: '"'"'Q_CHEM'"'"'})
MERGE (p)-[:ASKED_VIA]->(q)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [175]: MATCH (p:Parameter {id: '"'"'PARAM_CHEM'"'"'}), (q:Question ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (param_cond:Parameter {id: '"'"'PARAM_COND'"'"'})
SET param_cond.name = '"'"'Process Conditions'"'"',
    param_cond.type = '"'"'Text'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [176]: MERGE (param_cond:Parameter {id: '"'"'PARAM_COND'"'"'})
SET ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (q_cond:Question {id: '"'"'Q_COND'"'"'})
SET q_cond.text = '"'"'What is the operating temperature and relative humidity?'"'"',
    q_cond.intent = '"'"'engineering'"'"',
    q_cond.priority = 5' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [177]: MERGE (q_cond:Question {id: '"'"'Q_COND'"'"'})
SET q_cond.te..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (p:Parameter {id: '"'"'PARAM_COND'"'"'}), (q:Question {id: '"'"'Q_COND'"'"'})
MERGE (p)-[:ASKED_VIA]->(q)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [178]: MATCH (p:Parameter {id: '"'"'PARAM_COND'"'"'}), (q:Question ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (param_install:Parameter {id: '"'"'PARAM_INSTALL'"'"'})
SET param_install.name = '"'"'Installation Location'"'"',
    param_install.type = '"'"'Selection'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [179]: MERGE (param_install:Parameter {id: '"'"'PARAM_INSTALL'"'"'}..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (q_install:Question {id: '"'"'Q_INSTALL'"'"'})
SET q_install.text = '"'"'Will this unit be installed indoors or outdoors?'"'"',
    q_install.intent = '"'"'engineering'"'"',
    q_install.priority = 8' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [180]: MERGE (q_install:Question {id: '"'"'Q_INSTALL'"'"'})
SET q_i..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (p:Parameter {id: '"'"'PARAM_INSTALL'"'"'}), (q:Question {id: '"'"'Q_INSTALL'"'"'})
MERGE (p)-[:ASKED_VIA]->(q)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [181]: MATCH (p:Parameter {id: '"'"'PARAM_INSTALL'"'"'}), (q:Questi..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (pf:ProductFamily), (param_flow:Parameter {id: '"'"'PARAM_AIRFLOW'"'"'}), (param_dim:Parameter {id: '"'"'PARAM_DIMS'"'"'})
WHERE pf.id IN ['"'"'FAM_GDB'"'"', '"'"'FAM_GDC'"'"', '"'"'FAM_GDP'"'"', '"'"'FAM_GDMI'"'"', '"'"'FAM_GDC_FLEX'"'"']
MERGE (pf)-[:REQUIRES_PARAMETER {reason: '"'"'Sizing logic'"'"'}]->(param_flow)
MERGE (pf)-[:REQUIRES_PARAMETER {reason: '"'"'Physical fit'"'"'}]->(param_dim)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [182]: MATCH (pf:ProductFamily), (param_flow:Parameter {id: '"'"'PA..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (rule_paint_gdc:ClarificationRule {id: '"'"'RULE_PAINT_GDC_CHEM'"'"'})
SET rule_paint_gdc.name = '"'"'Paint Shop Solvents'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [183]: MERGE (rule_paint_gdc:ClarificationRule {id: '"'"'RULE_PAINT..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (rule:ClarificationRule {id: '"'"'RULE_PAINT_GDC_CHEM'"'"'}),
      (app:Application {id: '"'"'APP_PAINT'"'"'}),
      (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}),
      (param:Parameter {id: '"'"'PARAM_CHEM'"'"'})
MERGE (rule)-[:TRIGGERED_BY_CONTEXT]->(app)
MERGE (rule)-[:APPLIES_TO_PRODUCT]->(gdc)
MERGE (rule)-[:DEMANDS_PARAMETER]->(param)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [184]: MATCH (rule:ClarificationRule {id: '"'"'RULE_PAINT_GDC_CHEM'..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (rule_paint_atex:ClarificationRule {id: '"'"'RULE_PAINT_ATEX'"'"'})
SET rule_paint_atex.name = '"'"'Paint Shop Explosion Risk'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [185]: MERGE (rule_paint_atex:ClarificationRule {id: '"'"'RULE_PAIN..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (rule:ClarificationRule {id: '"'"'RULE_PAINT_ATEX'"'"'}),
      (app:Application {id: '"'"'APP_PAINT'"'"'}),
      (param:Parameter {id: '"'"'PARAM_ATEX'"'"'})
MERGE (rule)-[:TRIGGERED_BY_CONTEXT]->(app)
MERGE (rule)-[:DEMANDS_PARAMETER]->(param)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [186]: MATCH (rule:ClarificationRule {id: '"'"'RULE_PAINT_ATEX'"'"'..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (rule:ClarificationRule {id: '"'"'RULE_PAINT_ATEX'"'"'}), (pf:ProductFamily)
WHERE pf.id IN ['"'"'FAM_GDB'"'"', '"'"'FAM_GDC'"'"', '"'"'FAM_GDP'"'"', '"'"'FAM_GDMI'"'"', '"'"'FAM_GDC_FLEX'"'"']
MERGE (rule)-[:APPLIES_TO_PRODUCT]->(pf)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [187]: MATCH (rule:ClarificationRule {id: '"'"'RULE_PAINT_ATEX'"'"'..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (rule_outdoor:ClarificationRule {id: '"'"'RULE_OUTDOOR_CHECK'"'"'})
SET rule_outdoor.name = '"'"'Outdoor Insulation Check'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [188]: MERGE (rule_outdoor:ClarificationRule {id: '"'"'RULE_OUTDOOR..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (rule:ClarificationRule {id: '"'"'RULE_OUTDOOR_CHECK'"'"'}),
      (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}),
      (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}),
      (param:Parameter {id: '"'"'PARAM_INSTALL'"'"'})
MERGE (rule)-[:APPLIES_TO_PRODUCT]->(gdb)
MERGE (rule)-[:APPLIES_TO_PRODUCT]->(gdc)
MERGE (rule)-[:DEMANDS_PARAMETER]->(param)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [189]: MATCH (rule:ClarificationRule {id: '"'"'RULE_OUTDOOR_CHECK'"..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (strat_warn:Strategy {id: '"'"'STRAT_WARN_AND_CONFIRM'"'"'})
SET strat_warn.name = '"'"'Warn and Confirm'"'"',
    strat_warn.action = '"'"'DISPLAY_WARNING'"'"',
    strat_warn.instruction = '"'"'Display the identified risk clearly. Ask user to confirm if they accept the risk or want an alternative.'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [190]: MERGE (strat_warn:Strategy {id: '"'"'STRAT_WARN_AND_CONFIRM'..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (strat_block:Strategy {id: '"'"'STRAT_BLOCK'"'"'})
SET strat_block.name = '"'"'Hard Block'"'"',
    strat_block.action = '"'"'REFUSE_CONFIGURATION'"'"',
    strat_block.instruction = '"'"'State that the configuration is technically unsafe/impossible. Do not provide a quote. Suggest the correct alternative.'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [191]: MERGE (strat_block:Strategy {id: '"'"'STRAT_BLOCK'"'"'})
SET..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (strat_upsell:Strategy {id: '"'"'STRAT_UPSELL'"'"'})
SET strat_upsell.name = '"'"'Upsell / Cross-sell'"'"',
    strat_upsell.action = '"'"'SUGGEST_ADDON'"'"',
    strat_upsell.instruction = '"'"'Suggest compatible accessories that improve functionality.'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [192]: MERGE (strat_upsell:Strategy {id: '"'"'STRAT_UPSELL'"'"'})
S..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (r:Risk), (strat:Strategy {id: '"'"'STRAT_BLOCK'"'"'})
WHERE r.severity = '"'"'CRITICAL'"'"'
MERGE (r)-[:TRIGGERS_STRATEGY]->(strat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [193]: MATCH (r:Risk), (strat:Strategy {id: '"'"'STRAT_BLOCK'"'"'})..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (r:Risk), (strat:Strategy {id: '"'"'STRAT_WARN_AND_CONFIRM'"'"'})
WHERE r.severity = '"'"'HIGH'"'"'
MERGE (r)-[:TRIGGERS_STRATEGY]->(strat)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [194]: MATCH (r:Risk), (strat:Strategy {id: '"'"'STRAT_WARN_AND_CON..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_pt:Option {id: '"'"'OPT_TRANS_PT'"'"'})
SET opt_pt.name = '"'"'Transition Piece PT'"'"',
    opt_pt.type = '"'"'Accessory'"'"',
    opt_pt.desc = '"'"'Rectangular to round duct transition'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [195]: MERGE (opt_pt:Option {id: '"'"'OPT_TRANS_PT'"'"'})
SET opt_p..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (pf:ProductFamily), (opt:Option {id: '"'"'OPT_TRANS_PT'"'"'})
WHERE pf.id IN ['"'"'FAM_GDB'"'"', '"'"'FAM_GDC'"'"', '"'"'FAM_GDMI'"'"']
MERGE (pf)-[:SUGGESTS_CROSS_SELL {reason: '"'"'Connect rectangular housing to round ducts'"'"'}]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [196]: MATCH (pf:ProductFamily), (opt:Option {id: '"'"'OPT_TRANS_PT..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (consumable_bags:Option {id: '"'"'CONS_BAGS'"'"'})
SET consumable_bags.name = '"'"'Spare Bag Filters'"'"',
    consumable_bags.type = '"'"'Consumable'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [197]: MERGE (consumable_bags:Option {id: '"'"'CONS_BAGS'"'"'})
SET..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (cons:Option {id: '"'"'CONS_BAGS'"'"'})
MERGE (gdb)-[:SUGGESTS_CROSS_SELL {reason: '"'"'Complete the unit with spare filters'"'"'}]->(cons)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [198]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (cons:Opt..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (sol:Solution {id: '"'"'SOL_PREFILTER'"'"'})
MERGE (gdc)-[:SUGGESTS_CROSS_SELL {reason: '"'"'Protect carbon media from particles'"'"'}]->(sol)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [199]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (sol:Solu..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (vf_gdb_length:VariableFeature {id: '"'"'VF_GDB_LENGTH'"'"'})
SET vf_gdb_length.feature_name = '"'"'Housing Length'"'"',
    vf_gdb_length.parameter_name = '"'"'housing_length'"'"',
    vf_gdb_length.is_variable = true,
    vf_gdb_length.applies_to = '"'"'GDB'"'"',
    vf_gdb_length.question = '"'"'Which housing length do you need?'"'"',
    vf_gdb_length.why_needed = '"'"'GDB housings come in two lengths to accommodate different filter depths. The 550mm version fits short bag filters (up to 450mm depth), while the 750mm version fits long bag filters and compact filters (up to 650mm depth).'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [200]: MERGE (vf_gdb_length:VariableFeature {id: '"'"'VF_GDB_LENGTH..."; fi
echo "Progress: 200/243"
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (vf:VariableFeature {id: '"'"'VF_GDB_LENGTH'"'"'})
MERGE (gdb)-[:HAS_VARIABLE_FEATURE]->(vf)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [201]: MATCH (gdb:ProductFamily {id: '"'"'FAM_GDB'"'"'}), (vf:Varia..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_550:FeatureOption {id: '"'"'OPT_GDB_LEN_550'"'"'})
SET opt_550.value = '"'"'550'"'"',
    opt_550.name = '"'"'550mm'"'"',
    opt_550.display_label = '"'"'550mm (Short Housing)'"'"',
    opt_550.benefit = '"'"'For short bag filters up to 450mm depth'"'"',
    opt_550.is_default = false,
    opt_550.is_recommended = false' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [202]: MERGE (opt_550:FeatureOption {id: '"'"'OPT_GDB_LEN_550'"'"'}..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_750:FeatureOption {id: '"'"'OPT_GDB_LEN_750'"'"'})
SET opt_750.value = '"'"'750'"'"',
    opt_750.name = '"'"'750mm'"'"',
    opt_750.display_label = '"'"'750mm (Long Housing)'"'"',
    opt_750.benefit = '"'"'For long bag filters and compact filters - most common for standard installations'"'"',
    opt_750.is_default = true,
    opt_750.is_recommended = true' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [203]: MERGE (opt_750:FeatureOption {id: '"'"'OPT_GDB_LEN_750'"'"'}..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (vf:VariableFeature {id: '"'"'VF_GDB_LENGTH'"'"'}), (opt:FeatureOption {id: '"'"'OPT_GDB_LEN_550'"'"'})
MERGE (vf)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [204]: MATCH (vf:VariableFeature {id: '"'"'VF_GDB_LENGTH'"'"'}), (o..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (vf:VariableFeature {id: '"'"'VF_GDB_LENGTH'"'"'}), (opt:FeatureOption {id: '"'"'OPT_GDB_LEN_750'"'"'})
MERGE (vf)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [205]: MATCH (vf:VariableFeature {id: '"'"'VF_GDB_LENGTH'"'"'}), (o..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (disc_len:Discriminator {id: '"'"'DISC_LENGTH'"'"'})
SET disc_len.question = '"'"'Which housing length is required?'"'"',
    disc_len.explanation = '"'"'Longer housing allows for larger filter surface area and lower pressure drop'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [206]: MERGE (disc_len:Discriminator {id: '"'"'DISC_LENGTH'"'"'})
S..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (vf:VariableFeature {id: '"'"'VF_GDB_LENGTH'"'"'}), (disc:Discriminator {id: '"'"'DISC_LENGTH'"'"'})
MERGE (vf)-[:SELECTION_DEPENDS_ON]->(disc)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [207]: MATCH (vf:VariableFeature {id: '"'"'VF_GDB_LENGTH'"'"'}), (d..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (vf_gdmi_length:VariableFeature {id: '"'"'VF_GDMI_LENGTH'"'"'})
SET vf_gdmi_length.feature_name = '"'"'Housing Length'"'"',
    vf_gdmi_length.parameter_name = '"'"'housing_length'"'"',
    vf_gdmi_length.is_variable = true,
    vf_gdmi_length.applies_to = '"'"'GDMI'"'"',
    vf_gdmi_length.question = '"'"'Which housing length do you need?'"'"',
    vf_gdmi_length.why_needed = '"'"'GDMI insulated housings come in two lengths: 600mm for short filters and 850mm for long filters.'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [208]: MERGE (vf_gdmi_length:VariableFeature {id: '"'"'VF_GDMI_LENG..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (vf:VariableFeature {id: '"'"'VF_GDMI_LENGTH'"'"'})
MERGE (gdmi)-[:HAS_VARIABLE_FEATURE]->(vf)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [209]: MATCH (gdmi:ProductFamily {id: '"'"'FAM_GDMI'"'"'}), (vf:Var..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_gdmi_600:FeatureOption {id: '"'"'OPT_GDMI_LEN_600'"'"'})
SET opt_gdmi_600.value = '"'"'600'"'"',
    opt_gdmi_600.name = '"'"'600mm'"'"',
    opt_gdmi_600.display_label = '"'"'600mm (Short Housing)'"'"',
    opt_gdmi_600.benefit = '"'"'For short filters - compact installation'"'"',
    opt_gdmi_600.is_default = false' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [210]: MERGE (opt_gdmi_600:FeatureOption {id: '"'"'OPT_GDMI_LEN_600..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_gdmi_850:FeatureOption {id: '"'"'OPT_GDMI_LEN_850'"'"'})
SET opt_gdmi_850.value = '"'"'850'"'"',
    opt_gdmi_850.name = '"'"'850mm'"'"',
    opt_gdmi_850.display_label = '"'"'850mm (Long Housing)'"'"',
    opt_gdmi_850.benefit = '"'"'For long filters - maximum efficiency'"'"',
    opt_gdmi_850.is_default = true,
    opt_gdmi_850.is_recommended = true' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [211]: MERGE (opt_gdmi_850:FeatureOption {id: '"'"'OPT_GDMI_LEN_850..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (vf:VariableFeature {id: '"'"'VF_GDMI_LENGTH'"'"'}), (opt:FeatureOption {id: '"'"'OPT_GDMI_LEN_600'"'"'})
MERGE (vf)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [212]: MATCH (vf:VariableFeature {id: '"'"'VF_GDMI_LENGTH'"'"'}), (..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (vf:VariableFeature {id: '"'"'VF_GDMI_LENGTH'"'"'}), (opt:FeatureOption {id: '"'"'OPT_GDMI_LEN_850'"'"'})
MERGE (vf)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [213]: MATCH (vf:VariableFeature {id: '"'"'VF_GDMI_LENGTH'"'"'}), (..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (vf:VariableFeature {id: '"'"'VF_GDMI_LENGTH'"'"'}), (disc:Discriminator {id: '"'"'DISC_LENGTH'"'"'})
MERGE (vf)-[:SELECTION_DEPENDS_ON]->(disc)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [214]: MATCH (vf:VariableFeature {id: '"'"'VF_GDMI_LENGTH'"'"'}), (..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (vf_gdc_length:VariableFeature {id: '"'"'VF_GDC_LENGTH'"'"'})
SET vf_gdc_length.feature_name = '"'"'Housing Length'"'"',
    vf_gdc_length.parameter_name = '"'"'housing_length'"'"',
    vf_gdc_length.is_variable = true,
    vf_gdc_length.applies_to = '"'"'GDC'"'"',
    vf_gdc_length.question = '"'"'Which housing length do you need?'"'"',
    vf_gdc_length.why_needed = '"'"'GDC carbon housings come in 750mm (for 450mm cylinders) or 900mm (for 600mm cylinders or with Polisfilter rail).'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [215]: MERGE (vf_gdc_length:VariableFeature {id: '"'"'VF_GDC_LENGTH..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (vf:VariableFeature {id: '"'"'VF_GDC_LENGTH'"'"'})
MERGE (gdc)-[:HAS_VARIABLE_FEATURE]->(vf)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [216]: MATCH (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'}), (vf:Varia..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_gdc_750:FeatureOption {id: '"'"'OPT_GDC_LEN_750'"'"'})
SET opt_gdc_750.value = '"'"'750'"'"',
    opt_gdc_750.name = '"'"'750mm'"'"',
    opt_gdc_750.display_label = '"'"'750mm'"'"',
    opt_gdc_750.benefit = '"'"'For 450mm carbon cylinders'"'"',
    opt_gdc_750.is_default = true' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [217]: MERGE (opt_gdc_750:FeatureOption {id: '"'"'OPT_GDC_LEN_750'"..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (opt_gdc_900:FeatureOption {id: '"'"'OPT_GDC_LEN_900'"'"'})
SET opt_gdc_900.value = '"'"'900'"'"',
    opt_gdc_900.name = '"'"'900mm'"'"',
    opt_gdc_900.display_label = '"'"'900mm'"'"',
    opt_gdc_900.benefit = '"'"'For 600mm carbon cylinders or with Polisfilter rail'"'"',
    opt_gdc_900.is_default = false' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [218]: MERGE (opt_gdc_900:FeatureOption {id: '"'"'OPT_GDC_LEN_900'"..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (vf:VariableFeature {id: '"'"'VF_GDC_LENGTH'"'"'}), (opt:FeatureOption {id: '"'"'OPT_GDC_LEN_750'"'"'})
MERGE (vf)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [219]: MATCH (vf:VariableFeature {id: '"'"'VF_GDC_LENGTH'"'"'}), (o..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (vf:VariableFeature {id: '"'"'VF_GDC_LENGTH'"'"'}), (opt:FeatureOption {id: '"'"'OPT_GDC_LEN_900'"'"'})
MERGE (vf)-[:HAS_OPTION]->(opt)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [220]: MATCH (vf:VariableFeature {id: '"'"'VF_GDC_LENGTH'"'"'}), (o..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (vf:VariableFeature {id: '"'"'VF_GDC_LENGTH'"'"'}), (disc:Discriminator {id: '"'"'DISC_LENGTH'"'"'})
MERGE (vf)-[:SELECTION_DEPENDS_ON]->(disc)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [221]: MATCH (vf:VariableFeature {id: '"'"'VF_GDC_LENGTH'"'"'}), (d..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (acc:Accessory {code: '"'"'EXL'"'"'})
SET acc.full_name = '"'"'Eccentric Locking Mechanism'"'"',
    acc.compatible_families = ['"'"'GDB'"'"', '"'"'GDMI'"'"', '"'"'GDP'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [222]: MERGE (acc:Accessory {code: '"'"'EXL'"'"'})
SET acc.full_nam..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (acc:Accessory {code: '"'"'L'"'"'})
SET acc.full_name = '"'"'Left Hinge Option'"'"',
    acc.compatible_families = ['"'"'GDB'"'"', '"'"'GDC'"'"', '"'"'GDMI'"'"', '"'"'GDP'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [223]: MERGE (acc:Accessory {code: '"'"'L'"'"'})
SET acc.full_name ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (acc:Accessory {code: '"'"'F'"'"'})
SET acc.full_name = '"'"'Flange Connection'"'"',
    acc.compatible_families = ['"'"'GDB'"'"', '"'"'GDC'"'"', '"'"'GDMI'"'"', '"'"'GDP'"'"']' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [224]: MERGE (acc:Accessory {code: '"'"'F'"'"'})
SET acc.full_name ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (acc:Accessory {code: '"'"'Polis'"'"'})
SET acc.full_name = '"'"'Polysfilter Rail'"'"',
    acc.compatible_families = ['"'"'GDB'"'"', '"'"'GDMI'"'"'],
    acc.min_length_mm = 900' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [225]: MERGE (acc:Accessory {code: '"'"'Polis'"'"'})
SET acc.full_n..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MATCH (acc:Accessory {code: '"'"'EXL'"'"'}), (gdc:ProductFamily {id: '"'"'FAM_GDC'"'"'})
MERGE (acc)-[r:NOT_COMPATIBLE_WITH]->(gdc)
SET r.reason = '"'"'GDC uses bayonet mounting system, not compatible with EXL eccentric locks'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [226]: MATCH (acc:Accessory {code: '"'"'EXL'"'"'}), (gdc:ProductFam..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (constraint:GeometricConstraint {name: '"'"'polisfiltr_length'"'"'})
SET constraint.option = '"'"'polisfiltr'"'"',
    constraint.aliases = ['"'"'polis'"'"', '"'"'polysfilter'"'"', '"'"'afterfilter'"'"', '"'"'szyna na polisfiltr'"'"', '"'"'rail'"'"'],
    constraint.min_length_mm = 900,
    constraint.message = '"'"'Polysfilter rail option requires minimum housing length of 900mm'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [227]: MERGE (constraint:GeometricConstraint {name: '"'"'polisfiltr..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (constraint:GeometricConstraint {name: '"'"'prefilter_frame_length'"'"'})
SET constraint.option = '"'"'prefilter_frame'"'"',
    constraint.aliases = ['"'"'prefilter'"'"', '"'"'wstępny'"'"', '"'"'ramka na filtr wstępny'"'"'],
    constraint.additional_length_mm = 50,
    constraint.message = '"'"'Pre-filter frame adds 50mm to total installation length'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [228]: MERGE (constraint:GeometricConstraint {name: '"'"'prefilter_..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'MERGE (constraint:GeometricConstraint {name: '"'"'installation_tolerance'"'"'})
SET constraint.minimum_margin_mm = 10,
    constraint.message = '"'"'Zero tolerance fit (exact dimensions). Recommend 10mm+ margin for installation tolerances'"'"'' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [229]: MERGE (constraint:GeometricConstraint {name: '"'"'installati..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX application_name IF NOT EXISTS FOR (a:Application) ON (a.name)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [230]: CREATE INDEX application_name IF NOT EXISTS FOR (a:Applicati..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX application_id IF NOT EXISTS FOR (a:Application) ON (a.id)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [231]: CREATE INDEX application_id IF NOT EXISTS FOR (a:Application..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX risk_name IF NOT EXISTS FOR (r:Risk) ON (r.name)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [232]: CREATE INDEX risk_name IF NOT EXISTS FOR (r:Risk) ON (r.name..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX risk_id IF NOT EXISTS FOR (r:Risk) ON (r.id)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [233]: CREATE INDEX risk_id IF NOT EXISTS FOR (r:Risk) ON (r.id)..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX parameter_id IF NOT EXISTS FOR (p:Parameter) ON (p.id)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [234]: CREATE INDEX parameter_id IF NOT EXISTS FOR (p:Parameter) ON..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX question_id IF NOT EXISTS FOR (q:Question) ON (q.id)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [235]: CREATE INDEX question_id IF NOT EXISTS FOR (q:Question) ON (..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX material_code IF NOT EXISTS FOR (m:Material) ON (m.code)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [236]: CREATE INDEX material_code IF NOT EXISTS FOR (m:Material) ON..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX accessory_code IF NOT EXISTS FOR (a:Accessory) ON (a.code)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [237]: CREATE INDEX accessory_code IF NOT EXISTS FOR (a:Accessory) ..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX strategy_id IF NOT EXISTS FOR (s:Strategy) ON (s.id)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [238]: CREATE INDEX strategy_id IF NOT EXISTS FOR (s:Strategy) ON (..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CALL db.index.fulltext.createNodeIndex("applicationKeywords", ["Application"], ["name", "keywords"])
CREATE CONSTRAINT IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [239]: CALL db.index.fulltext.createNodeIndex("applicationKeywords"..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE CONSTRAINT IF NOT EXISTS FOR (ap:ActiveProject) REQUIRE ap.id IS UNIQUE' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [240]: CREATE CONSTRAINT IF NOT EXISTS FOR (ap:ActiveProject) REQUI..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX session_last_active IF NOT EXISTS FOR (s:Session) ON (s.last_active)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [241]: CREATE INDEX session_last_active IF NOT EXISTS FOR (s:Sessio..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX tagunit_session IF NOT EXISTS FOR (t:TagUnit) ON (t.session_id)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [242]: CREATE INDEX tagunit_session IF NOT EXISTS FOR (t:TagUnit) O..."; fi
redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse 'CREATE INDEX activeproject_session IF NOT EXISTS FOR (ap:ActiveProject) ON (ap.session_id)' > /dev/null 2>&1
if [ $? -eq 0 ]; then OK=$((OK+1)); else ERRORS=$((ERRORS+1)); echo "FAIL [243]: CREATE INDEX activeproject_session IF NOT EXISTS FOR (ap:Act..."; fi

echo "Done! OK=$OK ERRORS=$ERRORS"
