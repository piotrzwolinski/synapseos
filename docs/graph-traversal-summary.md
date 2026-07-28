# SynapseOS Knowledge Graph — Architecture & Traversal Summary

## The 4-Layer Knowledge Graph

| Layer | Name | Node Types | Purpose |
|-------|------|-----------|---------|
| 1 | **Inventory** | `Item`, `Trait` | Hard facts about what we sell |
| 2 | **Domain/Physics** | `Stressor`, `CausalRule`, `Substance`, `Risk` | How the world works (cause → effect) |
| 3 | **Playbook/Strategy** | `LogicGate`, `Parameter` | Decision trees and inquiry priority |
| 4 | **State** | `Session`, `TagUnit` | Digital Twin of the current project |

---

## Layer 3 Deep Dive — Playbook / Strategy

Layer 3 is the **decision-making intelligence** of the graph. It encodes *"if this context, ask these questions"* logic entirely as graph data — no Python code changes needed when new rules are added.

### LogicGates

Conditional checkpoints that activate only when a specific context is detected.

| Gate | Monitors (L2 Stressor) | Requires Data | Triggered By |
|------|----------------------|---------------|-------------|
| `GATE_DEW_POINT` | Outdoor Condensation | Min Temp, Humidity | `ENV_OUTDOOR` |
| `GATE_GREASE_LOAD` | Grease/Oil Exposure | Grease Presence | `APP_KITCHEN` |
| `GATE_CHLORINE_EXPOSURE` | Chlorine Exposure | Chlorine Concentration | `APP_POOL` |
| `GATE_ATEX_ZONE` | Explosive Atmosphere | ATEX Zone Class | `APP_POWDER_COATING`, `APP_FLOUR_MILL`, `APP_METALWORKING`, `ENV_ATEX` |

### Parameters

Variables the system must collect from the user. Two categories:

**Core** (required by all product families):
- `PARAM_AIRFLOW` (Numeric) — airflow rate
- `PARAM_DIMS` (Dimensions) — duct dimensions

**Gate-triggered** (only asked when a gate fires):
- `PARAM_GREASE_PRESENCE` — kitchen context
- `PARAM_MIN_TEMP`, `PARAM_REL_HUMIDITY` — outdoor context
- `PARAM_CHLORINE_LEVEL` — pool context
- `PARAM_ATEX_ZONE` — explosive atmosphere context

### Relationship Pattern

```
Layer 1/2 context          Layer 3 strategy              User interaction
─────────────────       ──────────────────────          ─────────────────
Application/Environment
  ──TRIGGERS_GATE──▶  LogicGate
                         ──REQUIRES_DATA──▶  Parameter  ──▶ Clarification Q
                         ──MONITORS──▶  Stressor (L2)

ProductFamily
  ──REQUIRES_PARAMETER──▶  Parameter                    ──▶ Clarification Q
```

---

## End-to-End Graph Traversal Example (HVAC)

**Scenario:** User says *"I need filtration for a commercial kitchen"*

### Step 0 — Scribe (LLM Intent Extraction)

Gemini Flash parses the vague input:
```json
{ "detected_application": "APP_KITCHEN" }
```
No airflow, no dimensions — just an application. The graph takes it from here.

### Step 1 — Layer 1 (Inventory): What does a Kitchen generate?

```
(:Application APP_KITCHEN)
    ──GENERATES──▶ (:Substance SUB_GREASE)      "Grease/Oil"
    ──GENERATES──▶ (:Substance SUB_WATER)        "Condensation/Water"
```

### Step 2 — Layer 2 (Physics): Cause → Effect

```
APP_KITCHEN ──EXPOSES_TO──▶ STRESSOR_GREASE_EXPOSURE
            ──EXPOSES_TO──▶ STRESSOR_CHEMICAL_VAPORS

SUB_GREASE  ──CAUSES──▶ RISK_CLOG ("Rapid Clogging")
```

Stressors demand physical traits:

| Stressor | Demanded Trait |
|----------|---------------|
| Grease/Oil Exposure | `TRAIT_MECHANICAL_FILTRATION` |
| Chemical Vapor Exposure | `TRAIT_POROUS_ADSORPTION` |

### Step 3 — Layer 3 (Playbook): What to ask + strategy

**Gate fires:**
```
APP_KITCHEN ──TRIGGERS_GATE──▶ GATE_GREASE_LOAD
    ──REQUIRES_DATA──▶ PARAM_GREASE_PRESENCE
    ──MONITORS──▶      STRESSOR_GREASE_EXPOSURE
```

**Risk strategy:**
```
RISK_CLOG ──TRIGGERS_STRATEGY──▶ STRAT_BLOCK      (Hard Block)
          ──MITIGATED_BY──▶      SOL_PREFILTER     (Pre-filtration F7/F9)
          ──MITIGATED_BY──▶      SOL_GREASE_SEP    (Grease Separator)
```

The clogging risk triggers a hard block — no bare filter into greasy duct. Must be mitigated by a pre-filter or grease separator → drives the **assembly protocol**.

### Step 4 — Trait Matching: Product candidates

| Demanded Trait | Qualifying Products |
|---|---|
| `TRAIT_MECHANICAL_FILTRATION` | GDP, GDB, GDMI, PFF |
| `TRAIT_POROUS_ADSORPTION` | GDC, GDC_FLEX, GDMI_FLEX |

Kitchen needs **both** → assembly:
- **Stage 1** = grease protection (GDP/GDB)
- **Stage 2** = main filtration (GDC)

### Step 5 — Clarification Cascade

