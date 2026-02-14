# Diagnostic Cypher Queries

Use these queries via `mcp__neo4j__read_neo4j_cypher` to verify graph data when debugging.

## 1. Product Family — Full Profile

```cypher
MATCH (pf:ProductFamily {id: $pf_id})
OPTIONAL MATCH (pf)-[:HAS_TRAIT]->(t:PhysicalTrait)
OPTIONAL MATCH (pf)-[:AVAILABLE_IN_MATERIAL]->(m:Material)
OPTIONAL MATCH (pf)-[:AVAILABLE_IN_SIZE]->(dm:DimensionModule)
RETURN pf {.*},
       collect(DISTINCT t.id) AS traits,
       collect(DISTINCT m.code) AS materials,
       collect(DISTINCT {id: dm.id, w: dm.width_mm, h: dm.height_mm, airflow: dm.reference_airflow_m3h}) AS sizes
```
Params: `{pf_id: "FAM_GDB"}`

## 2. DimensionModule — Reference Airflow Check

```cypher
MATCH (dm:DimensionModule {id: $dim_id})
RETURN dm {.*}
```
Params: `{dim_id: "DIM_600x600"}` or `{dim_id: "DIM_300x600"}`

## 3. Reference Airflow for Dimensions (what the button builder queries)

```cypher
MATCH (d:DimensionModule)
WHERE (d.width_mm = $w AND d.height_mm = $h)
   OR (d.width_mm = $h AND d.height_mm = $w)
RETURN d.id, d.reference_airflow_m3h, d.label, d.width_mm, d.height_mm
```
Params: `{w: 300, h: 600}`

## 4. Product-Specific Effective Airflow (CapacityRule + SizeProperty)

```cypher
MATCH (pf:ProductFamily {id: $pf_id})-[:AVAILABLE_IN_SIZE]->(dm:DimensionModule)
OPTIONAL MATCH (pf)-[:HAS_CAPACITY]->(cr:CapacityRule)
OPTIONAL MATCH (dm)-[:DETERMINES_PROPERTY]->(sp_fam:SizeProperty)
  WHERE sp_fam.key = cr.component_count_key AND sp_fam.for_family = pf.id
OPTIONAL MATCH (dm)-[:DETERMINES_PROPERTY]->(sp_gen:SizeProperty)
  WHERE sp_gen.key = cr.component_count_key AND sp_gen.for_family IS NULL
WITH pf, dm, cr,
     CASE WHEN cr IS NOT NULL AND COALESCE(sp_fam.value, sp_gen.value) IS NOT NULL
          THEN toFloat(COALESCE(sp_fam.value, sp_gen.value)) * toFloat(cr.capacity_per_component)
          ELSE dm.reference_airflow_m3h
     END AS effective_airflow
RETURN dm.id, dm.width_mm, dm.height_mm, effective_airflow, cr.output_rating
ORDER BY effective_airflow DESC
```
Params: `{pf_id: "FAM_GDB"}`

## 5. Stressors for Application

```cypher
MATCH (a:Application {id: $app_id})-[:EXPOSES_TO]->(s:EnvironmentalStressor)
RETURN a.name, s.id, s.name, s.category
```
Params: `{app_id: "APP_KITCHEN"}`

## 6. Stressors with Environment IS_A Hierarchy

```cypher
MATCH (e:Environment {id: $env_id})-[:IS_A*0..5]->(parent)
WITH collect(DISTINCT parent) + collect(DISTINCT e) AS chain
UNWIND chain AS node
OPTIONAL MATCH (node)-[:EXPOSES_TO]->(s:EnvironmentalStressor)
RETURN node.id AS source, s.id AS stressor_id, s.name AS stressor_name
```
Params: `{env_id: "ENV_KITCHEN"}`

## 7. Causal Rules for Stressors

```cypher
MATCH (s:EnvironmentalStressor)-[:DEMANDS_TRAIT]->(t:PhysicalTrait)
WHERE s.id IN $stressor_ids
RETURN s.id AS stressor, s.name, t.id AS trait, t.name AS trait_name
```
Params: `{stressor_ids: ["STRESSOR_CHEMICAL_VAPORS", "STRESSOR_PARTICULATE_EXPOSURE"]}`

