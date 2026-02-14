// ============================================================
// GEOMETRIC CONSTRAINT UPDATE: Polis After-Filter Rail
// ============================================================
// Source: PDF Catalog Page 14, Option Section
// The 'Polis' (after-filter polishing rail) option is ONLY available
// in the 900/950mm housing variant. It physically cannot fit in 750mm.
// ============================================================

// Step 1: Find or create the Polis option node
MERGE (o:FeatureOption {id: "OPT_POLIS"})
SET o.name = "Polis",
    o.value = "polis",
    o.display_label = "Polis (After-filter Rail)",
    o.description = "Secondary polishing filter stage for enhanced air quality",
    o.min_required_housing_length = 900,
    o.physics_logic = "The after-filter rail (Polis) requires extra internal depth to accommodate the secondary filter stage. This additional space is only available in the 900/950mm housing variants.",
    o.use_case = "High air quality requirements, cleanroom adjacent spaces",
    o.benefit = "Additional filtration stage for polishing air after primary carbon treatment"
RETURN o;

// Step 2: Link Polis to the GDC product family's length feature
MATCH (pf:ProductFamily {id: "FAM_GDC"})
MATCH (f:VariableFeature {parameter_name: "housing_length"})
WHERE (pf)-[:HAS_VARIABLE_FEATURE]->(f)
MATCH (o:FeatureOption {id: "OPT_POLIS"})
MERGE (f)-[:HAS_OPTION]->(o)
RETURN pf.name, f.feature_name, o.name;

// Step 3: Create explicit compatibility relationships
// 900mm variant IS compatible with Polis
MATCH (o:FeatureOption {id: "OPT_POLIS"})
MATCH (v900:FeatureOption)
WHERE v900.value IN ["900", "950"] AND v900.id CONTAINS "LENGTH"
MERGE (o)-[:COMPATIBLE_WITH_VARIANT]->(v900)
RETURN o.name, v900.value;

// Step 4: Create explicit INCOMPATIBILITY with 750mm
MATCH (o:FeatureOption {id: "OPT_POLIS"})
MATCH (v750:FeatureOption)
WHERE v750.value IN ["750", "550", "600"] AND v750.id CONTAINS "LENGTH"
MERGE (o)-[:INCOMPATIBLE_WITH_VARIANT {reason: "Insufficient internal depth for after-filter rail"}]->(v750)
RETURN o.name, v750.value;

// Step 5: Also update any existing VariableFeature for "afterfilter" or "polis"
MATCH (f:VariableFeature)
WHERE f.parameter_name CONTAINS "polis" OR f.feature_name CONTAINS "Polis"
SET f.min_required_housing_length = 900,
    f.physics_logic = "The after-filter rail requires 900mm minimum housing length."
RETURN f.feature_name;
