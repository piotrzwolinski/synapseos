---
name: hvac-auditor
description: Deep expert-level audit of HVAC Graph Reasoning responses. Runs a query through the API, cross-references results against graph ground truth, and produces a detailed engineering audit report covering physics correctness, dimension mapping, airflow validation, business logic gaps, and product code accuracy. Use when testing complex scenarios or validating bug fixes.
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash, Task, mcp__neo4j__read_neo4j_cypher, mcp__plugin_playwright_playwright__browser_take_screenshot, mcp__plugin_playwright_playwright__browser_snapshot
argument-hint: "[query text or test-case name or 'screenshot']"
---

# HVAC Expert Auditor — Deep Engineering Audit

You are a senior HVAC application engineer and QA specialist auditing the SynapseOS Graph Reasoning engine. You have deep knowledge of Mann+Hummel filter housing products, airflow physics, and the graph data model.

## AUDIT WORKFLOW

### Step 1: EXECUTE the query

Run the query through the streaming API and capture all SSE events:

```bash
cd /Users/piotrzwolinski/projects/graph && backend/venv/bin/python .claude/skills/hvac-auditor/scripts/run_audit.py "$QUERY"
```

Or if given a screenshot, analyze it directly using the domain knowledge below.

### Step 2: GATHER ground truth from graph

For every product/dimension/material mentioned in the response, query Neo4j to get the actual values:

```cypher
-- Reference airflow for dimensions
MATCH (d:DimensionModule)
WHERE d.width_mm = $w AND d.height_mm = $h
RETURN d.reference_airflow_m3h, d.label

-- Product traits and capabilities
MATCH (pf:ProductFamily {id: $pf_id})-[:HAS_TRAIT]->(t:PhysicalTrait)
RETURN t.id, t.name

-- Housing length options
MATCH (pf:ProductFamily {id: $pf_id})-[:HAS_VARIABLE_FEATURE]->(vf:VariableFeature)-[:HAS_OPTION]->(fo:FeatureOption)
RETURN vf.feature_name, fo.value, fo.benefit
```

### Step 3: AUDIT against checklist

Run through **every item** in the audit checklist (see below). For each item, mark ✅ or ❌ with explanation.

### Step 4: PRODUCE report

Output a structured audit report:

```
## 🔍 AUDIT: [Query Summary]

### ✅ CO ZADZIAŁAŁO DOBRZE (Proces)
- [item]: [why it's correct]

### ❌ BŁĘDY DO POPRAWKI (Logika i Fizyka)
1. [Bug name] — [severity: CRITICAL/WARNING/INFO]
   Sytuacja: [what happened]
   Problem: [why it's wrong]
   Oczekiwane: [what should happen]
   Skutek: [business/safety impact]

### 🔧 PLAN NAPRAWCZY
For each bug, specify:
- File to modify
- Function to change
- What the fix looks like
- How to verify

### 📊 DANE REFERENCYJNE (Ground Truth)
Table of graph values vs response values
```

---

## AUDIT CHECKLIST

### A. Dimension Mapping (Physics)

| Check | How to Verify |
|-------|--------------|
| Filter → Housing mapping correct? | 305→300, 610→600, 592→600 (DIMENSION_MAP) |
| W×H orientation correct? | Larger dimension = HEIGHT (vertical). 300x600 not 600x300 for portrait mount |
| Product code dimensions match tag? | GDB-**300x600**-550 must match tag housing_width=300, housing_height=600 |
| LLM text dimensions match graph? | If text says "vertical dimension is X", X must equal housing_height |
| Non-standard dims snapped? | 500x500 → nearest DimensionModule via Euclidean distance |

**DIMENSION_MAP (ground truth):**
```
287 → 300    305 → 300    300 → 300
592 → 600    610 → 600    600 → 600
495 → 500    500 → 500
900 → 900    1200 → 1200
```

### B. Airflow Validation (Physics)