Missing parameters to resolve:
1. `PARAM_GREASE_PRESENCE` — *"Confirm grease in airstream?"*
2. `PARAM_AIRFLOW` — *"What is the airflow rate?"*
3. `PARAM_DIMS` — *"What are the duct dimensions?"*

### Step 6 — Layer 4 (State): Persist Digital Twin

```
(:Session) ──HAS_UNIT──▶ (:TagUnit {tag: "item_1_stage_1", family: "GDP", role: "protector"})
(:Session) ──HAS_UNIT──▶ (:TagUnit {tag: "item_1_stage_2", family: "GDC", role: "main"})
```

Parameters synced across stages via `assembly_group_id`.

### Visual Summary

```
USER: "filtration for a kitchen"
  │
  ▼
SCRIBE (LLM) ──────────────────────────── extracts APP_KITCHEN
  │
  ▼ Layer 1 — INVENTORY
APP_KITCHEN ──GENERATES──▶ SUB_GREASE, SUB_WATER
            ──EXPOSES_TO──▶ STRESSOR_GREASE, STRESSOR_CHEM_VAPOR
  │
  ▼ Layer 2 — PHYSICS
STRESSOR_GREASE  ──DEMANDS_TRAIT──▶ TRAIT_MECHANICAL_FILTRATION
STRESSOR_CHEM    ──DEMANDS_TRAIT──▶ TRAIT_POROUS_ADSORPTION
SUB_GREASE       ──CAUSES──▶ RISK_CLOG ──TRIGGERS_STRATEGY──▶ HARD_BLOCK
                                       ──MITIGATED_BY──▶ SOL_PREFILTER
  │
  ▼ Layer 3 — PLAYBOOK
APP_KITCHEN ──TRIGGERS_GATE──▶ GATE_GREASE_LOAD ──REQUIRES_DATA──▶ PARAM_GREASE_PRESENCE
Product families ──REQUIRES_PARAMETER──▶ PARAM_AIRFLOW, PARAM_DIMS
  │
  ▼ TRAIT MATCHING
MECHANICAL_FILTRATION → GDP, GDB, GDMI, PFF     (protector candidates)
POROUS_ADSORPTION     → GDC, GDC_FLEX, GDMI_FLEX (main candidates)
  │
  ▼ Layer 4 — STATE (Digital Twin)
SESSION ──▶ TagUnit item_1_stage_1 (GDP, protector)
        ──▶ TagUnit item_1_stage_2 (GDC, main)
        ──▶ resolved: airflow=3000, dims=600x400, grease=confirmed
```

### Key Insight

**The Python engine never knew the word "kitchen."** It followed graph edges: substances demand traits, traits filter products, risks trigger strategies, gates demand parameters. All domain intelligence lives in the graph.

---
---

# PREFAB HOUSE CONFIGURATOR — Applying SynapseOS to a New Domain

Everything below documents the analysis and design for applying the SynapseOS graph reasoning platform to a **prefab house configurator** chatbot. The engine code stays unchanged — only graph data and tenant config change.

---

## 1. Domain Mapping — HVAC → Prefab Houses

The engine is domain-agnostic. Same node labels, different content:

| HVAC Concept | Prefab House Concept | Example |
|---|---|---|
| `ProductFamily` (GDB, GDC) | House model | Nordic 70, Classic 150, Villa 180 |
| `PhysicalTrait` (HEPA, corrosion) | Architectural feature | Guest room, open plan, garage |
| `EnvironmentalStressor` (grease, chlorine) | Lifestyle need | Frequent guests, remote work, pets |
| `Application` (kitchen, pool) | Family profile | 2+1, multigenerational, retirees |
| `Environment` (indoor, outdoor) | Site condition | Urban, suburban, rural |
| `DEMANDS_TRAIT` (chlorine → C5 steel) | Need → feature | Frequent guests → guest room |
| `NEUTRALIZED_BY` (grease → carbon) | Constraint blocks feature | Small plot → no double garage |
| `LogicGate` (dew point, ATEX) | Feasibility gate | Budget check, plot fit |
| `Parameter` (airflow, dimensions) | User parameter | Budget, plot size, style |
| `ClarificationRule` (paint shop → solvents?) | Contextual question | Guests detected → how often? |
| `VariableFeature` (connection type) | Configurable option | Facade material, heating system |
| Assembly (protector + main filter) | N/A for houses | Not applicable |

**Zero Python changes.** New tenant, new graph, same engine.

---

## 2. Layer 1 — Inventory: What We Sell

### ProductFamily Nodes (House Models)

```cypher
(:ProductFamily {
  id: "FAM_NORDIC_70",
  name: "Nordic 70",
  type: "Parterowy kompaktowy",
  desc: "Dom parterowy 70m², 2 sypialnie, idealny dla par",
  base_price: 289000,
  total_area_m2: 70,
  floors: 1,
  bedrooms: 2,
  bathrooms: 1,
  min_plot_width_m: 14,
  min_plot_area_m2: 400,
  selection_priority: 50
})

(:ProductFamily {
  id: "FAM_CLASSIC_150",
  name: "Classic 150",
  type: "Piętrowy rodzinny",
  desc: "Dom piętrowy 150m², 4 sypialnie, garaż, pokój gościnny",
  base_price: 529000,
  total_area_m2: 150,
  floors: 2,
  bedrooms: 4,
  bathrooms: 2,
  min_plot_width_m: 16,
  min_plot_area_m2: 600,
  selection_priority: 20
})

(:ProductFamily {
  id: "FAM_VILLA_180",
  name: "Villa 180",
  type: "Rezydencja",
  desc: "Dom 180m², 5 sypialni, garaż podwójny, master suite",
  base_price: 699000,
  total_area_m2: 180,
  ...
})

(:ProductFamily {
  id: "FAM_MODULAR_90",
  name: "Modular 90",
  type: "Rozbudowywalny",
  desc: "Dom modułowy 90m², możliwość rozbudowy o kolejne moduły",
  base_price: 349000,
  ...
})
```

