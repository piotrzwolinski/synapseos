# AI Solutions Finder — Graph Data Dictionary

Complete reference of all node types, relationships, and properties in the knowledge graph.

**Graph database:** FalkorDB (Cypher query language)
**Current stats:** ~1,000 nodes, ~3,000 relationships

---

## 1. Graph Overview by Layer

| Layer | Purpose | Node Count | Key Node Types |
|-------|---------|-----------|----------------|
| **Layer 1 — Inventory** | What we sell | ~900 | ProductFamily, ProductVariant, DimensionModule, Material, FilterConsumable, TransitionPiece |
| **Layer 2 — Physics** | How the world works | ~80 | EnvironmentalStressor, PhysicalTrait, Environment, Application, InstallationConstraint, DependencyRule |
| **Layer 3 — Playbook** | Decision logic | ~120 | LogicGate, Parameter, VariableFeature, CapacityRule, SizeProperty, ClarificationRule |
| **Layer 4 — State** | Per-session project | dynamic | Session, ActiveProject, TagUnit, ConversationTurn |

---

## 2. Layer 1 — Inventory

### ProductFamily (12 nodes)

The central hub node. Each product family (GDB, GDC, GDMI, GDP, etc.) is a node with all structural and constraint data.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | `"FAM_GDP"` |
| `name` | string | Display name | `"GDP Planfilterskåp"` |
| `type` | string | Product category | `"Panel Filter Housing"` |
| `description` | string | Product description | |
| `construction_type` | string | Build type | `"SINGLE_WALL_UNINSULATED"`, `"BOLTED"`, `"WELDED"` |
| `default_material` | string | Default material code | `"FZ"` |
| `selection_priority` | int | Lower = preferred for protector role | `10` |
| `indoor_only` | bool | Environment restriction | `true` / `false` |
| `allowed_environments` | list | Which environments this product works in | |
| `compatible_filter_types` | list | Filter types this housing accepts | |
| `code_format` | string | Product code template | |
| `max_filter_depth_mm` | int | Maximum filter depth | |
| `hinge_type` | string | Door hinge style | |
| `lock_type` | string | Locking mechanism | |
| `service_access_type` | string | How filters are serviced | |
| `service_access_factor` | float | Clearance multiplier | |

**Key relationships from ProductFamily:**

| Relationship | To | Count | Description |
|-------------|-----|-------|-------------|
| `AVAILABLE_IN_SIZE` | DimensionModule | 255 | Which sizes are available |
| `HAS_VARIANT` | ProductVariant | 255 | Pre-computed product configurations |
| `HAS_COMPATIBLE_TRANSITION` | TransitionPiece | 165 | Compatible duct transitions |
| `AVAILABLE_IN_MATERIAL` | Material | 49 | Which materials are offered |
| `HAS_CAPACITY` | CapacityRule | 29 | Airflow capacity per size |
| `HAS_TRAIT` | PhysicalTrait | 19 | Product capabilities |
| `HAS_VARIABLE_FEATURE` | VariableFeature | 18 | Configurable features |
| `HAS_INSTALLATION_CONSTRAINT` | InstallationConstraint | 16 | Where it can/cannot be installed |
| `HAS_OPTION` | Option | 15 | Available options |
| `HAS_LENGTH_VARIANT` | VariantLength | 11 | Available housing lengths |
| `HAS_COMPATIBLE_ACCESSORY` | Accessory | 10 | Compatible accessories |
| `INCOMPATIBLE_WITH` | Accessory | 4 | Incompatible accessories |
| `HAS_HARD_CONSTRAINT` | HardConstraint | 4 | Physical limits that cannot be overridden |
| `VULNERABLE_TO` | Risk | 4 | Risks this product is susceptible to |

---

### DimensionModule (273 nodes)

Available size configurations for each product family.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | |
| `label` | string | Display label | `"600x600"` |
| `width_mm` | int | Module width | `600` |
| `height_mm` | int | Module height | `600` |
| `reference_airflow_m3h` | int | Rated airflow for this size | `3400` |
| `reference_length_mm` | int | Reference housing length | |
| `unit_weight_kg` | int | Weight per module | |
| `weight_per_mm_length` | float | Weight scaling factor | |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `DETERMINES_PROPERTY` | SizeProperty | Size-specific properties (airflow, weight per length) |

