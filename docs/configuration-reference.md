# AI Solutions Finder — Configuration Reference

Complete reference of all fields in `config.yaml`. Located at `backend/tenants/mann_hummel/config.yaml`.

**Hot reload:** `POST /config/domain/{id}/reload` — no server restart needed.

---

## 1. Domain Metadata

```yaml
domain:
  id: "hvac_filtration"
  name: "Air Filtration Systems"
  company: "Mann+Hummel"
  description: "Sales Engineering Assistant for industrial air filtration products"
  version: "2.0"
  graph_name: "hvac"
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Internal domain identifier |
| `name` | string | Display name |
| `company` | string | Company name |
| `description` | string | Domain description |
| `version` | string | Configuration version |
| `graph_name` | string | FalkorDB graph name |

---

## 2. Entity Patterns

Defines the valid product, material, and option codes the system recognizes.

```yaml
entity_patterns:
  product_families:
    values: ["GDC-FLEX", "GDC", "GDP", "GDR", "GDF", "GDMI", "GDB", "PFF", "BFF"]
  material_codes:
    values: ["FZ", "ZM", "RF", "SS", "ALU", "AZ"]
  option_codes:
    values: ["EXL", "L", "F", "Polis"]
```

| Field | Type | Description |
|-------|------|-------------|
| `product_families.values` | list[string] | Valid product family codes |
| `material_codes.values` | list[string] | Valid material codes |
| `option_codes.values` | list[string] | Valid option codes |

---

## 3. Search Triggers

Keywords that trigger different types of searches in the knowledge graph.

```yaml
search_triggers:
  option_keywords: ["option", "code", "hinging", "flange", "frame", "material", ...]
  material_keywords: ["corrosion", "steel", "galvanized", "stainless", ...]
  technical_keywords: ["capacity", "airflow", "temperature", "pressure", ...]
```

| Field | Type | Description |
|-------|------|-------------|
| `option_keywords` | list[string] | Words that trigger option/configuration searches |
| `material_keywords` | list[string] | Words that trigger material-related searches |
| `technical_keywords` | list[string] | Words that trigger technical data searches |

---

## 4. Material-Environment Rules

### Material Hierarchy

Defines available materials with their corrosion resistance ratings.

```yaml
material_environment_rules:
  material_hierarchy:
    - code: "FZ"
      full_name: "Galvanized Steel (Zinc)"
      corrosion_class: "C3"
      description: "Standard indoor, mild environments"
      suitable_for: ["office", "warehouse", "light industrial"]
```

| Field | Type | Description |
|-------|------|-------------|
| `code` | string | Material code (FZ, ZM, RF, SF) |
| `full_name` | string | Full material name |
| `corrosion_class` | string | EN ISO 12944 class (C3, C4, C5, C5.1) |
| `description` | string | Suitable conditions |
| `suitable_for` | list[string] | Environment keywords |

**Current materials:**

| Code | Name | Corrosion Class | Typical Use |
|------|------|----------------|-------------|
| FZ | Galvanized Steel | C3 | Standard indoor |
| ZM | Zinc-Magnesium (ZM310) | C5 | Coastal, outdoor, industrial |
| RF | Stainless Steel (304) | C5 | Healthcare, food, chemical |
| SF | Stainless Steel (316L) | C5.1 | Marine, high chloride |

### Demanding Environments

Environments that require specific material grades.

```yaml
  demanding_environments:
    - name: "hospital"
      aliases: ["medical", "healthcare", "clinic", "szpital"]
      min_corrosion_class: "C5"
      required_materials: ["RF", "SF"]
      concern: "hygiene requirements, chemical disinfection, VDI 6022 compliance"
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Environment name |
| `aliases` | list[string] | Alternative names / multilingual keywords |
| `min_corrosion_class` | string | Minimum required corrosion class |
| `required_materials` | list[string] | Which material codes are acceptable |
| `concern` | string | Why this environment is demanding |

**Current demanding environments:**