### PhysicalTrait Nodes (Architectural Features)

Categories: **spatial**, **comfort**, **energy**, **accessibility**, **modularity**

```
── spatial ──────────────────────────────────
TRAIT_3_BEDROOMS        "3+ sypialnie"
TRAIT_4_BEDROOMS        "4+ sypialnie"
TRAIT_2_BATHROOMS       "2+ łazienki"
TRAIT_OPEN_PLAN         "Otwarty plan (salon+kuchnia+jadalnia)"
TRAIT_LARGE_KITCHEN     "Duża kuchnia (>15m²)"
TRAIT_GUEST_ROOM        "Pokój gościnny"
TRAIT_HOME_OFFICE       "Gabinet / home office"
TRAIT_PLAYROOM          "Pokój zabaw"
TRAIT_MASTER_SUITE      "Master suite (sypialnia + łazienka)"
TRAIT_GALLERY           "Galeria (otwarta strefa na piętrze)"
TRAIT_SEPARATE_KITCHEN  "Osobna kuchnia (nie open plan)"

── comfort ──────────────────────────────────
TRAIT_GARAGE_SINGLE     "Garaż pojedynczy"
TRAIT_GARAGE_DOUBLE     "Garaż podwójny"
TRAIT_PANTRY            "Spiżarnia"
TRAIT_MUDROOM           "Wiatrołap / garderoba wejściowa"
TRAIT_WALK_IN_CLOSET    "Garderoba"
TRAIT_UTILITY_ROOM      "Pomieszczenie gospodarcze"
TRAIT_GARDEN_ACCESS     "Bezpośredni dostęp do ogrodu (taras)"

── energy ───────────────────────────────────
TRAIT_ENERGY_A_PLUS     "Klasa energetyczna A+"
TRAIT_HEAT_PUMP_READY   "Przystosowany pod pompę ciepła"
TRAIT_PV_READY          "Przystosowany pod fotowoltaikę"

── accessibility ────────────────────────────
TRAIT_SINGLE_FLOOR      "Parterowy (bez schodów)"
TRAIT_ACCESSIBILITY     "Dostępny (szerokie drzwi, brak progów)"

── modularity ───────────────────────────────
TRAIT_EXPANDABLE        "Rozbudowywalny (dodatkowe moduły)"
```

### HAS_TRAIT Relationships

```cypher
(FAM_CLASSIC_150)-[:HAS_TRAIT {primary: true}]->(TRAIT_4_BEDROOMS)
(FAM_CLASSIC_150)-[:HAS_TRAIT {primary: true}]->(TRAIT_GUEST_ROOM)
(FAM_CLASSIC_150)-[:HAS_TRAIT {primary: true}]->(TRAIT_GARAGE_SINGLE)
(FAM_CLASSIC_150)-[:HAS_TRAIT]->(TRAIT_2_BATHROOMS)
(FAM_CLASSIC_150)-[:HAS_TRAIT]->(TRAIT_OPEN_PLAN)
(FAM_CLASSIC_150)-[:HAS_TRAIT]->(TRAIT_GARDEN_ACCESS)
(FAM_CLASSIC_150)-[:HAS_TRAIT]->(TRAIT_UTILITY_ROOM)
```

### Room Nodes (Optional — for drill-down answers)

Extracted from floor plans per model:

```cypher
(:Room {id: "ROOM_X_WOHNEN", name: "Wohnen/Essen", area_m2: 33.48,
        floor: "EG", type: "living", is_open_plan: true})
(:Room {id: "ROOM_X_GAST", name: "Gast", area_m2: 14.06,
        floor: "EG", type: "guest_bedroom"})
(FAM_X)-[:CONTAINS_ROOM]->(ROOM_X_WOHNEN)
```

Enables: *"Jak duży jest salon?"* → `MATCH (f)-[:CONTAINS_ROOM]->(r {type: "living"}) RETURN r.area_m2`

---

## 3. Layer 2 — Lifestyle Physics: How the World Works

### EnvironmentalStressor Nodes (Lifestyle Needs)

In HVAC: "grease destroys activated carbon." Here: "frequent guests demand a guest room." **Same mechanics** — external factor forces a product trait.

