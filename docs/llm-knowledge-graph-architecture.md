# AI Solutions Finder — LLM + Knowledge Graph Architecture

How the system combines Large Language Models with a Knowledge Graph to deliver accurate, explainable product recommendations.

---

## 1. The Core Idea

Traditional chatbots rely entirely on an LLM — they can hallucinate specs, forget constraints, and give inconsistent answers across turns. The AI Solutions Finder solves this by splitting responsibilities:

| | Knowledge Graph | LLM (GPT) |
|---|---|---|
| **Role** | Domain expert | Communicator |
| **Owns** | Facts, rules, constraints, product data | Natural language understanding & generation |
| **Strength** | 100% accurate, deterministic, auditable | Flexible, conversational, multilingual |
| **Weakness** | Cannot understand free text | Can hallucinate if unsupervised |

**The principle:** The graph decides *what* to recommend. The LLM decides *how* to say it.

---

## 2. Why Both Are Needed

### What the LLM alone cannot do

- Guarantee that a product is physically compatible with an environment
- Track 15+ parameters across a multi-turn conversation without drift
- Enforce hard engineering constraints (minimum dimensions, material ratings)
- Provide a deterministic audit trail ("why was this product selected?")

### What the Knowledge Graph alone cannot do

- Understand "I need something for a greasy kitchen, about 3400 cubic meters per hour"
- Ask follow-up questions in natural, professional language
- Explain physics in a way a project manager understands
- Handle multilingual input (English, Polish, Swedish, German)

### Together

The graph provides **engineering certainty**. The LLM provides **human communication**. Neither can replace the other.

---

## 3. The Pipeline — Step by Step

When a user sends a message, it flows through four stages:

```
                           User Message
                               │
                               ▼
                  ┌─────────────────────────┐
           LLM   │   1. Intent Extraction   │   "What does the user want?"
                  │      (GPT call #1)       │
                  └────────────┬────────────┘
                               │ Structured parameters
                               ▼
                  ┌─────────────────────────┐
                  │   2. State Update        │   Merge new info into
                  │      (Python)            │   cumulative project spec
                  └────────────┬────────────┘
                               │ Complete project state
                               ▼
                  ┌─────────────────────────┐
         Graph    │   3. Reasoning Engine    │   Query graph, evaluate
                  │      (FalkorDB)          │   rules, select products
                  └────────────┬────────────┘
                               │ Verdict (facts + constraints)
                               ▼
                  ┌─────────────────────────┐
           LLM   │   4. Response Synthesis  │   Turn facts into a
                  │      (GPT call #2)       │   professional response
                  └─────────────────────────┘
```

---

### Stage 1 — Intent Extraction (LLM)

**What happens:** The LLM reads the user's message and extracts structured data.

**Input:** Free-text user message + conversation history + current project state

**Output:** Structured JSON with:
- Product dimensions (width, height, depth)
- Airflow requirements
- Material preferences
- Application type (kitchen, hospital, pool, etc.)
- Environment (outdoor, marine, clean room, etc.)

**Example:**

> User: *"I need a unit for a hospital ventilation system, 600×600, stainless steel, 3400 m³/h"*

Extracted:
```
dimensions:    600 × 600 mm
airflow:       3400 m³/h
material:      Stainless Steel (RF)
application:   Hospital
```

**Why LLM:** Free text is messy — users write in different languages, use abbreviations, refer to previous messages ("same size as before"). Only an LLM can reliably parse this.

---

### Stage 2 — State Update (Python)

**What happens:** The extracted parameters are merged into the cumulative project specification.

**Key behavior:**
- New values override previous ones (user changed their mind)
- Unmentioned parameters are preserved (no "forgetting")
- State is persisted in the graph database for cross-session continuity

**Example — Turn 2:**

> User: *"Actually, make it 900×900 instead"*

Only dimensions change. Airflow (3400), material (RF), and application (hospital) are preserved from Turn 1.

---