| Environment | Min Class | Required Materials | Key Concern |
|------------|-----------|-------------------|-------------|
| Hospital | C5 | RF, SF | Hygiene, VDI 6022 |
| Food Processing | C5 | RF, SF | Contamination, HACCP |
| Pool | C5 | RF, SF | Chlorine exposure |
| Marine | C5.1 | SF only | Salt spray |
| Laboratory | C5 | RF, SF | Chemical exposure |
| Commercial Kitchen | C4 | ZM, RF | Grease, steam |

---

## 5. Product-Application Rules

### Product Capabilities

Defines what each product family can and cannot filter.

```yaml
product_application_rules:
  product_capabilities:
    - family: "GDB"
      full_name: "Bag Filter Housing"
      filters: ["dust", "particulate", "solid aerosols"]
      does_NOT_filter: ["gas", "odor", "fumes", "VOC", "smoke"]
      warning_applications:
        - trigger: ["exhaust fumes", "odor", "gas", "VOC"]
          message: "GDB bag filters capture PARTICLES only..."
          alternative: "GDC"
```

| Field | Type | Description |
|-------|------|-------------|
| `family` | string | Product family code |
| `full_name` | string | Display name |
| `filters` | list[string] | What this product handles |
| `does_NOT_filter` | list[string] | What this product cannot handle |
| `type` | string | Product type description |
| `special_feature` | string | Unique capability |
| `recommended_for` | list[string] | Best-fit scenarios |
| `warning_applications[].trigger` | list[string] | Keywords that trigger warning |
| `warning_applications[].message` | string | Warning text |
| `warning_applications[].alternative` | string | Recommended alternative |

### Installation Warnings

Warnings for specific installation conditions.

```yaml
  installation_warnings:
    - trigger: ["rooftop", "outdoor", "no insulation"]
      condition: "outdoor or rooftop"
      products_affected: ["GDB", "GDC", "GDP"]
      message: "Non-insulated housing on rooftop WILL cause condensation..."
      alternative: "GDMI"
```

| Field | Type | Description |
|-------|------|-------------|
| `trigger` | list[string] | Keywords that activate this warning |
| `condition` | string | Condition description |
| `products_affected` | list[string] | Which products this applies to |
| `message` | string | Warning message |
| `alternative` | string | Recommended product instead |

---

## 6. Geometric Constraints

Physical dimension rules that cannot be violated.

```yaml
geometric_constraints:
  options_requiring_length:
    - option: "polisfiltr"
      aliases: ["polis", "polysfilter", "afterfilter"]
      min_length_mm: 900
      message: "Polysfilter rail requires minimum 900mm length."

    - option: "prefilter_frame"
      aliases: ["prefilter"]
      additional_length_mm: 50
      message: "Pre-filter frame adds 50mm to total length."

  installation_tolerance:
    minimum_margin_mm: 10
```

| Field | Type | Description |
|-------|------|-------------|
| `option` | string | Option name |
| `aliases` | list[string] | Alternative names |
| `min_length_mm` | int | Minimum housing length required (mm) |
| `additional_length_mm` | int | Length added by this option (mm) |
| `message` | string | Explanation text |
| `minimum_margin_mm` | int | Recommended installation clearance (mm) |

---

## 7. Accessory Compatibility

Which accessories work with which product families.

```yaml
accessory_compatibility:
  - accessory: "EXL"
    full_name: "Eccentric Locking Mechanism"
    compatible_with: ["GDB", "GDMI", "GDP"]
    NOT_compatible_with: ["GDC"]
    reason: "GDC uses bayonet mounting, not compatible with EXL."
```

| Field | Type | Description |
|-------|------|-------------|
| `accessory` | string | Accessory code |
| `full_name` | string | Full name |
| `compatible_with` | list[string] | Compatible product families |
| `NOT_compatible_with` | list[string] | Incompatible product families |
| `reason` | string | Why it's incompatible |

---

## 8. Clarification Rules

Parameters the system must collect before recommending a product, in priority order.