```cypher
(:EnvironmentalStressor {
  id: "STRESSOR_FREQUENT_GUESTS",
  name: "Częste wizyty gości",
  category: "lifestyle",
  keywords: ["goście", "gości", "odwiedziny", "rodzina przyjeżdża",
             "imprezy", "guests", "często gościmy"]
})

(:EnvironmentalStressor {
  id: "STRESSOR_GROWING_FAMILY",
  name: "Rosnąca rodzina",
  category: "lifecycle",
  keywords: ["2+1", "2+2", "dziecko", "dzieci", "ciąża",
             "planujemy dziecko", "małe dziecko"]
})

(:EnvironmentalStressor {
  id: "STRESSOR_REMOTE_WORK",
  name: "Praca zdalna",
  category: "lifestyle",
  keywords: ["home office", "praca zdalna", "praca z domu",
             "freelancer", "programista", "zdalnie"]
})

(:EnvironmentalStressor {
  id: "STRESSOR_ELDERLY_PARENT",
  name: "Osoba starsza w domu",
  category: "lifecycle",
  keywords: ["teściowa", "rodzic", "babcia", "dziadek",
             "opieka", "starszy", "emeryt"]
})

(:EnvironmentalStressor {
  id: "STRESSOR_PETS_LARGE",
  name: "Duże zwierzęta domowe",
  category: "lifestyle",
  keywords: ["pies", "duży pies", "dwa psy", "labrador", "owczarek"]
})

(:EnvironmentalStressor {
  id: "STRESSOR_SMALL_PLOT",
  name: "Ograniczona działka",
  category: "site",
  keywords: ["mała działka", "wąska", "15m", "zabudowa szeregowa",
             "miasto", "osiedle"]
})

(:EnvironmentalStressor {
  id: "STRESSOR_TIGHT_BUDGET",
  name: "Ograniczony budżet",
  category: "financial",
  keywords: ["tanio", "budżet", "oszczędnie", "ekonomicznie",
             "najtaniej", "do 400 tysięcy"]
})

(:EnvironmentalStressor {
  id: "STRESSOR_COOKING_ENTHUSIAST",
  name: "Pasja gotowania",
  category: "lifestyle",
  keywords: ["gotowanie", "kuchnia", "chef", "dużo gotujemy"]
})

(:EnvironmentalStressor {
  id: "STRESSOR_ENERGY_CONSCIOUS",
  name: "Świadomość energetyczna",
  category: "values",
  keywords: ["ekologia", "fotowoltaika", "pompa ciepła",
             "pasywny", "zero-energy", "eko"]
})
```

### DEMANDS_TRAIT — Stressor Forces a Feature

```cypher
(STRESSOR_FREQUENT_GUESTS)-[:DEMANDS_TRAIT {
  severity: "CRITICAL",
  explanation: "Częste wizyty wymagają dedykowanego pokoju gościnnego —
               sofa w salonie to nie rozwiązanie przy regularnych gościach"
}]->(TRAIT_GUEST_ROOM)

(STRESSOR_FREQUENT_GUESTS)-[:DEMANDS_TRAIT {
  severity: "WARNING",
  explanation: "Otwarty plan ułatwia wspólne gotowanie i spędzanie czasu z gośćmi"
}]->(TRAIT_OPEN_PLAN)

(STRESSOR_FREQUENT_GUESTS)-[:DEMANDS_TRAIT {
  severity: "WARNING",
  explanation: "Druga łazienka eliminuje kolejki rano przy gościach"
}]->(TRAIT_2_BATHROOMS)

(STRESSOR_GROWING_FAMILY)-[:DEMANDS_TRAIT {
  severity: "CRITICAL",
  explanation: "Rodzina 2+1 potrzebuje minimum 3 sypialni —
               własny pokój dziecka jest kluczowy dla rozwoju"
}]->(TRAIT_3_BEDROOMS)

(STRESSOR_REMOTE_WORK)-[:DEMANDS_TRAIT {
  severity: "CRITICAL",
  explanation: "Praca zdalna wymaga izolowanego akustycznie gabinetu —
               praca przy kuchennym stole obniża produktywność o 40%"
}]->(TRAIT_HOME_OFFICE)

(STRESSOR_ELDERLY_PARENT)-[:DEMANDS_TRAIT {
  severity: "CRITICAL",
  explanation: "Osoba starsza musi mieć wszystko na jednym poziomie —
               schody to ryzyko upadku i bariera mobilności"
}]->(TRAIT_SINGLE_FLOOR)

(STRESSOR_PETS_LARGE)-[:DEMANDS_TRAIT {
  severity: "CRITICAL",
  explanation: "Duże psy potrzebują bezpośredniego wyjścia do ogrodu"
}]->(TRAIT_GARDEN_ACCESS)

(STRESSOR_COOKING_ENTHUSIAST)-[:DEMANDS_TRAIT {
  severity: "CRITICAL",
  explanation: "Pasja gotowania wymaga kuchni >15m² z miejscem na wyspę"
}]->(TRAIT_LARGE_KITCHEN)

(STRESSOR_ENERGY_CONSCIOUS)-[:DEMANDS_TRAIT {
  severity: "CRITICAL",
  explanation: "Świadomość energetyczna wymaga klasy A+ z izolacją ≥20cm"
}]->(TRAIT_ENERGY_A_PLUS)
```

### NEUTRALIZED_BY — Constraint Blocks a Feature

```cypher
(TRAIT_GARAGE_DOUBLE)-[:NEUTRALIZED_BY {
  severity: "CRITICAL",
  explanation: "Garaż podwójny wymaga frontu >18m — na wąskiej działce
               fizycznie się nie zmieści"
}]->(STRESSOR_SMALL_PLOT)

(TRAIT_EXPANDABLE)-[:NEUTRALIZED_BY {
  severity: "WARNING",
  explanation: "Na małej działce brak miejsca na rozbudowę modułową"
}]->(STRESSOR_SMALL_PLOT)

(TRAIT_4_BEDROOMS)-[:NEUTRALIZED_BY {
  severity: "WARNING",
  explanation: "4+ sypialnie = dom >120m², znacząco podnosi koszt"
}]->(STRESSOR_TIGHT_BUDGET)
```

### Application Nodes (Family Profiles)

```cypher
(:Application {id: "APP_FAMILY_SMALL", name: "Rodzina 2+1",
  keywords: ["2+1", "rodzina", "jedno dziecko", "małe dziecko"]})

(:Application {id: "APP_FAMILY_LARGE", name: "Duża rodzina",
  keywords: ["2+2", "2+3", "troje dzieci", "duża rodzina"]})

(:Application {id: "APP_MULTIGENERATIONAL", name: "Dom wielopokoleniowy",
  keywords: ["wielopokoleniowy", "z rodzicami", "teściowie", "babcia mieszka"]})

// Context triggers gates:
(APP_MULTIGENERATIONAL)-[:TRIGGERS_GATE]->(GATE_ELDERLY_FLOOR)
```