---

### ProductVariant (255 nodes)

Pre-computed product configurations (family + size + length).

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | |
| `name` | string | Display name | |
| `product_family` | string | Parent family reference | `"GDB"` |
| `width_mm` | int | Housing width | `600` |
| `height_mm` | int | Housing height | `600` |
| `housing_length_mm` | int | Housing length | `750` |
| `reference_airflow_m3h` | float | Rated airflow | `3400.0` |
| `weight_kg` | float | Total weight | `25.0` |

---

### Material (5 nodes)

Available material options with corrosion class ratings.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | `"MAT_RF"` |
| `code` | string | Short code | `"RF"` |
| `name` | string | Short name | `"Stainless Steel"` |
| `full_name` | string | Full name | `"Stainless Steel (1.4301/304)"` |
| `corrosion_class` | string | EN ISO 12944 class | `"C5"` |
| `aliases` | list | Alternative names | `["STAINLESS", "ROSTFRI"]` |
| `extraction_keywords` | list | Keywords for detection | `["stainless", "nierdzewna", "inox"]` |
| `suitable_for` | list | Suitable environments | `["hospital", "food processing"]` |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `PROVIDES_TRAIT` | PhysicalTrait | What traits this material provides |
| `MEETS_REQUIREMENT` | Requirement | Which requirements it satisfies |

---

### TransitionPiece (33 nodes)

Duct transition adapters (rectangular to round).

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | |
| `name` | string | Display name | |
| `type` | string | Piece type | `"PT"` (flat), `"TT"` (conical) |
| `housing_width_mm` | int | Compatible housing width | `600` |
| `housing_height_mm` | int | Compatible housing height | `600` |
| `duct_diameter_mm` | int | Round duct diameter | `400` |
| `standard_length_mm` | int | Standard piece length | |
| `standard_material` | string | Default material | `"FZ"` |

---

### FilterConsumable (31 nodes)

Compatible filter elements.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `name` | string | Filter name | |
| `part_number` | string | Order number | |
| `filter_type` | string | Filter category | `"Bag"`, `"Compact"` |
| `efficiency_class` | string | Filtration efficiency | `"ePM1 55%"` |
| `dimensions` | string | Physical size | |

**Relationships:**

| Relationship | To | Count | Description |
|-------------|-----|-------|-------------|
| `COMPATIBLE_WITH` | DimensionModule | 1,496 | Which housing sizes this filter fits |

---

### CompetitorProduct (22 nodes)

Competitor products for cross-referencing.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | |
| `manufacturer` | string | Competitor brand | `"Camfil"` |
| `model` | string | Product model | |
| `category` | string | Product type | |
| `width_mm`, `height_mm`, `depth_mm` | int | Dimensions | |
| `iso_class` | string | Efficiency class | |
| `aliases` | list | Alternative names | |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `CROSS_REFERENCES` | FilterConsumable | MH equivalent consumable |
| `CROSS_REFERENCES` | ProductFamily | MH equivalent family |

---

### Accessory (11 nodes)

Available accessories for product families.

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Unique identifier |
| `name` | string | Accessory name |
| `description` | string | What it does |

---

## 3. Layer 2 — Domain Physics

### Environment (10 nodes)

Installation environments with their characteristics.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | `"ENV_MARINE"` |
| `name` | string | Display name | `"Marine"` |
| `description` | string | Environment description | |
| `humidity_exposure` | string | Humidity level | `"high"` |
| `temperature_variation` | string | Temperature range | `"extreme"` |
| `keywords` | list | Detection keywords | `["ship", "offshore", "coastal"]` |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `EXPOSES_TO` | EnvironmentalStressor | What stressors this environment creates |
| `REQUIRES_MATERIAL` | Material | Which materials are required |
| `TRIGGERS_GATE` | LogicGate | Logic gates activated by this environment |
| `HAS_RISK` | Risk | Risks associated with this environment |