```yaml
clarification_rules:
  required_parameters:
    - name: "filtration_purpose"
      aliases: ["filter type", "what to filter"]
      applies_to: ["all"]
      prompt: "What do you need to filter - particles or gases/odors?"
      priority: 1
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Parameter name |
| `aliases` | list[string] | Alternative names the user might use |
| `units` | list[string] | Accepted units (if applicable) |
| `applies_to` | list[string] | Which product families need this (`["all"]` = all) |
| `prompt` | string | Question to ask the user |
| `priority` | int | Order in which to ask (1 = first) |

**Current priority order:**

| Priority | Parameter | Applies To |
|----------|-----------|-----------|
| 1 | Filtration purpose | All |
| 2 | Installation location | All |
| 3 | Airflow | GDB, GDC, GDMI, GDP, GDF |
| 4 | Filter type | GDB, GDMI |
| 5 | Dimensions | All |

---

## 9. Assembly Configuration

Properties that automatically synchronize across all stages in a multi-stage assembly (e.g., pre-filter + main filter share the same duct dimensions).

```yaml
assembly:
  shared_properties:
    - "filter_width"
    - "filter_height"
    - "housing_width"
    - "housing_height"
    - "airflow_m3h"
```

When a dimension is set on one assembly stage, it automatically propagates to all sibling stages. Housing length is intentionally NOT shared — each stage derives its own from the graph.

---

## 10. Dimension Mapping

### Filter-to-Housing Size

Maps common filter dimensions to housing sizes (in mm).

```yaml
dimension_mapping:
  filter_to_housing:
    287: 300
    305: 300
    592: 600
    610: 600
    495: 500
    300: 300
    600: 600
    500: 500
    900: 900
    1200: 1200
```

### Corrosion Class Map

Material code to EN ISO 12944 corrosion class.

```yaml
corrosion_class_map:
  FZ: "C3"
  AZ: "C4"
  ZM: "C5"
  RF: "C5"
  SF: "C5.1"
```

### Housing Length Derivation

Derives housing length from filter depth, per product family.

```yaml
housing_length_derivation:
  GDMI:
    - max_depth: 450
      length: 600
    - max_depth: 99999
      length: 850
  GDC:
    - max_depth: 450
      length: 750
    - max_depth: 99999
      length: 900
  GDB:
    - max_depth: 292
      length: 550
    - max_depth: 450
      length: 750
    - max_depth: 99999
      length: 900
```

**How it works:** For a given filter depth, find the first entry where `depth ≤ max_depth` and use that `length`. Example: GDB with filter depth 300mm → first match is `max_depth: 450` → housing length = 750mm.

### Orientation Threshold

```yaml
orientation_threshold: 600
```

Width threshold (mm) for normalizing dimension orientation.

---

## 11. Material Codes Extended

Extended material definitions with multilingual extraction keywords.

```yaml
material_codes_extended:
  - code: "RF"
    aliases: ["STAINLESS", "STAINLESS STEEL", "ROSTFRI", "NIERDZEWNA"]
    extraction_keywords: ["stainless steel", "stainless", "nierdzewna", "rostfri", "edelstahl", "inox", "rf"]
```

| Field | Type | Description |
|-------|------|-------------|
| `code` | string | Material code |
| `aliases` | list[string] | Uppercase aliases |
| `extraction_keywords` | list[string] | Keywords for LLM extraction (multilingual) |

---

## 12. Defaults

```yaml
default_material: "FZ"
default_product_family: "GDB"
```

| Field | Type | Description |
|-------|------|-------------|
| `default_material` | string | Material used when none specified |
| `default_product_family` | string | Product family used when none specified |

---

## 13. Fallback Keywords

Keyword mappings used as a safety net when LLM extraction is unavailable.

### Application Keywords

```yaml
fallback_keywords:
  application_keywords:
    hospital: ["hospital", "szpital", "medical", "clinic"]
    kitchen: ["kitchen", "kuchnia", "restaurant"]
    office: ["office", "biuro", "commercial"]
```

### Environment Mapping

Maps keywords to internal environment IDs.

```yaml
  environment_mapping:
    outdoor: "ENV_OUTDOOR"
    rooftop: "ENV_OUTDOOR"
    hospital: "ENV_HOSPITAL"
    pool: "ENV_POOL"
    kitchen: "ENV_KITCHEN"
    atex: "ENV_ATEX"
    marine: "ENV_MARINE"
    pharma: "ENV_PHARMACEUTICAL"
