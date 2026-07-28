# SynapseOS Ontology Transfer: HVAC → Chemistry

**Date:** 2026-03-06
**Context:** Exploration of applying the SynapseOS 4-layer knowledge graph ontology to a new domain (industrial chemistry) using a Wacker SILRES BS 5133 product data sheet as example.

---

## 1. HVAC Ontology Export (Layer 1 & 2)

### Layer 1: Inventory

**ProductFamily (12 nodes):**

| ID | Name | Construction | Priority | Material | Environments |
|---|---|---|---|---|---|
| `FAM_GDP` | GDP Planfilterskåp | SINGLE_WALL_UNINSULATED | 10 | FZ | Indoor, ATEX, Coastal |
| `FAM_GDB` | GDB Kanalfilterskåp | SINGLE_WALL_UNINSULATED | 15 | FZ | Indoor, ATEX, Coastal |
| `FAM_GDC` | GDC Patronfilterskåp | SINGLE_WALL_UNINSULATED | 20 | FZ | Indoor, ATEX, Coastal |
| `FAM_GDC_FLEX` | GDC FLEX | SINGLE_WALL_UNINSULATED | 22 | FZ | Indoor, ATEX, Coastal |
| `FAM_GDMI` | GDMI Modulfilterskåp | DOUBLE_WALL_INSULATED | 25 | FZ | Indoor, ATEX, Hospital, Pharma, Coastal |
| `FAM_GDMI_FLEX` | GDMI FLEX | DOUBLE_WALL_INSULATED | 20 | FZ | Indoor, ATEX, Kitchen, Coastal |
| `FAM_PFF` | PFF Planfilterram | STAMPED_MESH_BENT_FRAME | 50 | FZ | — |

**Accessories:** BFF (frame), PT (flat transition), TT (conical transition), EXL (lock), Filter Profil (profile)

**PhysicalTrait → ProductFamily mapping:**

| Trait | Primary on |
|---|---|
| `TRAIT_MECHANICAL_FILTRATION` | GDP, GDB, PFF |
| `TRAIT_POROUS_ADSORPTION` | GDC, GDC_FLEX |
| `TRAIT_THERMAL_INSULATION` | GDMI |
| `TRAIT_EXTRACTABLE_RAIL` | GDC_FLEX, GDMI_FLEX |

**VariableFeature (17):** Housing Length, Airflow, Connection Type, Frame Depth — per product family.

**SizeProperty:** 44 nodes (dimension/capacity lookup tables).

### Layer 2: Domain / Physics

**Causal chain structure:**

```
Application/Environment
    → EXPOSES_TO → EnvironmentalStressor
        → DEMANDS_TRAIT → PhysicalTrait (what's needed)
        → NEUTRALIZED_BY ← PhysicalTrait (what it kills)
        → CAUSES → Risk → TRIGGERS_STRATEGY → Strategy
    → TRIGGERS_GATE → LogicGate → REQUIRES_DATA → Parameter
```

**EnvironmentalStressor (13) — each DEMANDS a trait:**

| Stressor | Demands Trait | Severity |
|---|---|---|
| `STRESSOR_CHLORINE` | `TRAIT_CORROSION_RESISTANCE_C5` | CRITICAL |
| `STRESSOR_OUTDOOR_CONDENSATION` | `TRAIT_THERMAL_INSULATION` | CRITICAL |
| `STRESSOR_PARTICULATE_EXPOSURE` | `TRAIT_MECHANICAL_FILTRATION` | CRITICAL |
| `STRESSOR_GREASE_EXPOSURE` | `TRAIT_MECHANICAL_FILTRATION` | INFO |
| `STRESSOR_SALT_SPRAY` | `TRAIT_CORROSION_RESISTANCE_C5M` | CRITICAL |
| `STRESSOR_CHEMICAL_VAPORS` | `TRAIT_POROUS_ADSORPTION` | CRITICAL |
| `STRESSOR_FORMALDEHYDE` | `TRAIT_IMPREGNATED_MEDIA` | CRITICAL |
| `STRESSOR_COASTAL_SALT_AIR` | `TRAIT_CORROSION_RESISTANCE_C5` | CRITICAL |