---

## 4. Layer 3 — Playbook: What to Ask and When

### Parameter + Question Nodes

```cypher
(:Parameter {id: "PARAM_BUDGET", property_key: "budget",
  unit: "PLN", priority: 1
})-[:ASKED_VIA]->(:Question {id: "Q_BUDGET",
  text: "Jaki jest orientacyjny budżet na sam dom (bez działki)?",
  priority: 1, intent: "sizing"})

(:Parameter {id: "PARAM_PLOT_WIDTH", property_key: "plot_width",
  unit: "m", priority: 2
})-[:ASKED_VIA]->(:Question {id: "Q_PLOT_WIDTH",
  text: "Jaka jest szerokość działki (w metrach)?",
  priority: 2, intent: "constraint"})

(:Parameter {id: "PARAM_FLOORS_PREF", property_key: "floors_preference",
  priority: 3
})-[:ASKED_VIA]->(:Question {id: "Q_FLOORS",
  text: "Wolisz dom parterowy czy piętrowy?",
  priority: 3, intent: "preference"})

(:Parameter {id: "PARAM_STYLE", property_key: "style_preference",
  priority: 5
})-[:ASKED_VIA]->(:Question {id: "Q_STYLE",
  text: "Jaki styl preferujesz? (nowoczesny / klasyczny / skandynawski)",
  priority: 5, intent: "preference"})
```

### LogicGate Nodes (Feasibility Gates)

```cypher
(:LogicGate {
  id: "GATE_BUDGET_CHECK",
  name: "Budget Feasibility Gate",
  condition_logic: "IF budget < model.base_price THEN VETO ELSE PASS",
  physics_explanation: "Cena bazowa modelu przekracza dostępny budżet."
})-[:MONITORS]->(STRESSOR_TIGHT_BUDGET)
 -[:REQUIRES_DATA]->(PARAM_BUDGET)

(:LogicGate {
  id: "GATE_PLOT_FIT",
  name: "Plot Width Gate",
  condition_logic: "IF plot_width < model.min_plot_width_m + 6 THEN VETO",
  physics_explanation: "Dom nie zmieści się na działce z wymaganymi
    odstępami od granic (min. 3m z każdej strony)."
})-[:MONITORS]->(STRESSOR_SMALL_PLOT)
 -[:REQUIRES_DATA]->(PARAM_PLOT_WIDTH)

(:LogicGate {
  id: "GATE_ELDERLY_FLOOR",
  name: "Elderly Single-Floor Gate",
  condition_logic: "IF has_elderly AND model.floors > 1 THEN VETO",
  physics_explanation: "Dom piętrowy jest nieodpowiedni dla osoby starszej —
    schody stanowią ryzyko upadku."
})-[:MONITORS]->(STRESSOR_ELDERLY_PARENT)
```

### ClarificationRule Nodes (Context-Triggered Questions)

```cypher
(:ClarificationRule {id: "RULE_GUESTS_FREQUENCY"})
  -[:TRIGGERED_BY_CONTEXT]->(:Application {id: "APP_FAMILY_SMALL"})
  -[:DEMANDS_PARAMETER]->(:Parameter {id: "PARAM_GUEST_FREQ",
    property_key: "guest_frequency",
    question: "Jak często gościcie na noclegi — co tydzień, co miesiąc,
              czy kilka razy w roku?"})

(:ClarificationRule {id: "RULE_REMOTE_WORK_DETAILS"})
  -[:TRIGGERED_BY_CONTEXT]->(STRESSOR_REMOTE_WORK detected)
  -[:DEMANDS_PARAMETER]->(:Parameter {id: "PARAM_WORK_STYLE",
    property_key: "remote_workers_count",
    question: "Jedna osoba pracuje z domu, czy dwie? Pełen etat czy hybrydowo?"})

(:ClarificationRule {id: "RULE_ELDERLY_INDEPENDENCE"})
  -[:TRIGGERED_BY_CONTEXT]->(APP_MULTIGENERATIONAL)
  -[:DEMANDS_PARAMETER]->(:Parameter {id: "PARAM_ELDERLY_ZONE",
    property_key: "elderly_independent_zone",
    question: "Czy osoba starsza potrzebuje niezależnej strefy
              (osobna łazienka, aneks)?"})
```

### VariableFeature Nodes (Per-Model Config Options)

```cypher
(FAM_CLASSIC_150)-[:HAS_VARIABLE_FEATURE]->(:VariableFeature {
  id: "VARFEAT_FACADE", parameter_name: "facade_material",
  is_variable: true,
  question: "Jaki materiał elewacji? (tynk / drewno / klinkier)"
})-[:HAS_OPTION]->(:FeatureOption {value: "plaster", name: "Tynk", is_default: true})
 -[:HAS_OPTION]->(:FeatureOption {value: "wood", name: "Drewno"})
 -[:HAS_OPTION]->(:FeatureOption {value: "clinker", name: "Klinkier"})

(FAM_CLASSIC_150)-[:HAS_VARIABLE_FEATURE]->(:VariableFeature {
  id: "VARFEAT_HEATING", parameter_name: "heating_system",
  auto_resolve: true, default_value: "heat_pump",
  question: "Jaki system ogrzewania? (pompa ciepła / gaz / pellet)"
})
```

---

## 5. End-to-End Walkthrough: "Szukam domu dla rodziny 2+1, mamy często gości"

### Turn 1 — Scribe + Engine