### Stage 3 — Reasoning Engine (Knowledge Graph)

**What happens:** The engine queries the knowledge graph to evaluate the project against all known rules and constraints. This is pure graph traversal — no LLM involved.

The engine runs through a series of evaluations:

```
  ┌──────────────────────────────────────────────────┐
  │              REASONING ENGINE                     │
  │                                                    │
  │  ① Stressor Detection                            │
  │     "Hospital → Chemical disinfection, Humidity"  │
  │                                                    │
  │  ② Rule Evaluation                                │
  │     "Chemical exposure → requires C5 corrosion    │
  │      resistance (CRITICAL)"                        │
  │                                                    │
  │  ③ Product Matching                               │
  │     Score each product family by trait coverage    │
  │     GDB: 60%  GDP: 45%  GDC: 90%  GDMI: 85%     │
  │                                                    │
  │  ④ Constraint Checking                            │
  │     "GDB in galvanized steel → BLOCKED            │
  │      (hospital requires C5, FZ only rated C3)"    │
  │                                                    │
  │  ⑤ Assembly Detection                             │
  │     "This application requires pre-filtration →   │
  │      add protector stage"                          │
  │                                                    │
  │  ⑥ Missing Parameter Check                        │
  │     "Housing length not specified → ask user"      │
  │                                                    │
  └──────────────────────────────────────────────────┘
```

**Output — the Verdict:**

A structured result containing:
- Recommended product(s) with full specifications
- Any constraint violations with explanations
- Assembly requirements (multi-stage configurations)
- Missing parameters that still need to be collected
- Physics reasoning chain (which stressor triggered which rule)

**Why Knowledge Graph:** Every fact is traceable. "Why stainless steel?" → Because hospital environment exposes to chemical disinfectants → which demands C5 corrosion resistance → which only RF and SF materials provide. This chain lives entirely in the graph and can be audited.

---

### Stage 4 — Response Synthesis (LLM)

**What happens:** The LLM receives the graph verdict and converts it into a professional, readable response.

**Input:**
- The full verdict from the reasoning engine (injected into the system prompt)
- The user's original question
- Conversation history

**Output:** A structured response with:
- Product recommendation with specifications
- Physics explanation (why this product, why this material)
- Any warnings or constraint violations
- Next clarification question (if parameters are still missing)

**Key rule — Source Hierarchy:**

| Priority | Source | How to present |
|----------|--------|----------------|
| 1 | Graph verdict | Present as established fact |
| 2 | LLM's own engineering knowledge | Separate as "Engineering Note" |
| 3 | No data available | Do not speculate |

The LLM is explicitly instructed: **graph data overrides your own knowledge**. If the graph says a product is incompatible, the LLM cannot override that.

**Example response:**

> *For your hospital ventilation project at 3400 m³/h with 600×600 housing:*
>
> *I recommend the **GDB-600×600-RF** in stainless steel (304). The hospital environment requires C5 corrosion resistance due to chemical disinfection protocols, which stainless steel provides.*
>
> *To finalize the specification, which housing length suits your installation? Available options: 550mm, 750mm, or 900mm.*

---

## 4. The Knowledge Graph — What It Contains

The graph is organized in three layers:

### Layer 1 — Inventory (What we sell)

All products, sizes, materials, weights, and configurations.

```
(ProductFamily:GDB) ──AVAILABLE_IN_SIZE──▶ (DimensionModule:600×600)
                     ──AVAILABLE_IN_MATERIAL──▶ (Material:RF)
                     ──HAS_VARIANT──▶ (ProductVariant:GDB-600×600-750)
```

### Layer 2 — Domain Physics (How the world works)

Environmental stressors, causal rules, and physical trait requirements.

```
(Application:Hospital) ──EXPOSES_TO──▶ (Stressor:ChemicalDisinfection)
(Stressor:ChemicalDisinfection) ──DEMANDS_TRAIT──▶ (Trait:CorrosionResistance_C5)
(Material:RF) ──PROVIDES_TRAIT──▶ (Trait:CorrosionResistance_C5)
```