**NEUTRALIZED_BY (trait killed by stressor):**

| Trait | Neutralized by | Severity |
|---|---|---|
| `TRAIT_POROUS_ADSORPTION` | `STRESSOR_PARTICULATE_EXPOSURE` | CRITICAL |
| `TRAIT_POROUS_ADSORPTION` | `STRESSOR_GREASE_EXPOSURE` | CRITICAL |
| `TRAIT_CORROSION_RESISTANCE_C3` | `STRESSOR_CHLORINE` | CRITICAL |
| `TRAIT_CORROSION_RESISTANCE_C3` | `STRESSOR_SALT_SPRAY` | CRITICAL |
| `TRAIT_CORROSION_RESISTANCE_C3` | `STRESSOR_H2S_CORROSION` | CRITICAL |

**Risk (6):** RISK_CLOG (CRITICAL→BLOCK), RISK_CORR (HIGH→WARN), RISK_HYG (CRITICAL→BLOCK), RISK_COND (HIGH→WARN), RISK_EXPLO (CRITICAL→BLOCK), RISK_GREASE.

**LogicGate (4):** GATE_DEW_POINT, GATE_GREASE_LOAD, GATE_CHLORINE_EXPOSURE, GATE_ATEX_ZONE — each monitors a stressor and requires specific parameters.

**DependencyRule (4):** Kitchen/dusty/paint environments mandate mechanical pre-filtration upstream of carbon stage.

---

## 2. Ontology Mapping: HVAC → Chemistry

The ontology is **domain-agnostic by design**. Same node types, same edge types, different content.

| HVAC Concept | Chemistry Equivalent | Example (SILRES) |
|---|---|---|
| `ProductFamily` | ProductFamily | SILRES BS (Silicone Fluid Emulsions) |
| `ProductVariant` | Product | SILRES BS 5133 |
| `PhysicalTrait` | PhysicalTrait | TRAIT_WATER_REPELLENCY, TRAIT_REACTIVE_PDMS |
| `VariableFeature` | VariableFeature | FEAT_ADDITION_RATIO, FEAT_DILUTION_RATIO |
| `SizeProperty` | TechnicalProperty | pH 5-8, density 1 g/cm³, viscosity 100 mPa·s |
| `Material` | Substrate | Glass Mineral Wool, Stone Mineral Wool |
| `Application` | Application | Insulation Manufacturing |
| `Environment` | ProcessCondition | Fiberizing Unit, Spray Application |
| `EnvironmentalStressor` | ChemicalStressor | Moisture Ingress, Binder Incompatibility, pH Deviation |
| `InstallationConstraint` | ProcessConstraint | pH range 5-8, max addition ratio 0.3 wt% |
| `DependencyRule` | DependencyRule | Compatibility test before production |

**What stays identical:** Graph structure, edge types (DEMANDS_TRAIT, NEUTRALIZED_BY, TRIGGERS_GATE, CAUSES, TRIGGERS_STRATEGY), engine pipeline, `universal_engine.py`.

**What changes:** Node content, tenant config (`tenants/wacker/`), Scribe hints, prompt templates.

---

## 3. Full Graph for SILRES BS 5133

### Layer 1 Nodes

**Product:**
- `PROD_SILRES_BS_5133` — Aqueous emulsion of reactive PDMS. Water repellency for mineral wool.

**TechnicalProperty:** pH 5-8, solid 60 wt%, white liquid, density 1 g/cm³, viscosity 100 mPa·s (Brookfield).

**PhysicalTrait:**
- `TRAIT_WATER_REPELLENCY` (primary) — Hydrophobic monolayer via Si-O-Si crosslinking
- `TRAIT_CARBOHYDRATE_BINDER_COMPAT` (primary) — Optimized for starch/sugar/dextrin binders
- `TRAIT_WATER_DILUTABLE` — Dilutable with any quantity of water
- `TRAIT_REACTIVE_PDMS` — Crosslinks permanently on fiber surface