**Scribe** extracts:
```json
{ "family_size": 3, "detected_application": "APP_FAMILY_SMALL",
  "context_hints": ["frequent_guests"] }
```

**Layer 2 fires:**
```
STRESSOR_GROWING_FAMILY  →  DEMANDS_TRAIT → TRAIT_3_BEDROOMS   (CRITICAL)
STRESSOR_GROWING_FAMILY  →  DEMANDS_TRAIT → TRAIT_PLAYROOM     (WARNING)
STRESSOR_FREQUENT_GUESTS →  DEMANDS_TRAIT → TRAIT_GUEST_ROOM   (CRITICAL)
STRESSOR_FREQUENT_GUESTS →  DEMANDS_TRAIT → TRAIT_OPEN_PLAN    (WARNING)
STRESSOR_FREQUENT_GUESTS →  DEMANDS_TRAIT → TRAIT_2_BATHROOMS  (WARNING)
```

**Layer 1 trait matching:**

| Model | 3_BED | GUEST | OPEN | 2_BATH | PLAY | Coverage | Veto? |
|---|---|---|---|---|---|---|---|
| Villa 180 | ✓ | ✓ | ✓ | ✓ | ✓ | **1.0** | — |
| Classic 150 | ✓ | ✓ | ✓ | ✓ | ✗ | **0.8** | — |
| Nordic 130 | ✓ | ✗ | ✓ | ✓ | ✗ | 0.6 | **VETO** (CRITICAL guest room) |
| Nordic 70 | ✗ | ✗ | ✗ | ✗ | ✗ | 0.0 | **VETO** (CRITICAL 3 bedrooms) |

**Recommendation:** Classic 150 (best coverage × selection_priority).

**Layer 3 clarifications** (by priority):
1. (prio 0) Gate VALIDATION_REQUIRED — budget/plot unknown
2. (prio 1) PARAM_BUDGET: "Jaki jest orientacyjny budżet?"
3. (prio 2) PARAM_PLOT_AREA: "Jaka jest powierzchnia działki?"
4. (prio 5) ClarificationRule: "Jak często gościcie?"

**LLM output:**
> Dla rodziny 2+1 z częstymi gośćmi najlepiej sprawdzi się Classic 150 — dom piętrowy z 4 sypialniami, dedykowanym pokojem gościnnym i otwartym planem. Macie już upatrzoną działkę?

### Turn 2 — "budżet 500k, działka 800m², 20m szeroka"

Gates evaluate → budget tight (529k > 500k), plot OK (20m ≥ 16m + 6m). System adjusts.

### Turn 3+ — Refinement, final top 3

System presents ranked options with per-model explanations.

---

## 6. Natural Conversation: Not an Interrogation

### Problem

Naive Layer 3 dumps all clarification questions at once → feels like a police interrogation.

### Three Levers to Fix This (No Engine Changes)

#### Lever 1 — Prompt: "One question per turn, woven into narrative"

System prompt instructs the LLM:
> "Never list more than 1 question at a time. Share your reasoning first, then ask naturally."

Result: *"Classic 150 ma dedykowany pokój gościnny — to się sprawdzi przy częstych gościach. Cena bazowa to ok. 530 tys. — mieści się to w Waszym budżecie?"*

#### Lever 2 — Graph: Priority tiers + auto_resolve + inferred_from

**Priority as "conversation turn":**
- Priority 1 = ask in turn 1 (budget)
- Priority 2 = ask in turn 2 (plot — only after budget)
- Priority 5 = ask in turn 3+ (style, details)

**Auto-resolve:** `VariableFeature.auto_resolve=true` with `default_value` — user never sees the question unless they bring it up.

**Inferred_from (new property):** `PARAM_BEDROOMS_MIN.inferred_from = "family_size"`, `inference_rule = "family_size + 1"` → zero questions about bedroom count.

#### Lever 3 — Retriever: Drip Mode (top-1 priority tier per turn)

```python
# Instead of dumping ALL clarifications into the prompt:
if clarifications:
    top_priority = clarifications[0]["priority"]
    this_turn = [c for c in clarifications if c["priority"] == top_priority]
    # rest waits for the next turn
```

~10 lines changed in retriever. Engine still returns the full list; LLM sees only one batch per turn.

---

## 7. Layer 4 — Structured Memory (vs. Full Chat History)

### The Problem with Classic LLM Chatbots

A standard chatbot passes the entire conversation history to the LLM on every turn:

```
Turn 12 input: [12× question + 12× answer + RAG chunks] = ~50k tokens
```

Expensive, slow, and fragile (context window pressure → "amnesia").

### SynapseOS Layer 4 Solution

The graph IS the memory. Python's `TechnicalState` is a stateless working copy rebuilt from FalkorDB on every turn.

**Layer 4 node structure:**
```
(:Session {id, last_active})
  └──[:WORKING_ON]──► (:ActiveProject {
        name, detected_family, locked_material,
        resolved_params (JSON dict),
        pending_clarification,
        vetoed_families, accessories
     })
        ├──[:HAS_UNIT]──► (:TagUnit {tag_id, product_family, all specs...})
        ├──[:HAS_TURN]──► (:ConversationTurn {role, message, turn_number})
        └──[:TARGETS_FAMILY]──► (:ProductFamily)   // cross-link to Layer 1
```

**Turn lifecycle:**
```
START:  load_from_graph()     → TechnicalState rebuilt from FalkorDB
        store_turn("user")    → ConversationTurn node
        get_recent_turns(n=3) → Scribe window (last 3 turns only)
        Scribe LLM            → extract intent
        Engine pipeline        → graph reasoning (zero LLM)
        Synthesis LLM          → natural language output

END:    persist_to_graph()    → all state written back
        store_turn("assistant") → compact summary (not full response)
```