---

### Application (11 nodes)

Application types (kitchen, hospital, pool, etc.).

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | `"APP_KITCHEN"` |
| `name` | string | Display name | `"Commercial Kitchen"` |
| `keywords` | list | Detection keywords | `["kitchen", "restaurant", "fryer"]` |
| `embedding` | list | Vector embedding | 3072-dimensional float array |
| `embedding_text` | string | Text used for embedding | |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `EXPOSES_TO` | EnvironmentalStressor | Stressors this application produces |
| `GENERATES` | Substance | Substances generated (grease, particles, etc.) |
| `TRIGGERS_GATE` | LogicGate | Logic gates activated by this application |
| `HAS_RISK` | Risk | Application-specific risks |
| `REQUIRES_RESISTANCE` | Requirement | Required material resistance |

---

### EnvironmentalStressor (13 nodes)

Environmental factors that affect product selection.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | `"STRESSOR_GREASE"` |
| `name` | string | Stressor name | `"Grease"` |
| `description` | string | What it does | |
| `category` | string | Stressor category | `"Chemical"`, `"Physical"` |
| `keywords` | list | Detection keywords | |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `DEMANDS_TRAIT` | PhysicalTrait | Which traits are needed to handle this stressor |

---

### PhysicalTrait (14 nodes)

Product capabilities that counter stressors.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | `"TRAIT_NEUTRALIZATION"` |
| `name` | string | Trait name | `"Neutralization Capability"` |
| `description` | string | What this trait does | |
| `category` | string | Trait category | |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `NEUTRALIZED_BY` | EnvironmentalStressor | Which stressors this trait addresses |

---

### InstallationConstraint (5 nodes)

Rules that block certain product/environment combinations.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | |
| `constraint_type` | string | Type of constraint | `"CROSS_NODE_THRESHOLD"` |
| `input_key` | string | Input parameter to check | |
| `operator` | string | Comparison operator | `"<"`, `">"` |
| `error_msg` | string | User-facing error message | |
| `severity` | string | How critical | `"CRITICAL"` |

---

### DependencyRule (4 nodes)

Rules that trigger multi-stage assemblies (e.g., pre-filter + main filter).

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Unique identifier |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `TRIGGERED_BY_STRESSOR` | EnvironmentalStressor | What stressor activates this rule |
| `UPSTREAM_REQUIRES_TRAIT` | PhysicalTrait | Trait needed in the upstream (protector) stage |
| `DOWNSTREAM_PROVIDES_TRAIT` | PhysicalTrait | Trait provided by the downstream (target) stage |

---

### HardConstraint (4 nodes)

Physical limits that auto-correct user input (e.g., minimum housing width).

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Unique identifier |
| `input_key` | string | Parameter being constrained |
| `operator` | string | Comparison operator |
| `error_msg` | string | Explanation shown to user |

---

## 4. Layer 3 — Playbook

### LogicGate (4 nodes)

Conditional physics checks that evaluate before product selection.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | |
| `name` | string | Gate name | |
| `condition_logic` | string | Evaluation logic | |
| `physics_explanation` | string | Why this constraint exists | |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `REQUIRES_DATA` | Parameter | What data is needed to evaluate |
| `MONITORS` | EnvironmentalStressor | What stressor this gate watches |