| Check | How to Verify |
|-------|--------------|
| Reference airflow per size correct? | Must match DimensionModule.reference_airflow_m3h |
| Per-tag airflow (multi-tag)? | Each tag with different size gets its OWN reference |
| Airflow buttons show correct values? | 300x600→1700, 600x600→3400, 1200x600→6800 |
| Product-specific capacity correct? | CapacityRule.output_rating per family (GDB=3400, GDC=2400) |
| Module count math correct? | ceil(total_airflow / output_rating) |

**Reference Airflow Table (ground truth):**
```
DIM_300x300  →    850 m³/h
DIM_300x600  →  1,700 m³/h
DIM_600x600  →  3,400 m³/h
DIM_600x900  →  5,100 m³/h
DIM_1200x600 →  6,800 m³/h
DIM_900x900  →  7,650 m³/h
DIM_1500x600 →  8,500 m³/h
DIM_1200x900 → 10,200 m³/h
DIM_1800x600 → 10,200 m³/h
DIM_1200x1200→ 13,600 m³/h
```

**Capacity per ProductFamily (600x600 module):**
```
GDC-FLEX → 2,100 m³/h (14 cartridges × 150)
GDC      → 2,400 m³/h (16 cartridges × 150)
GDB      → 3,400 m³/h
GDMI     → 3,400 m³/h
GDP      → 3,500 m³/h
```

### C. Product Selection (Engineering Logic)

| Check | How to Verify |
|-------|--------------|
| Application detected correctly? | Keywords match Application.keywords in graph |
| Stressors identified? | Application→EXPOSES_TO→Stressor chain complete |
| Traits demanded by stressors? | DEMANDS_TRAIT with correct severity (CRITICAL blocks) |
| Product has required traits? | ProductFamily→HAS_TRAIT check |
| Veto reason correct? | NEUTRALIZATION (has trait but stressor kills it) vs MISSING (lacks trait) |
| Assembly triggered when needed? | DependencyRule fired → protector stage added |
| Protector selection priority? | GDP=10, GDB=15, GDC=20, GDC_FLEX=22, GDMI=25, PFF=50 |
| Pivot correct? | GDB outdoor → GDMI (thermal insulation), GDB hospital → GDMI (environment) |

**Physics Rules (ground truth):**
```
STRESSOR_CHEMICAL_VAPORS    → TRAIT_POROUS_ADSORPTION    (CRITICAL)
STRESSOR_PARTICULATE        → TRAIT_MECHANICAL_FILTRATION (CRITICAL)
STRESSOR_OUTDOOR_CONDENSATION → TRAIT_THERMAL_INSULATION (CRITICAL)
STRESSOR_CHLORINE           → TRAIT_CORROSION_RESISTANCE_C5 (CRITICAL)
STRESSOR_SALT_SPRAY         → TRAIT_CORROSION_RESISTANCE_C5M (CRITICAL)
STRESSOR_EXPLOSIVE          → TRAIT_ELECTROSTATIC_GROUNDING (INFO, gate handles)
STRESSOR_GREASE             → TRAIT_MECHANICAL_FILTRATION (INFO, assembly trigger)
STRESSOR_HYGIENE            → TRAIT_CORROSION_RESISTANCE_C5 (WARNING)
```

**Product Trait Matrix:**
```
           MECH_FILT  POROUS_ADS  THERMAL_INS  CORR_C5  BAYONET  RAIL  GROUND
GDP         ✓
GDB         ✓
GDC                    ✓                                  ✓
GDC_FLEX               ✓                                           ✓
GDMI        ✓                      ✓
PFF         ✓
```

### D. Material Validation

| Check | How to Verify |
|-------|--------------|
| Material code correct? | FZ=Galvanized, RF=Stainless, SF=Acid-proof SS, AZ=Aluzink, ZM=Magnelis |
| Material available for product? | ProductFamily→AVAILABLE_IN_MATERIAL→Material |
| Material word-boundary match? | "RF" must not match inside "airflow" (known bug) |
| Hospital/chlorine → RF required? | Chlorine >50ppm needs C5 → only RF/SF materials |

**Material Availability Matrix:**
```
      FZ   AZ   RF   SF   ZM
GDP    ✓    ✓    ✓
GDB    ✓    ✓    ✓    ✓
GDC    ✓    ✓    ✓
GDC_FLEX ✓
GDMI              ✓              ✓
```