```

---

## 14. Scribe Hints

Keywords that help the LLM infer product families from natural language.

```yaml
scribe_hints:
  product_inference:
    - keywords: ["insulated", "insulation", "condensation-proof"]
      product_family: "GDMI"
    - keywords: ["carbon", "activated carbon", "odor", "VOC"]
      product_family: "GDC"
      flex_variant: "GDC_FLEX"
    - keywords: ["pre-filter", "protector"]
      product_family: "GDP"
    - keywords: ["pocket filter", "bag filter", "particle filter"]
      product_family: "GDB"
```

| Field | Type | Description |
|-------|------|-------------|
| `keywords` | list[string] | If user mentions these words... |
| `product_family` | string | ...infer this product family |
| `flex_variant` | string | Optional variant for flexible configurations |

---

## 15. Completeness Check

Defines which fields must be present for a product specification to be considered "complete" for recommendation.

```yaml
completeness_required:
  - key: filter_dimensions
    fields: [housing_width, housing_height, filter_width, filter_height]
  - key: filter_depth
    fields: [housing_length, filter_depth]
  - key: airflow
    fields: [airflow_m3h]
```

Each entry requires at least ONE of the listed fields to have a value.

---

## 16. Parameter Routing

Maps user-facing parameter names to internal fields with validation rules.

```yaml
parameter_routing:
  airflow:
    field: "airflow_m3h"
    aliases: ["airflow", "airflow_m3h", "przepływ", "luftflöde"]
    route_to: "all_tags"
    skip_if_set: true
    validation:
      min: 500
      max: 100000
  filter_depth:
    field: "filter_depth"
    aliases: ["filter_depth", "depth", "djup"]
    route_to: "all_tags"
    skip_if_set: true
  housing_length:
    field: "housing_length"
    aliases: ["housing_length", "length", "längd", "długość"]
    route_to: "all_tags"
    skip_if_set: false
```

| Field | Type | Description |
|-------|------|-------------|
| `field` | string | Internal field name |
| `aliases` | list[string] | Names the user might use (multilingual) |
| `route_to` | string | Where to apply: `"all_tags"` = all products |
| `skip_if_set` | bool | Skip if already has a value |
| `validation.min` / `validation.max` | int | Value range |

---

## 17. Sample Questions

Example questions shown in the UI for each category.

```yaml
sample_questions:
  product_selection:
    label: "Product Selection"
    questions:
      - "I need a GDB housing for hospital ventilation, 3400 m³/h"
      - "Select carbon filter housing for 2000 m³/h kitchen exhaust"
  guardian_tests:
    label: "Guardian Tests"
    questions:
      - "I need GDB housing in galvanized steel (FZ) for a swimming pool"
      - "Hospital project - client wants cheap galvanized (FZ) housings"
```

---

## Quick Reference: What to Change Where

| I want to... | Config section | Example |
|-------------|---------------|---------|
| Add a new product family code | `entity_patterns.product_families.values` | Add `"NEW"` to the list |
| Add a new material | `material_environment_rules.material_hierarchy` | New entry with code, class, description |
| Add a new demanding environment | `material_environment_rules.demanding_environments` | New entry with name, aliases, required materials |
| Change clarification question order | `clarification_rules.required_parameters[].priority` | Change priority numbers |
| Add a product warning | `product_application_rules.product_capabilities[].warning_applications` | New trigger + message |
| Add an installation warning | `product_application_rules.installation_warnings` | New trigger + products + message |
| Add a dimension mapping | `dimension_mapping.filter_to_housing` | New `filter_size: housing_size` entry |
| Add housing length rule | `housing_length_derivation.<FAMILY>` | New `max_depth` + `length` entry |
| Add LLM keyword hints | `scribe_hints.product_inference` | New keywords + product_family |
| Change default material | `default_material` | Change from `"FZ"` to another code |
| Add multilingual keywords | `material_codes_extended[].extraction_keywords` | Add keywords in new language |