**Substrate:** Glass Mineral Wool, Stone Mineral Wool (max 0.3 wt%).

**BinderType:** Carbohydrate (HIGH hydrophilicity, optimized), Phenolic (LOW, not optimized).

**VariableFeature:** Addition Ratio (wt%), Dilution Ratio, Application Method.

### Layer 2 Nodes

**EnvironmentalStressor (6):**

| ID | Name | Severity |
|---|---|---|
| `STRESSOR_MOISTURE_INGRESS` | Moisture Ingress | CRITICAL |
| `STRESSOR_BINDER_HYDROPHILICITY` | Binder Hydrophilicity | HIGH |
| `STRESSOR_BINDER_INCOMPATIBILITY` | Binder-Silicone Incompatibility | CRITICAL |
| `STRESSOR_EMULSION_AGING` | Emulsion Aging / Shelf Life | HIGH |
| `STRESSOR_PH_DEVIATION` | pH Deviation | HIGH |
| `STRESSOR_OVERDOSING` | Silicone Overdosing | WARNING |

**DEMANDS_TRAIT:**
- MOISTURE_INGRESS → TRAIT_WATER_REPELLENCY (CRITICAL)
- BINDER_HYDROPHILICITY → TRAIT_CARBOHYDRATE_BINDER_COMPAT (HIGH)
- BINDER_INCOMPATIBILITY → TRAIT_REACTIVE_PDMS (CRITICAL)

**NEUTRALIZED_BY:**
- TRAIT_WATER_REPELLENCY ← STRESSOR_BINDER_INCOMPATIBILITY (CRITICAL)
- TRAIT_WATER_REPELLENCY ← STRESSOR_EMULSION_AGING (HIGH)
- TRAIT_REACTIVE_PDMS ← STRESSOR_PH_DEVIATION (CRITICAL)
- TRAIT_CARBOHYDRATE_BINDER_COMPAT ← STRESSOR_OVERDOSING (WARNING)

**Risk (4):** Insulation Degradation, Emulsion Break, Incomplete Cure, Binder Failure.

**LogicGate (3):** pH Compatibility (5-8), Binder Compatibility (carbohydrate whitelist), Dosage Limit (≤0.3 wt%).

**Strategy (4):** Mandatory Compatibility Test, Apply Without Delay, Increase Dosage, Block pH Out of Range.

**ProcessConstraint (3):** PC_PH_RANGE (5-8), PC_MAX_ADDITION_RATIO (≤0.3), PC_BINDER_WHITELIST (carbohydrate).

### Causal Chains

```
APP_INSULATION_MANUFACTURING
  ├── EXPOSES_TO → STRESSOR_MOISTURE_INGRESS
  │     ├── DEMANDS → TRAIT_WATER_REPELLENCY ← BS_5133 HAS ✓
  │     └── CAUSES → RISK_INSULATION_DEGRADATION → STRAT_INCREASE_DOSAGE
  │
  ├── EXPOSES_TO → STRESSOR_BINDER_INCOMPATIBILITY
  │     ├── DEMANDS → TRAIT_REACTIVE_PDMS ← BS_5133 HAS ✓
  │     ├── NEUTRALIZES → TRAIT_WATER_REPELLENCY (if wrong binder!)
  │     └── CAUSES → RISK_INCOMPLETE_CURE → STRAT_MANDATORY_COMPATIBILITY_TEST
  │
  ├── GATE_PH_COMPATIBILITY
  │     ├── MONITORS → STRESSOR_PH_DEVIATION → NEUTRALIZES TRAIT_REACTIVE_PDMS
  │     ├── CAUSES → RISK_EMULSION_BREAK → STRAT_BLOCK_PH_OUT_OF_RANGE
  │     └── REQUIRES_DATA → PARAM_PROCESS_PH
  │
  ├── GATE_BINDER_COMPATIBILITY → REQUIRES_DATA → PARAM_BINDER_TYPE
  └── GATE_DOSAGE_LIMIT → MONITORS → STRESSOR_OVERDOSING → RISK_BINDER_FAILURE
```