## 8. Logic Gates for Stressors

```cypher
MATCH (g:LogicGate)-[:MONITORS]->(s:EnvironmentalStressor)
WHERE s.id IN $stressor_ids
OPTIONAL MATCH (g)-[:REQUIRES_DATA]->(p:Parameter)
RETURN g.id, g.name, s.id AS stressor, collect({param: p.id, key: p.property_key, unit: p.unit}) AS params
```
Params: `{stressor_ids: ["STRESSOR_EXPLOSIVE_ATMOSPHERE"]}`

## 9. DependencyRules (Assembly Triggers)

```cypher
MATCH (dr:DependencyRule)-[:TRIGGERED_BY_STRESSOR]->(s:EnvironmentalStressor)
WHERE s.id IN $stressor_ids
MATCH (dr)-[:UPSTREAM_REQUIRES_TRAIT]->(ut:PhysicalTrait)
MATCH (dr)-[:DOWNSTREAM_PROVIDES_TRAIT]->(dt:PhysicalTrait)
RETURN dr.id, dr.dependency_type, s.name AS trigger,
       ut.id AS upstream_trait, dt.id AS downstream_trait
```
Params: `{stressor_ids: ["STRESSOR_GREASE_EXPOSURE"]}`

## 10. Installation Constraints for Product

```cypher
MATCH (pf:ProductFamily {id: $pf_id})-[:HAS_INSTALLATION_CONSTRAINT]->(ic:InstallationConstraint)
RETURN ic {.*}, pf.allowed_environments, pf.service_access_factor
```
Params: `{pf_id: "FAM_GDB"}`

## 11. CapacityRule for Product + Module Size

```cypher
MATCH (pf:ProductFamily {id: $pf_id})-[:HAS_CAPACITY]->(cr:CapacityRule)
RETURN cr {.*}
```
Params: `{pf_id: "FAM_GDB"}`

## 12. Variable Features (Auto-Resolve Check)

```cypher
MATCH (pf:ProductFamily {id: $pf_id})-[:HAS_VARIABLE_FEATURE]->(vf:VariableFeature)
OPTIONAL MATCH (vf)-[:HAS_OPTION]->(opt:FeatureOption)
RETURN vf.id, vf.feature_name, vf.auto_resolve, vf.default_value,
       collect({name: opt.name, value: opt.value, is_default: opt.is_default}) AS options
```
Params: `{pf_id: "FAM_GDP"}`

## 13. Session State (Layer 4)

```cypher
MATCH (s:Session {id: $session_id})-[:WORKING_ON]->(p:ActiveProject)
OPTIONAL MATCH (p)-[:HAS_UNIT]->(t:TagUnit)
RETURN p {.*}, collect(t {.*}) AS tags
```
Params: `{session_id: "your-session-id"}`

## 14. All Product Families with Traits (Assembly Candidate Check)

```cypher
MATCH (pf:ProductFamily)
OPTIONAL MATCH (pf)-[:HAS_TRAIT]->(t:PhysicalTrait)
RETURN pf.id, pf.name, pf.selection_priority,
       collect(t.id) AS traits
ORDER BY pf.selection_priority ASC
```

## 15. Material Properties (Chlorine Check)

```cypher
MATCH (pf:ProductFamily {id: $pf_id})-[:AVAILABLE_IN_MATERIAL]->(m:Material)
RETURN m.id, m.code, m.name, m.chlorine_resistance_ppm, m.corrosion_class
```
Params: `{pf_id: "FAM_GDB"}`

## 16. Higher-Capacity Alternatives

```cypher
MATCH (pf:ProductFamily)-[:HAS_CAPACITY]->(cr:CapacityRule)
WHERE cr.module_descriptor = $module
RETURN pf.id, pf.name, cr.output_rating, pf.selection_priority
ORDER BY cr.output_rating DESC
```
Params: `{module: "600x600"}`