**Gate states:** `FIRED` (constraint applies), `PASSED` (constraint doesn't apply), `VALIDATION_REQUIRED` (need more data).

---

### Parameter (11 nodes)

Input parameters the system needs to collect.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | |
| `name` | string | Parameter name | `"Airflow"` |
| `type` | string | Data type | `"numeric"`, `"categorical"` |
| `unit` | string | Unit of measurement | `"m³/h"` |

---

### VariableFeature (17 nodes)

Configurable product features with options and defaults.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | |
| `name` | string | Feature name | |
| `property_key` | string | Key in the product specification | |
| `is_variable` | bool | Whether user can choose | |
| `question` | string | Clarification question to ask | |
| `why_needed` | string | Why this parameter matters | |
| `derivation_note` | string | How to auto-resolve if possible | |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `HAS_OPTION` | FeatureOption | Available options for this feature |
| `SELECTION_DEPENDS_ON` | Discriminator | What determines the selection |

---

### CapacityRule (29 nodes)

Airflow capacity rules per product size.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | |
| `input_requirement` | string | Required input | `"airflow_m3h"` |
| `module_descriptor` | string | Which module this applies to | |
| `output_rating` | int | Rated airflow capacity | `3400` |
| `assumption` | string | Assumptions for this rating | |

---

### SizeProperty (24 nodes)

Size-specific properties linked from DimensionModule.

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | string | Unique identifier | |
| `for_family` | string | Product family | `"GDB"` |
| `key` | string | Property name | `"reference_airflow_m3h"` |
| `display_name` | string | User-facing label | |
| `value` | int | Property value | `3400` |

---

## 5. Layer 4 — Session State

Stores per-session project data. Created dynamically as users interact with the system.

### Session

Root node per conversation session.

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Session UUID |
| `user_id` | string | Authenticated user |
| `created_at` | int | Creation timestamp (ms) |
| `last_active` | int | Last activity timestamp (ms) |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `WORKING_ON` | ActiveProject | Current project in this session |

---

### ActiveProject

Project context within a session.

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Project UUID |
| `session_id` | string | Parent session |
| `detected_family` | string | Active product family |
| `locked_material` | string | Locked material selection |
| `resolved_params` | string | JSON of all resolved parameters |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `HAS_UNIT` | TagUnit | Product specifications in this project |
| `TARGETS_FAMILY` | ProductFamily | Selected product family |
| `USES_MATERIAL` | Material | Selected material |
| `HAS_TURN` | ConversationTurn | Message history |

---

### TagUnit

Individual product specification within a project.

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Tag UUID |
| `tag_id` | string | Tag identifier (e.g., "item_1") |
| `session_id` | string | Parent session |
| `product_family` | string | Product family |
| `product_code` | string | Full product code |
| `housing_width` | int | Housing width (mm) |
| `housing_height` | int | Housing height (mm) |
| `filter_width` | int | Filter width (mm) |
| `filter_height` | int | Filter height (mm) |
| `airflow_m3h` | int | Airflow requirement |
| `quantity` | int | Number of units |
| `is_complete` | bool | All required parameters present |

**Relationships:**

| Relationship | To | Description |
|-------------|-----|-------------|
| `SIZED_AS` | DimensionModule | Selected size configuration |

---

### ConversationTurn

Individual messages in the conversation history.

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Turn UUID |
| `role` | string | `"user"` or `"assistant"` |
| `message` | string | Message content |
| `turn_number` | int | Sequential order |
| `created_at` | int | Timestamp (ms) |

---

## 6. Relationship Summary

The 10 most important relationship patterns:

| From | Relationship | To | What it means |
|------|-------------|-----|---------------|
| ProductFamily | `AVAILABLE_IN_SIZE` | DimensionModule | Product comes in these sizes |
| ProductFamily | `AVAILABLE_IN_MATERIAL` | Material | Product available in these materials |
| ProductFamily | `HAS_TRAIT` | PhysicalTrait | Product has these capabilities |
| Application | `EXPOSES_TO` | EnvironmentalStressor | This application creates these stressors |
| EnvironmentalStressor | `DEMANDS_TRAIT` | PhysicalTrait | This stressor requires these traits |
| Environment | `REQUIRES_MATERIAL` | Material | This environment requires these materials |
| ProductFamily | `HAS_INSTALLATION_CONSTRAINT` | InstallationConstraint | Installation restrictions |
| DimensionModule | `DETERMINES_PROPERTY` | SizeProperty | Size-specific properties (airflow, weight) |
| FilterConsumable | `COMPATIBLE_WITH` | DimensionModule | Which filter fits which housing size |
| DependencyRule | `TRIGGERED_BY_STRESSOR` | EnvironmentalStressor | What triggers multi-stage assembly |
