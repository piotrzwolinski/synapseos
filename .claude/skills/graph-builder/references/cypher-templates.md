# Cypher Templates — Ready-to-Use Patterns for Graph CRUD

## New Application

```cypher
MERGE (a:Application {id: $id})
SET a.name = $name,
    a.keywords = $keywords
```
Params:
```json
{
  "id": "APP_PHARMACEUTICAL",
  "name": "Pharmaceutical Cleanroom",
  "keywords": ["pharmaceutical", "pharma", "cleanroom", "gmp", "sterile"]
}
```

**With embedding (for vector search):**
After creating the node, generate embedding via Python:
```python
from embeddings import generate_embedding
text = f"{name}. Keywords: {', '.join(keywords)}"
embedding = generate_embedding(text)
# Then SET a.embedding = $embedding, a.embedding_text = $text
```

## New Environment

```cypher
MERGE (e:Environment {id: $id})
SET e.name = $name,
    e.description = $description,
    e.keywords = $keywords,
    e.humidity_exposure = $humidity,
    e.temperature_variation = $temp_var
```
Params:
```json
{
  "id": "ENV_CLEANROOM",
  "name": "Cleanroom Environment",
  "description": "Controlled environment with strict particulate and contamination limits",
  "keywords": ["cleanroom", "clean room", "iso 14644", "gmp"],
  "humidity": "Controlled",
  "temp_var": "Low"
}
```

**With IS_A hierarchy:**
```cypher
MATCH (child:Environment {id: $child_id})
MATCH (parent:Environment {id: $parent_id})
MERGE (child)-[:IS_A]->(parent)
```

## New EnvironmentalStressor

```cypher
MERGE (s:EnvironmentalStressor {id: $id})
SET s.name = $name,
    s.category = $category,
    s.description = $description,
    s.keywords = $keywords
```
Params:
```json
{
  "id": "STRESSOR_UV_RADIATION",
  "name": "UV Radiation Exposure",
  "category": "physical",
  "description": "Ultraviolet radiation degrades polymer materials and coatings",
  "keywords": ["uv", "ultraviolet", "sun", "radiation", "sunlight"]
}
```

## Application → Stressor Link

```cypher
MATCH (a:Application {id: $app_id})
MATCH (s:EnvironmentalStressor {id: $stressor_id})
MERGE (a)-[:EXPOSES_TO]->(s)
```

## Environment → Stressor Link

```cypher
MATCH (e:Environment {id: $env_id})
MATCH (s:EnvironmentalStressor {id: $stressor_id})
MERGE (e)-[:EXPOSES_TO]->(s)
```

## Stressor → Trait Demand (Causal Rule)

This is the core physics rule: "This stressor DEMANDS this trait to be neutralized."

```cypher
MATCH (s:EnvironmentalStressor {id: $stressor_id})
MATCH (t:PhysicalTrait {id: $trait_id})
MERGE (s)-[r:DEMANDS_TRAIT]->(t)
SET r.severity = $severity,
    r.explanation = $explanation
```
Params:
```json
{
  "stressor_id": "STRESSOR_UV_RADIATION",
  "trait_id": "TRAIT_UV_RESISTANCE",
  "severity": "CRITICAL",
  "explanation": "UV radiation causes photodegradation of non-UV-stabilized polymers, leading to embrittlement and structural failure within 2-5 years"
}
```
Severity options: `CRITICAL` (blocks product), `WARNING` (warns user), `INFO` (informational)

## New PhysicalTrait

```cypher
MERGE (t:PhysicalTrait {id: $id})
SET t.name = $name,
    t.category = $category,
    t.description = $description,
    t.keywords = $keywords
```

## ProductFamily → Trait Link

```cypher
MATCH (pf:ProductFamily {id: $pf_id})
MATCH (t:PhysicalTrait {id: $trait_id})
MERGE (pf)-[:HAS_TRAIT]->(t)
```

## New DependencyRule (Assembly Trigger)

Creates a rule that says: "When stressor X is present, the target product needs a protector with trait Y upstream."

```cypher
MERGE (dr:DependencyRule {id: $id})
SET dr.dependency_type = 'MANDATES_PROTECTION',
    dr.description = $description

WITH dr
MATCH (s:EnvironmentalStressor {id: $stressor_id})
MERGE (dr)-[:TRIGGERED_BY_STRESSOR]->(s)

WITH dr
MATCH (ut:PhysicalTrait {id: $upstream_trait_id})
MERGE (dr)-[:UPSTREAM_REQUIRES_TRAIT]->(ut)

WITH dr
MATCH (dt:PhysicalTrait {id: $downstream_trait_id})
MERGE (dr)-[:DOWNSTREAM_PROVIDES_TRAIT]->(dt)
```
Params:
```json
{
  "id": "DEP_UV_COATING",
  "description": "UV-exposed environments require UV-resistant coating upstream of standard housing",
  "stressor_id": "STRESSOR_UV_RADIATION",
  "upstream_trait_id": "TRAIT_MECHANICAL_FILTRATION",
  "downstream_trait_id": "TRAIT_UV_RESISTANCE"
}
```

## New LogicGate

```cypher
MERGE (g:LogicGate {id: $id})
SET g.name = $name,
    g.condition_logic = $condition,
    g.physics_explanation = $physics

WITH g
MATCH (s:EnvironmentalStressor {id: $stressor_id})
MERGE (g)-[:MONITORS]->(s)
```