### What the LLM Sees: Turn 12 Comparison

**Classic chatbot:**
```
messages: [24 items = 12 user + 12 assistant messages]
// ~50k tokens, growing linearly
```

**SynapseOS:**
```
system_prompt:  persona + EngineVerdict           ~4k tokens
synthesis_prompt:
  query:    "A co z pompą ciepła?"                ~20 tokens
  policies: TechnicalState snapshot {             ~2k tokens
    ✓ KNOWN: budget = 500k — DO NOT ask
    ✓ KNOWN: plot = 800m², 20m — DO NOT ask
    ✓ KNOWN: family = Classic 150
    ✓ KNOWN: roof = Satteldach
    PENDING: heating_system
  }
  context:  product specs from Layer 1            ~2k tokens
// TOTAL: ~8-10k tokens, FLAT (not growing)
```

### Growth Comparison

```
Tokens per turn:

 60k ┤                                          ╱ Classic LLM chatbot
     │                                       ╱
 40k ┤                                    ╱
     │                                 ╱
 20k ┤                              ╱
     │                           ╱
 10k ┤─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  SynapseOS (flat)
     │
   0 ┼──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬
     1  2  3  4  5  6  7  8  9  10 11 12   turn
```

### Triple Guard (Clarification Suppression)

Three independent mechanisms prevent asking about already-known parameters:

1. **Engine guard:** `check_missing_parameters()` — skips if key exists in context
2. **Retriever guard:** `get_clarifications()` — skips if `context[key] != None`
3. **LLM guard:** Prompt injection `✓ KNOWN: budget = 500k — DO NOT ask`

Even if guards 1 and 2 fail, the explicit `DO NOT ask` instruction prevents repetition.

### Small Model Feasibility

Because reasoning is in the graph and memory is in Layer 4, the synthesis LLM only needs to generate natural language from a structured brief:

| Model | Input Window | Sufficient? |
|---|---|---|
| Gemini 2.0 Flash | 1M | Overkill, fast + cheap |
| Haiku 3.5 | 200k | Easily (~10k input = 5% of window) |
| GPT-4o-mini | 128k | Easily |
| Gemini Flash 8B | 1M | Probably (test DE/PL quality) |

Only risk: multilingual output quality (DE/PL) on very small models.

---

## 8. Preference Changes: "Chcę płaski dach" → later: "rozważam dwuspadowy"

### Current Behavior

`resolved_params` is a flat dict with overwrite semantics:
- Turn 3: `roof_type = "Flachdach"` → saved
- Turn 7: `roof_type = "Satteldach"` → **overwrites**, "Flachdach" is lost

The system remembers the CURRENT preference but NOT that the user changed their mind.

### Proposed Extension: Versioned Preferences

Three implementation levels:

#### Level 1 — Versioned dict (minimal, ~30 lines)

```python
resolved_params = {
  "roof_type": {
    "value": "Satteldach",
    "previous": ["Flachdach"],
    "confidence": "considering",   # decided | considering | rejected
    "changed_at_turn": 7
  }
}
```

Prompt injection changes from:
```
✓ KNOWN: roof_type = Satteldach — DO NOT ask
```
to:
```
⚖ CONSIDERING: roof_type = Satteldach (previously: Flachdach, changed turn 7)
  → User is weighing options. You may compare both if relevant.
```

#### Level 2 — PreferenceEvent nodes (~4h)

```cypher
(:ActiveProject)-[:HAS_PREFERENCE]->(
  :PreferenceEvent {param: "roof_type", value: "Flachdach",
    turn: 3, confidence: "decided"})
(:ActiveProject)-[:HAS_PREFERENCE]->(
  :PreferenceEvent {param: "roof_type", value: "Satteldach",
    turn: 7, confidence: "considering"})
```

#### Level 3 — Scribe intent detection (~6h)

Scribe recognizes `intent_type: "preference_change"` and routes differently:
- Don't overwrite immediately — wait for confirmation
- Inject comparison prompt
- Ask what drove the change

**Recommendation:** Start with Level 1 for MVP. Gives 80% of value at 20% cost.

---

## 9. Anaphora Resolution: "rozwiń o inne rodzaje"

### How Does the System Handle Vague Follow-ups?

User says "rozwiń o inne rodzaje" (without specifying WHAT kinds) after a roof discussion.

**Scribe receives:**
```
RECENT CONVERSATION:
  [USER] a jednak rozważam dach dwuspadowy
  [ASSISTANT] Recommended: CLASSIC_150, type=answer, tags=1
  [USER] rozwiń o inne rodzaje

CURRENT PROJECT STATE:
  roof_type: Satteldach, family: CLASSIC_150, ...
```

Three signals for disambiguation:
1. **Recent turns** — last exchange was about roofs
2. **State** — `roof_type: Satteldach` is the active topic
3. **Linguistic context** — "rozwiń" = continuation, "inne rodzaje" = variants of same topic

### What Works (Within 3-Turn Window)

| Message | Resolved? | Mechanism |
|---|---|---|
| "rozwiń o inne rodzaje" (after roof talk) | ✓ | Recent turns + state |
| "a ten drugi?" (after comparing 2 houses) | ✓ | Recent turns |
| "ile kosztuje?" (after recommendation) | ✓ | `detected_family` in state |
| "1200" (after budget question) | ✓ | `pending_clarification` |

### What Doesn't Work (Beyond 3-Turn Window)

| Message | Problem |
|---|---|
| "wróćmy do tego co mówiłeś o kuchni" (turn 2, now turn 9) | Turn 2 outside Scribe window |

