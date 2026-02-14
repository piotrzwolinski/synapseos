// ============================================================
// NEO4J PERFORMANCE INDEXES
// Run this script to optimize query performance
// ============================================================

// ======================
// FULLTEXT INDEXES (for CONTAINS queries - critical for performance!)
// ======================

// ProductVariant fulltext index (used by config_search - was 6.48s)
CREATE FULLTEXT INDEX product_variant_fulltext IF NOT EXISTS
FOR (n:ProductVariant) ON EACH [n.name, n.family, n.options_json];

// FilterCartridge fulltext index
CREATE FULLTEXT INDEX filter_cartridge_fulltext IF NOT EXISTS
FOR (n:FilterCartridge) ON EACH [n.name, n.model_name];

// FilterConsumable fulltext index
CREATE FULLTEXT INDEX filter_consumable_fulltext IF NOT EXISTS
FOR (n:FilterConsumable) ON EACH [n.part_number, n.model_name, n.filter_type];

// MaterialSpecification fulltext index
CREATE FULLTEXT INDEX material_spec_fulltext IF NOT EXISTS
FOR (n:MaterialSpecification) ON EACH [n.code, n.full_name, n.name, n.description];

// Project fulltext index (used by project_search - was 4.28s)
CREATE FULLTEXT INDEX project_fulltext IF NOT EXISTS
FOR (n:Project) ON EACH [n.name];

// Concept fulltext index (for hybrid retrieval)
CREATE FULLTEXT INDEX concept_fulltext IF NOT EXISTS
FOR (n:Concept) ON EACH [n.name, n.description, n.text];

// Keyword fulltext index (for learned rules)
CREATE FULLTEXT INDEX keyword_fulltext IF NOT EXISTS
FOR (n:Keyword) ON EACH [n.name];

// ======================
// B-TREE INDEXES (for exact lookups and STARTS WITH)
// ======================

// ProductVariant lookups
CREATE INDEX product_variant_name IF NOT EXISTS FOR (n:ProductVariant) ON (n.name);
CREATE INDEX product_variant_family IF NOT EXISTS FOR (n:ProductFamily) ON (n.id);
CREATE INDEX product_family_name IF NOT EXISTS FOR (n:ProductFamily) ON (n.name);

// Material lookups
CREATE INDEX material_code IF NOT EXISTS FOR (n:Material) ON (n.code);

// Application lookups (for policy evaluation)
CREATE INDEX application_id IF NOT EXISTS FOR (n:Application) ON (n.id);
CREATE INDEX application_name IF NOT EXISTS FOR (n:Application) ON (n.name);

// Option/Feature lookups
CREATE INDEX option_code IF NOT EXISTS FOR (n:Option) ON (n.code);
CREATE INDEX variable_feature_id IF NOT EXISTS FOR (n:VariableFeature) ON (n.id);

// Project lookups
CREATE INDEX project_name IF NOT EXISTS FOR (n:Project) ON (n.name);

// ======================
// SHOW ALL INDEXES
// ======================
SHOW INDEXES;