---

## 4. Graph Traversal Example

**Query:** "What is the recommended dosage range for Stone Wool?"

**Scribe output:**
```json
{
  "detected_intent": "property_query",
  "detected_property": "addition_ratio",
  "detected_substrate": "stone_mineral_wool"
}
```

Intent is `property_query` (asking about a property value), NOT `product_recommendation` (asking which product to use). This affects routing — shorter traversal, no full trait-matching/veto pipeline.

**Traversal:**

1. **Substrate resolution:** `SUB_STONE_MINERAL_WOOL`
2. **Product match:** `PROD_SILRES_BS_5133` via `COMPATIBLE_WITH {max_addition_ratio: 0.3}`
3. **VariableFeature:** `FEAT_ADDITION_RATIO` — unit: wt%, basis: dry final product weight
4. **ProcessConstraint:** `PC_MAX_ADDITION_RATIO` — threshold ≤ 0.3 wt%
5. **Context (why this range?):** `STRESSOR_BINDER_HYDROPHILICITY` — source_quote from PDF
6. **Strategies:** MANDATORY_COMPATIBILITY_TEST + APPLY_WITHOUT_DELAY

### Reasoning Report

```
REASONING_REPORT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PRODUCT MATCH:
  ✓ SILRES BS 5133 — Silicone Fluid Emulsion (reactive PDMS)
  ✓ Compatible with Stone Mineral Wool

DOSAGE:
  • Recommended range: up to 0.3 wt% (based on dry final product weight)
  • Reason for upper bound: carbohydrate-based binders are hydrophilic,
    requiring higher silicone dosage to compensate
  • General recommendation cannot be given — individual tests mandatory

TRAIT SATISFACTION:
  ✓ TRAIT_WATER_REPELLENCY          — primary function
  ✓ TRAIT_CARBOHYDRATE_BINDER_COMPAT — optimized for this binder type
  ✓ TRAIT_REACTIVE_PDMS             — permanent crosslinked coating

ACTIVE WARNINGS:
  ⚠ Exact dosage depends on:
    - Desired water repellency level (PARAM_TARGET_REPELLENCY — unknown)
    - Binder type used (PARAM_BINDER_TYPE — unknown)
    - Process pH (PARAM_PROCESS_PH — unknown, must be 5–8)
  ⚠ STRAT_APPLY_WITHOUT_DELAY — diluted mixture has limited shelf life
  ⚠ STRAT_MANDATORY_COMPATIBILITY_TEST — always required per plant

CLARIFICATIONS NEEDED:
  1. What type of binder system is used?
  2. What is the pH of the binder mixture / process water? (must be 5–8)

✓ KNOWN: addition_ratio ≤ 0.3 wt% — DO NOT ask about dosage range.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### LLM Response

> **For stone mineral wool, the recommended dosage of SILRES BS 5133 is up to 0.3 wt%** (based on dry final product weight).
>
> This upper limit is specific to stone wool because carbohydrate-based binders used in stone wool production are more hydrophilic than traditional phenolic resins, requiring a higher silicone dosage to achieve adequate water repellency.
>
> **Important caveats:**
> - The exact dosage within the 0–0.3% range depends on your desired water repellency level and the specific binder formulation used in your plant
> - A **specific compatibility test is always mandatory** — no general recommendation can be given due to the variety of binder types and additives across production lines
> - Once diluted into the binder mixture, **apply without delay** — shelf life of the diluted mixture is limited
>
> To help refine the recommendation further:
> 1. **What binder system do you use?** (starch-based, modified starch, sugar-based?)
> 2. **What is the pH of your binder mixture?** (SILRES BS 5133 requires pH 5–8 for emulsion stability)

### Traversal Example 2: "Can I use this product in a phenolic resin system?"

**Scribe output:**
```json
{
  "detected_intent": "compatibility_check",
  "detected_product": "SILRES_BS_5133",
  "detected_binder_type": "phenolic"
}
```

**Traversal:**

1. **Product resolution:** `PROD_SILRES_BS_5133`
2. **Binder match:** `BINDER_PHENOLIC` — NOT in `OPTIMIZED_FOR` edge
3. **ProcessConstraint:** `PC_BINDER_WHITELIST` — valid_set: `[carbohydrate]` — **VIOLATION**
4. **LogicGate:** `GATE_BINDER_COMPATIBILITY` fires — `phenolic NOT IN [carbohydrate]` → DEMAND_COMPATIBILITY_TEST
5. **Stressor activated:** `STRESSOR_BINDER_INCOMPATIBILITY` (CRITICAL)
6. **Risk:** `RISK_INCOMPLETE_CURE` — PDMS may not crosslink properly
7. **Strategy:** `STRAT_MANDATORY_COMPATIBILITY_TEST` (REQUIRE_TEST)

**Reasoning Report:**
```
COMPATIBILITY CHECK:
  ✗ SILRES BS 5133 is optimized for CARBOHYDRATE binders
  ✗ Phenolic resin NOT in validated binder list
  ⚠ STRESSOR_BINDER_INCOMPATIBILITY activated (CRITICAL)
  ⚠ RISK_INCOMPLETE_CURE — PDMS may fail to crosslink

