// ============================================================
// GEOMETRIC CONSTRAINT: Polis After-Filter Rail
// ============================================================
// Source: PDF Catalog Page 14, Option Section
// The 'Polis' (after-filter polishing rail) is ONLY available in the
// 900/950mm housing variant. It physically cannot fit in 750mm.
//
// MODELING RULE: Polis is an ACCESSORY (ACC_POLIS), NOT a housing-length
// option. It MUST NOT be linked to a housing_length VariableFeature via
// HAS_OPTION — doing so pollutes the length-selection clarification with a
// non-length item. The geometric constraint lives on the Accessory node and
// is read via the HAS_COMPATIBLE_ACCESSORY path (see
// database.get_option_geometric_constraints). Family-level suitability is
// governed by HAS_COMPATIBLE_ACCESSORY / INCOMPATIBLE_WITH edges (Polis is
// compatible with GDB/GDMI, incompatible with GDC/GDC_FLEX).
// ============================================================

// Step 1: Put the geometric constraint on the Polis ACCESSORY node.
MERGE (a:Accessory {id: "ACC_POLIS"})
SET a.name = "Polis",
    a.value = "polis",
    a.min_required_housing_length = 900,
    a.min_housing_length = 900,
    a.physics_logic = "The after-filter rail (Polis) requires extra internal depth to accommodate the secondary filter stage. This additional space is only available in the 900/950mm housing variants."
RETURN a.id, a.min_required_housing_length;

// NOTE: Deliberately NO step linking Polis to a housing_length VariableFeature.
// A previous version created (:VariableFeature{housing_length})-[:HAS_OPTION]->(OPT_POLIS),
// which caused Polis to leak into the housing-length clarification options.
// See database/fix_polis_length_feature.py for the repair migration.