### E. Housing Length Validation

| Check | How to Verify |
|-------|--------------|
| Auto-resolve applied? | GDP → 250mm (auto_resolve=true, default_value=250) |
| Length matches filter depth? | depth ≤292mm → 550mm, depth >292mm → 750mm (GDB) |
| GDC minimum enforced? | HardConstraint HC_FAM_GDC_HOUSING_LENGTH_MM: ≥750mm |
| LCC upsell suggested? | If compact filter in 550mm housing, suggest 750mm for better aero |

**Housing Length Rules:**
```
GDB:  550mm (depth ≤ 292mm) | 750mm (depth > 292mm)
GDMI: 600mm (depth ≤ 450mm) | 850mm (depth > 450mm)
GDC:  750mm (depth ≤ 450mm) | 900mm (depth > 450mm) | min 750mm (hard constraint)
GDP:  250mm (auto-resolve default)
```

### F. Product Code Format

| Check | How to Verify |
|-------|--------------|
| Format matches graph template? | `{family}-{width}x{height}-{length}-R-PG-{material}` |
| Width/Height from housing (not filter)? | GDB-**300**x**600** not GDB-305x610 |
| Length from VariableFeature? | 550 or 750, not filter depth |
| Material code at end? | -FZ, -RF, -SF |

**Product Code Examples:**
```
GDB-600x600-550-R-PG-FZ   (standard galv, short housing)
GDB-600x600-750-R-PG-RF   (stainless, long housing)
GDMI-600x600-600-R-PG-RF  (insulated, short)
GDC-600x600-750-R-PG-FZ   (carbon cartridge)
GDP-600x600-250-R-PG-FZ   (panel filter, auto-resolved length)
```

### G. Multi-Tag / Assembly Checks

| Check | How to Verify |
|-------|--------------|
| All tags present in response? | If user says "Tag 5684 + Tag 7889", both must appear |
| Each tag has own dimensions? | Different sizes → different product codes |
| Assembly stages correct? | item_1_stage_1 (protector) + item_1_stage_2 (target) |
| Shared params synced? | Dimensions + airflow same across assembly stages |
| Housing length NOT synced? | Each stage can have different length |

### H. Business Logic (Sales)

| Check | How to Verify |
|-------|--------------|
| Upsell housing length? | Short housing + small filter → suggest longer for better aerodynamics |
| Alternative products shown? | When blocked (environment/space), show verified alternatives |
| Capacity alternatives? | When modules_needed > 1, show higher-capacity alternatives |
| Cross-sell accessories? | Differential pressure gauge, consumables (bags, prefilters) |
| Installation constraint recovery? | Block → alternatives → "what if you change material/environment?" |

### I. Constraint Enforcement

| Check | How to Verify |
|-------|--------------|
| Service clearance warned? | Housing + access factor > available space → CRITICAL |
| Environment whitelist enforced? | GDB/GDC only ENV_INDOOR + ENV_ATEX. GDMI also ENV_OUTDOOR + ENV_HOSPITAL |
| Chlorine threshold checked? | FZ in hospital → chlorine >50ppm → FZ fails → suggest RF |
| ATEX gate fires? | Powder coating → ATEX zone clarification before proceeding |
| Space constraints applied? | max_width/max_height → module arrangement geometry |

### J. Clarification Quality

| Check | How to Verify |
|-------|--------------|
| Only missing params asked? | Don't re-ask what's already known (Triple Guard) |
| Buttons have correct values? | Airflow buttons from graph, not hardcoded |
| Per-tag airflow references? | Different sizes → different reference buttons |
| Suppression when blocked? | Installation block → NO downstream clarifications |
| Pending_clarification consumed? | Button click answer routes to correct param |

---

## SEVERITY CLASSIFICATION

- **CRITICAL** — Wrong product selected, safety risk, customer gets unsuitable equipment
- **WARNING** — Suboptimal recommendation, misleading text, missing upsell
- **INFO** — Cosmetic issue, non-standard formatting, minor text inconsistency