CONSTRAINT VIOLATION:
  PC_BINDER_WHITELIST: "SILRES BS 5133 is optimized for carbohydrate-based
  binders. Binder type 'phenolic' requires mandatory compatibility testing
  before production use."

STRATEGY: STRAT_MANDATORY_COMPATIBILITY_TEST
  → Do NOT recommend for production without plant-specific testing.
```

**LLM Response:**

> SILRES BS 5133 has been **specifically developed and optimized for carbohydrate-based binders** (starch, sugar, dextrin). It is **not validated for phenolic resin systems**.
>
> This does not mean it cannot work — but there is a **critical risk of incomplete crosslinking** if the silicone emulsion is incompatible with your specific phenolic formulation. This would result in non-durable water repellency that washes off over time.
>
> **Before any production use, a mandatory compatibility test at your plant is required.** Contact Wacker Chemie technical support for guidance on testing protocols.

### Traversal Example 3: "What happens if our process water is pH 4?"

**Scribe output:**
```json
{
  "detected_intent": "constraint_check",
  "detected_parameter": "process_ph",
  "detected_value": 4
}
```

**Traversal:**

1. **ProcessConstraint:** `PC_PH_RANGE` — min: 5, max: 8 — input: 4 → **VIOLATION (CRITICAL)**
2. **LogicGate:** `GATE_PH_COMPATIBILITY` fires — `4 < 5` → RISK
3. **Stressor activated:** `STRESSOR_PH_DEVIATION` (HIGH)
4. **NEUTRALIZED_BY:** `TRAIT_REACTIVE_PDMS` ← `STRESSOR_PH_DEVIATION` — PDMS crosslinking fails
5. **Risk:** `RISK_EMULSION_BREAK` (CRITICAL) — phase separation
6. **Strategy:** `STRAT_BLOCK_PH_OUT_OF_RANGE` (REFUSE_CONFIGURATION)

**Reasoning Report:**
```
CONSTRAINT VIOLATION:
  ✗ PC_PH_RANGE: Process pH 4 is BELOW minimum 5
    error: "Process pH 4 is outside stable range (5-8).
           Emulsion may break. Adjust pH before adding SILRES BS 5133."
    severity: CRITICAL

TRAIT NEUTRALIZATION:
  ✗ TRAIT_REACTIVE_PDMS neutralized by STRESSOR_PH_DEVIATION
    → PDMS may crosslink prematurely in tank or emulsion breaks entirely

RISK:
  ✗ RISK_EMULSION_BREAK — phase separation, uneven coating, blocked nozzles