## Gate → Parameter Link

```cypher
MATCH (g:LogicGate {id: $gate_id})
MATCH (p:Parameter {id: $param_id})
MERGE (g)-[:REQUIRES_DATA]->(p)
```

## New Parameter

```cypher
MERGE (p:Parameter {id: $id})
SET p.name = $name,
    p.property_key = $property_key,
    p.priority = $priority,
    p.question = $question,
    p.unit = $unit,
    p.type = $type
```

## Application → Gate Trigger

```cypher
MATCH (a:Application {id: $app_id})
MATCH (g:LogicGate {id: $gate_id})
MERGE (a)-[:TRIGGERS_GATE]->(g)
```

## New HardConstraint

```cypher
MERGE (hc:HardConstraint {id: $id})
SET hc.property_key = $property_key,
    hc.operator = $operator,
    hc.value = $value,
    hc.error_msg = $error_msg

WITH hc
MATCH (pf:ProductFamily {id: $pf_id})
MERGE (pf)-[:HAS_HARD_CONSTRAINT]->(hc)
```
Operators: `>=`, `<=`, `==`, `!=`, `>`, `<`, `in`, `not_in`

## New InstallationConstraint

### Type: COMPUTED_FORMULA (Service Clearance)
```cypher
MERGE (ic:InstallationConstraint {id: $id})
SET ic.constraint_type = 'COMPUTED_FORMULA',
    ic.dimension_key = $dim_key,
    ic.factor_property = 'service_access_factor',
    ic.comparison_key = 'available_space_mm',
    ic.severity = 'CRITICAL',
    ic.error_msg = $error_msg

WITH ic
MATCH (pf:ProductFamily {id: $pf_id})
MERGE (pf)-[:HAS_INSTALLATION_CONSTRAINT]->(ic)
```

### Type: SET_MEMBERSHIP (Environment Whitelist)
```cypher
MERGE (ic:InstallationConstraint {id: $id})
SET ic.constraint_type = 'SET_MEMBERSHIP',
    ic.input_key = 'installation_environment',
    ic.list_property = 'allowed_environments',
    ic.severity = 'CRITICAL',
    ic.error_msg = $error_msg

WITH ic
MATCH (pf:ProductFamily {id: $pf_id})
SET pf.allowed_environments = $allowed_envs
MERGE (pf)-[:HAS_INSTALLATION_CONSTRAINT]->(ic)
```

### Type: CROSS_NODE_THRESHOLD (Material Property)
```cypher
MERGE (ic:InstallationConstraint {id: $id})
SET ic.constraint_type = 'CROSS_NODE_THRESHOLD',
    ic.input_key = $input_key,
    ic.cross_property = $cross_property,
    ic.material_context_key = 'material',
    ic.operator = '>=',
    ic.severity = 'CRITICAL',
    ic.error_msg = $error_msg

WITH ic
MATCH (pf:ProductFamily {id: $pf_id})
MERGE (pf)-[:HAS_INSTALLATION_CONSTRAINT]->(ic)
```

## New CapacityRule

```cypher
MERGE (cr:CapacityRule {id: $id})
SET cr.module_descriptor = $module_desc,
    cr.output_rating = $output_rating,
    cr.input_requirement = 'airflow_m3h',
    cr.capacity_per_component = $per_component,
    cr.description = $description,
    cr.assumption = $assumption

WITH cr
MATCH (pf:ProductFamily {id: $pf_id})
MERGE (pf)-[:HAS_CAPACITY]->(cr)
```

## New DimensionModule

```cypher
MERGE (dm:DimensionModule {id: $id})
SET dm.width_mm = $width,
    dm.height_mm = $height,
    dm.reference_airflow_m3h = $airflow,
    dm.label = $label
```

## ProductFamily → DimensionModule Link

```cypher
MATCH (pf:ProductFamily {id: $pf_id})
MATCH (dm:DimensionModule {id: $dim_id})
MERGE (pf)-[:AVAILABLE_IN_SIZE]->(dm)
```

## New VariableFeature with Options

```cypher
MERGE (vf:VariableFeature {id: $id})
SET vf.feature_name = $name,
    vf.parameter_name = $param_name,
    vf.description = $description,
    vf.is_variable = true,
    vf.auto_resolve = $auto_resolve,
    vf.default_value = $default_value

WITH vf
MATCH (pf:ProductFamily {id: $pf_id})
MERGE (pf)-[:HAS_VARIABLE_FEATURE]->(vf)

WITH vf
UNWIND $options AS opt
MERGE (fo:FeatureOption {id: opt.id})
SET fo.name = opt.name,
    fo.value = opt.value,
    fo.description = opt.description,
    fo.is_default = opt.is_default,
    fo.display_label = opt.display_label
MERGE (vf)-[:HAS_OPTION]->(fo)
```

## Bulk Node Creation (with UNWIND)

```cypher
UNWIND $items AS item
MERGE (n:NodeType {id: item.id})
SET n.name = item.name,
    n.description = item.description
```

## Delete Node (with safety check)

```cypher
// First verify what will be deleted
MATCH (n {id: $id})
OPTIONAL MATCH (n)-[r]-()
RETURN n, type(r) AS rel_type, count(r) AS rel_count

// Then delete (DETACH removes all relationships)
MATCH (n {id: $id})
DETACH DELETE n
```