### Layer 3 — Playbook (Decision logic)

Logic gates, parameters, capacity rules, and clarification priorities.

```
(LogicGate:GreaseExposure) ──MONITORS──▶ (Stressor:Grease)
                           ──REQUIRES_DATA──▶ (Parameter:Airflow)
```

**The graph currently contains ~1,000 nodes and ~3,000 relationships** covering all MH product families, materials, environments, and engineering constraints.

---

## 5. Reasoning Chain — Transparency

Every recommendation comes with a full reasoning chain that traces back to graph data:

```
User asked: "GDB housing for hospital in galvanized steel"

Reasoning Chain:
  ├─ Application detected: Hospital
  │   └─ Stressors: Chemical disinfection, High humidity
  │       └─ Rule: Chemical exposure demands C5 corrosion resistance (CRITICAL)
  │
  ├─ Material requested: FZ (Galvanized Steel)
  │   └─ Corrosion rating: C3
  │       └─ VIOLATION: C3 < C5 required → Material blocked
  │
  ├─ Constraint: Hospital requires minimum C5 material
  │   └─ Compatible materials: RF (Stainless 304), SF (Stainless 316L)
  │
  └─ Recommendation: Override material to RF (Stainless Steel)
      └─ Reason: "Galvanized steel (C3) does not meet hospital hygiene
                  requirements. Stainless steel (C5) is required for
                  chemical disinfection resistance."
```

This chain is:
- **Deterministic** — same inputs always produce the same chain
- **Auditable** — every step references a graph relationship
- **Explainable** — the LLM converts it to natural language for the user

---

## 6. Multi-Turn Conversation — State Continuity

The system maintains a cumulative project specification across the entire conversation:

```
Turn 1: "I need a unit for a kitchen, 600×900"
         → State: {application: kitchen, dimensions: 600×900}

Turn 2: "3400 cubic meters per hour"
         → State: {application: kitchen, dimensions: 600×900, airflow: 3400}

Turn 3: "Actually, make it stainless steel"
         → State: {application: kitchen, dimensions: 600×900, airflow: 3400, material: RF}

Turn 4: "What about 900×900 instead?"
         → State: {application: kitchen, dimensions: 900×900, airflow: 3400, material: RF}
```

Each turn, the graph engine re-evaluates the complete state. Parameters accumulate; nothing is forgotten unless explicitly changed.

State is persisted in the graph database (Layer 4), so conversations can be resumed across sessions.

---

## 7. Quality Assurance — AI-as-Judge

An independent evaluation framework scores every response on 6 dimensions:

| Dimension | What it checks |
|-----------|----------------|
| Accuracy | Do product specs match graph data? |
| Completeness | Are all relevant constraints addressed? |
| Consistency | Does the response align with the reasoning chain? |
| Safety | Are material/environment warnings properly surfaced? |
| Clarity | Is the response understandable for a project manager? |
| Relevance | Does it answer what the user actually asked? |

The judge uses a separate LLM call with access to the graph verdict, ensuring the response faithfully represents the engineering analysis.

---

## 8. Summary — The Best of Both Worlds

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   Knowledge Graph              LLM (GPT)                   │
│   ══════════════              ═══════════                   │
│                                                             │
│   ✓ Product database          ✓ Understands free text       │
│   ✓ Physics rules             ✓ Multilingual                │
│   ✓ Constraint logic          ✓ Professional tone           │
│   ✓ Deterministic             ✓ Explains physics            │
│   ✓ Auditable                 ✓ Handles ambiguity           │
│   ✓ Zero hallucination        ✓ Asks smart follow-ups       │
│                                                             │
│           Graph provides FACTS                              │
│           LLM provides NARRATIVE                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

The result: a system that combines the accuracy of a structured database with the conversational intelligence of a modern LLM — giving MH sales engineers a tool that is both reliable and easy to use.