STRATEGY: STRAT_BLOCK_PH_OUT_OF_RANGE (REFUSE_CONFIGURATION)
  → Do NOT add SILRES BS 5133 to pH 4 mixture.
```

**LLM Response:**

> **Do not add SILRES BS 5133 to a pH 4 process mixture.** The product is stable only in the pH 5–8 range.
>
> At pH 4, the emulsion will likely **break (phase separate)** — the silicone oil separates from the water phase. This causes:
> - **Uneven coating** on mineral fibers (patchy hydrophobic treatment)
> - **Blocked spray nozzles** from coagulated silicone
> - **Premature crosslinking** of reactive PDMS in the tank rather than on fiber surfaces
>
> **Action required:** Adjust your process water pH to at least 5.0 before adding SILRES BS 5133 to the binder mixture.

### Traversal Example 4: "We need water repellency for glass wool, 5000 m³/h line"

**Scribe output:**
```json
{
  "detected_intent": "product_recommendation",
  "detected_substrate": "glass_mineral_wool",
  "detected_application": "insulation_manufacturing",
  "detected_line_capacity": "5000 m3/h"
}
```

**Traversal:**

1. **Application:** `APP_INSULATION_MANUFACTURING`
2. **Stressor discovery:** MOISTURE_INGRESS, BINDER_HYDROPHILICITY, BINDER_INCOMPATIBILITY
3. **Trait demands:** TRAIT_WATER_REPELLENCY, TRAIT_CARBOHYDRATE_BINDER_COMPAT, TRAIT_REACTIVE_PDMS
4. **Candidate:** `PROD_SILRES_BS_5133` — all 3 traits satisfied ✓
5. **Substrate match:** `SUB_GLASS_MINERAL_WOOL` via `COMPATIBLE_WITH`
6. **VariableFeature check:** `FEAT_ADDITION_RATIO` — auto_resolve: false → needs clarification
7. **Note:** Line capacity (5000 m³/h) is **not a graph parameter** — no `VariableFeature` maps to it
8. **Missing parameters:** binder_type, process_ph, target_repellency, addition_ratio
9. **Strategies:** MANDATORY_COMPATIBILITY_TEST

**Reasoning Report:**
```
PRODUCT MATCH:
  ✓ SILRES BS 5133 — all trait demands satisfied for glass mineral wool

MISSING PARAMETERS:
  ? PARAM_BINDER_TYPE — needed for GATE_BINDER_COMPATIBILITY
  ? PARAM_PROCESS_PH — needed for GATE_PH_COMPATIBILITY
  ? FEAT_ADDITION_RATIO — no auto_resolve, must be determined by testing

UNRESOLVED INPUT:
  ⚠ "5000 m³/h" — no graph parameter maps to production line capacity.
    This value cannot be used for dosage calculation.
    Dosage is based on wt% of dry final product, not airflow.