**But:** extracted facts persist forever in state. If Scribe extracted `STRESSOR_COOKING_ENTHUSIAST` at turn 2, it's still in state at turn 9. The gap is only for narrative references ("what you said about..."), not for factual references.

### Proposed Enhancements

1. **Topic tracking:** Save `_last_topic` / `_prev_topic` in `resolved_params` (~5 lines)
2. **Wider Scribe window:** Change `n=3` to `n=5` (~200 tokens extra, trivial)
3. **Conversation summary node:** Every 5 turns, a 2-sentence summary → Scribe gets full context from turn 1 in ~50 tokens

---

## 10. RAG vs KG: Assessment (Satteldach Example)

### The Problem with Pure RAG

User asks: *"Welche Vorteile hat ein Satteldach?"*

RAG API returns **~4000 words** of raw catalog text including Walmdach, Pultdach, Flachdach, drainage, overhangs, floor plans — **~15% signal, ~85% noise.**

### Hybrid Solution: Three Tiers

#### Tier A — Knowledge Graph (structured facts + relations)

For **reasoning and comparison**:

```cypher
(:RoofType {id: "ROOF_SATTELDACH", u_value: 0.16, snow_load_kn: 1.5,
  expandable_attic: true, kniestock_option: true})

(ROOF_SATTELDACH)-[:HAS_TRAIT]->(TRAIT_ATTIC_EXPANSION)
(ROOF_SATTELDACH)-[:HAS_TRAIT]->(TRAIT_CLASSIC_AESTHETIC)
(ROOF_SATTELDACH)-[:HAS_TRAIT]->(TRAIT_HIGH_SNOW_RESISTANCE)
```

#### Tier B — Structured Descriptions (KG nodes)

Pre-extracted advantages per entity:

```cypher
(ROOF_SATTELDACH)-[:HAS_ADVANTAGE]->(:Advantage {
  text_de: "Dachgeschoss durch Kniestock erweiterbar — zusätzlicher Wohnraum",
  category: "spatial"})

(ROOF_SATTELDACH)-[:HAS_ADVANTAGE]->(:Advantage {
  text_de: "U-Wert 0,16 W/m²K — hervorragender Wärmeschutz",
  category: "energy"})
```

Answers the question in **4 sentences, not 4000 words.**

#### Tier C — RAG (raw catalog, on-demand fallback)

Full PDF stays in RAG but only triggered for drill-down detail questions:
*"Jak dokładnie wygląda budowa warstw Satteldach?"*

### Decision Rule

| If information... | Where |
|---|---|
| Affects a **decision** (comparison, recommendation, veto) | **KG** |
| Is **descriptive/detailed** and doesn't affect choice | **RAG** as fallback |

---

## 11. Floor Plan Data Extraction

### What CAN Be Extracted from Architectural Drawings

From a single floor plan image, we extract ~70% of ProductFamily data:

**Hard facts:**
- Room names, types, and areas (m²)
- Building width (dimension lines on drawing)
- Floor count (EG/DG tabs)
- Window/door dimensions
- Open plan vs. separate rooms (wall lines)

**Derived traits:**
- `TRAIT_GUEST_ROOM` ← "Gast 14.06 m²" room detected
- `TRAIT_OPEN_PLAN` ← "Wohnen/Essen 33.48 m²" single space
- `TRAIT_3_BEDROOMS` ← Schlafen + Kind I + Kind II counted
- `TRAIT_2_BATHROOMS` ← Bad + DU/WC counted
- `TRAIT_UTILITY_ROOM` ← "HWR/Technik 9.21 m²" detected
- `TRAIT_GALLERY` ← "Galerie 24.06 m²" open upper space

**Negative traits (equally important for matching):**
- ✗ `TRAIT_SINGLE_FLOOR` — 2 floors (stairs visible)
- ✗ `TRAIT_LARGE_KITCHEN` — 13.63 m² < 15 m² threshold
- ✗ `TRAIT_HOME_OFFICE` — no dedicated room (but Galerie could serve)
- ✗ `TRAIT_MASTER_SUITE` — bedroom and bathroom not en-suite
- ✗ `TRAIT_MUDROOM` — no dedicated entrance hall

**Optional Room nodes for drill-down:**
```cypher
(:Room {name: "Wohnen/Essen", area_m2: 33.48, floor: "EG", type: "living"})
(FAM_X)-[:CONTAINS_ROOM]->(ROOM)
```

### What CANNOT Be Extracted (Need External Input)

- Model name / series
- Base price
- Roof type (not visible from floor plan)
- Available roof/facade variants
- Energy class / U-Wert
- Garage / carport (may be separate drawing)
- Ausbaustufe (completion level)

---

## 12. Required Inputs for Implementation

### MUST HAVE (Blocking)

1. **Product catalog** — all house models with: name, area, bedrooms, bathrooms, floors, price, min plot width, series, features
2. **Trait mapping** — which 15-25 features matter, and which models have them
3. **5-10 example conversations** — typical customer dialogues (real or realistic)
4. **Business rules** — what vetoes what (budget hard stop? plot hard stop? elderly = mandatory single floor?)
5. **Language + tone** — DE/PL/EN? Formal or friendly?

### NICE TO HAVE (Accelerators)

- Question priorities (what to ask first) — default: budget → plot → style → details
- Marketing descriptions per model — default: generate from specs
- FAQ / knowledge base content — default: KG-only, no RAG at start
- CRM conversion data — default: set `selection_priority` manually

### Minimum for PoC

1. Product catalog PDF (or link to product page)
2. 5 example customer conversations

From this, all graph data (L1/L2/L3) can be generated. Engine, retriever, Layer 4 — zero code changes.