STRATEGY: STRAT_MANDATORY_COMPATIBILITY_TEST (always)
```

**LLM Response:**

> For water repellency treatment of **glass mineral wool**, I recommend **SILRES BS 5133** — it's a reactive PDMS emulsion specifically designed for this application.
>
> Regarding your 5000 m³/h line capacity — the **dosage is not determined by air volume** but by **weight percentage of the dry final product**. The addition ratio must be determined through individual testing at your plant.
>
> To provide a specific recommendation, I need:
> 1. **What binder system do you use?** (BS 5133 is optimized for carbohydrate-based binders)
> 2. **What is the pH of your binder mixture?** (must be between 5 and 8)
> 3. **What level of water repellency is required?** (determines addition ratio)

### Intent Routing Summary

| User Question | Intent | Traversal Depth |
|---|---|---|
| "What is the dosage for stone wool?" | `property_query` | Short — lookup + context |
| "Can I use this with phenolic resin?" | `compatibility_check` | Medium — constraint + gate + risk |
| "What happens at pH 4?" | `constraint_check` | Medium — constraint + neutralization + block |
| "We need water repellency for glass wool" | `product_recommendation` | Full — stressors → traits → candidates → verdict |

---

## 5. Inference Detection & Expert Verification

### The Problem

LLM receives graph facts and generates a response. Sometimes it adds inferences not present in the graph:

- **Graph fact:** `max_addition_ratio: 0.3` on stone wool edge + `source_quote: "due to hydrophilicity"`
- **LLM inference:** "Stone wool needs more silicone than glass wool"

The inference is reasonable but NOT in the graph. It should be:
1. Detected as an inference
2. Shown to the user with different visual treatment
3. Available for expert approval/rejection
4. Once approved, written back to graph as a verified fact

### Key Principle

**Graph = facts + source. LLM = reasoning.** Inferences must not be silently presented as facts.

Every node/edge gets provenance metadata:
```
provenance:    PDF_TDS | LLM_INFERENCE | EXPERT_VERIFIED
confidence:    VERBATIM | INFERRED | SPECULATIVE
review_status: PENDING_REVIEW | APPROVED | REJECTED | SUPERSEDED
source_ref:    document reference
source_quote:  exact quote from source
created_by:    claude | expert_name
verified_by:   null | expert_name
```

### Pipeline: Inference Extractor

New step after LLM response generation — a second LLM call that compares the response against the reasoning report:

```
User Query
    ↓
Scribe (intent extraction)
    ↓
Engine Traversal → REASONING_REPORT (all GRAPH_FACT)
    ↓
LLM Response Generation (receives report + query)
    ↓
Inference Extractor (NEW — compares response vs report)
    ↓
Structured Response:
{
  "answer": "...",
  "claims": [
    {"text": "dosage up to 0.3 wt%", "type": "GRAPH_FACT", "source": "TDS p.1"},
    {"text": "stone wool needs more silicone than glass wool", "type": "LLM_INFERENCE",
     "basis": ["max_addition_ratio: 0.3", "'even for stone mineral wool'"],
     "review_id": "INF_20260306_001", "actions": ["approve", "reject", "edit"]}
  ]
}
```

The Inference Extractor prompt instructs an LLM to classify each claim in the response as either `GRAPH_FACT` (directly stated in reasoning report) or `LLM_INFERENCE` (not in report, derived by combining facts or adding external knowledge). For inferences, it also suggests a graph write (new edge/node) to persist the knowledge.

### Expert Approval Flow

1. Expert sees response with claims color-coded (fact vs inference)
2. Clicks "approve" on an inference
3. System writes to graph:
   ```cypher
   MATCH (a {id: 'SUB_STONE_MINERAL_WOOL'}), (b {id: 'SUB_GLASS_MINERAL_WOOL'})
   CREATE (a)-[:REQUIRES_MORE_THAN {
     property: 'addition_ratio',
     reason: 'higher binder hydrophilicity',
     provenance: 'LLM_INFERENCE',
     review_status: 'APPROVED',
     verified_by: 'thorsten',
     verified_at: datetime()
   }]->(b)
   ```
4. Next traversal picks this up as a GRAPH_FACT — LLM no longer needs to infer it

### Trust Levels for Traversal

```cypher
-- PRODUCTION: only verified facts
WHERE r.review_status = 'APPROVED'

-- ADVISORY: verified + pending (with labels)
WHERE r.review_status IN ['APPROVED', 'PENDING_REVIEW']

-- DISCOVERY: everything
-- (no filter)
```

### Cost

- +1 LLM call per response (gemini-flash, ~500ms, ~200 tokens output)
- +1 graph write per detected inference (PendingInference node)
- +1 graph mutation per expert approval

### Result: Self-Learning Graph

```
PDF → Graph (VERBATIM)
       ↓
  Engine traversal → LLM response
       ↓
  Inference detected → Graph (PENDING_REVIEW)
       ↓
  Expert approves → Graph (APPROVED)
       ↓
  Next traversal → fact available without inference
```

The graph densifies with each interaction. Domain knowledge accumulates from both documents (bottom-up) and expert verification of LLM inferences (top-down).
