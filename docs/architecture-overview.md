# SynapseOS — Architecture Overview

## System Summary

SynapseOS is a **Graph-Augmented Reasoning Platform** that combines a 4-layer knowledge graph with LLM-powered intent extraction and domain-agnostic trait-based reasoning. The system is designed as a **multi-tenant, domain-agnostic engine** where all business logic lives in the graph — Python code is a pure processor.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER BROWSER                                │
│              Next.js 14 · React · Tailwind · shadcn/ui              │
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────┐  │
│  │ Chat UI  │  │ Graph Viewer │  │  Test Lab  │  │ Bulk Offers  │  │
│  │  (SSE)   │  │ (force-graph)│  │  (Judge)   │  │  (Excel/PDF) │  │
│  └────┬─────┘  └──────────────┘  └────────────┘  └──────────────┘  │
│       │ POST /consult/deep-explainable/stream                       │
│       │ + JWT auth + session_id                                     │
└───────┼─────────────────────────────────────────────────────────────┘
        │ SSE (Server-Sent Events)
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FASTAPI BACKEND (port 8000)                     │
│                                                                     │
│  ┌──────────────────── Request Pipeline ─────────────────────────┐  │
│  │                                                               │  │
│  │  1. SCRIBE (scribe.py)                                        │  │
│  │     LLM-first intent extraction → SemanticIntent              │  │
│  │     (dimensions, material, application, environment)          │  │
│  │                                                               │  │
│  │  2. STATE MERGE (state.py)                                    │  │
│  │     SemanticIntent → TechnicalState (cumulative across turns) │  │
│  │                                                               │  │
│  │  3. TRAIT ENGINE (universal_engine.py)                         │  │
│  │     Graph-driven pipeline:                                    │  │
│  │     stressors → rules → candidates → traits → vetoes →       │  │
│  │     goals → gates → assembly → constraints → capacity →      │  │
│  │     variance → accessories → clarifications → verdict         │  │
│  │                                                               │  │
│  │  4. LLM SYNTHESIS (retriever.py)                              │  │
│  │     EngineVerdict + REASONING_REPORT → narrative response     │  │
│  │                                                               │  │
│  │  5. PERSIST (session_graph.py)                                │  │
│  │     Write session state → Layer 4 graph nodes                 │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Supporting Services:                                               │
│  ┌────────────┐ ┌──────────┐ ┌────────────┐ ┌───────────────────┐  │
│  │ LLM Router │ │  Judge   │ │  Ingestor  │ │ Config Loader     │  │
│  │ (OpenAI +  │ │ (multi-  │ │ (email +   │ │ (tenant discovery │  │
│  │  Gemini)   │ │  model)  │ │  document) │ │  + DomainConfig)  │  │
│  └────────────┘ └──────────┘ └────────────┘ └───────────────────┘  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  FALKORDB (graph database, port 6379)                │
│                                                                     │
│  ┌─── Layer 1: Inventory ──┐  ┌── Layer 2: Domain/Physics ───────┐ │
│  │ ProductFamily, Item,    │  │ Stressor, CausalRule,            │ │
│  │ Trait, Material,        │  │ Environment, Application         │ │
│  │ DimensionModule         │  │                                  │ │
│  └─────────────────────────┘  └──────────────────────────────────┘ │
│                                                                     │
│  ┌─── Layer 3: Playbook ───┐  ┌── Layer 4: Session State ────────┐ │
│  │ LogicGate, Parameter,   │  │ Session, ActiveProject,          │ │
│  │ VariableFeature         │  │ TagUnit, ConversationTurn        │ │
│  └─────────────────────────┘  └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Design Principles

| Principle | Description |
|---|---|
| **Domain Agnosticism** | `universal_engine.py` contains ZERO domain-specific terms. All business rules, product names, and physics come from the graph. |
| **Graph = Intelligence** | Python is a processor. The knowledge graph holds ALL domain intelligence — stressors, causal rules, product traits, installation constraints. |
| **LLM-First Extraction** | Intent detection always goes through LLM (Scribe). Regex is only a last-resort fallback after LLM failure. |
| **4-Layer Separation** | Inventory → Physics → Playbook → Session State. Each layer has a distinct responsibility. |
| **Multi-Tenant** | All domain data in `tenants/<domain_id>/config.yaml` + `prompts/*.txt`. Runtime switching via API. |

---

## Component Breakdown

### Frontend (Next.js 14)

| Component | Role |
|---|---|
| `chat.tsx` | Main conversational UI. Consumes SSE stream, renders inference steps + final response. |
| `global-graph-viewer.tsx` | Full knowledge graph visualization (react-force-graph-2d). |
| `session-graph-viewer.tsx` | Layer 4 session state visualization. |
| `reasoning-chain.tsx` | Live display of engine pipeline steps during streaming. |
| `bulk-offer.tsx` | Bulk offer generation workflow (Excel/PDF upload → structured offers). |
| `test-lab.tsx` / `judge-*.tsx` | LLM-as-a-judge evaluation UI. |
| `lib/api.ts` | API helpers with JWT auth, SSE consumption, typed interfaces. |

### Backend — Request Pipeline

#### 1. Scribe (`logic/scribe.py`)
- **LLM-powered** semantic intent extraction (Gemini Flash / GPT, temp=0.0)
- Extracts: dimensions, material, application, environment, accessories, product family
- Graph-driven prompt: queries Environment + Application nodes to build valid enum lists
- Output: `SemanticIntent` dataclass

#### 2. TechnicalState (`logic/state.py`)
- In-memory working copy of the cumulative project specification
- Merges Scribe output turn-by-turn (new values override, nulls preserve previous)
- Bidirectional sync with Layer 4 graph nodes
- Assembly sibling sync via `domain_config.yaml` shared properties

#### 3. TraitBasedEngine (`logic/universal_engine.py`)
- **14-stage pipeline**, fully domain-agnostic:
  1. Detect stressors from resolved context
  2. Fetch causal rules from graph
  3. Get product family candidates
  4. Match traits and score
  5. Apply vetoes (environment blocks, material blocks)
  6. Compute goals and logic gates
  7. Assembly (multi-stage products for neutralization vetoes)
  8. Installation constraints (3 types: COMPUTED_FORMULA, SET_MEMBERSHIP, CROSS_NODE_THRESHOLD)
  9. Capacity rules and sizing arrangement
  10. Variance analysis
  11. Accessories
  12. Clarification check (missing required parameters)
  13. Alternatives generation (sales recovery)
  14. Final verdict assembly

- Output: `EngineVerdict` containing recommended products, violations, alternatives, clarifications

#### 4. LLM Synthesis (`retriever.py`)
- Takes `EngineVerdict` → builds `REASONING_REPORT` (structured prompt injection)
- Calls LLM with tenant-specific system prompt + report
- Generates natural language response with product recommendations

#### 5. Layer 4 Persistence (`logic/session_graph.py`)
- Writes session state to graph: Session → ActiveProject → TagUnit → ConversationTurn
- Enables cross-turn memory (the "Digital Twin" of the conversation)
- Sibling property sync across assembly groups

### Backend — Supporting Services

| Service | File | Role |
|---|---|---|
| **LLM Router** | `llm_router.py` | Unified `llm_call()` dispatching to OpenAI or Google GenAI by model prefix |
| **Judge** | `judge.py` | Multi-model evaluation across 6 quality dimensions |
| **Ingestor** | `ingestor.py`, `ingestor_docs.py` | Email thread + document ingestion into graph (2-pass AI extraction) |
| **Graph Auditor** | `graph_auditor.py` | PDF catalog vs graph consistency checking |
| **Config Loader** | `config_loader.py` | Tenant discovery, `DomainConfig` dataclass, prompt loading with cache |
| **Auth** | `auth.py` | JWT-based authentication |

---

## Data Flow: Graph Reasoning Mode

```
User message: "I need a filter housing for a commercial kitchen, 1200 CFM"
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │         1. SCRIBE              │
                    │  LLM extracts:                 │
                    │  • application: "kitchen"      │
                    │  • airflow: 1200               │
                    │  • product_hint: "housing"     │
                    └───────────────┬───────────────┘
                                    │ SemanticIntent
                                    ▼
                    ┌───────────────────────────────┐
                    │     2. STATE MERGE             │
                    │  TechnicalState updated:       │
                    │  • detected_application: "KIT" │
                    │  • airflow_cfm: 1200           │
                    │  + previous turn params kept   │
                    └───────────────┬───────────────┘
                                    │ resolved_context
                                    ▼
                    ┌───────────────────────────────┐
                    │     3. TRAIT ENGINE             │
                    │  Graph queries:                 │
                    │  • Kitchen → Grease stressor   │
                    │  • Grease → needs NEUTRALIZE   │
                    │  • ProductFamily candidates     │
                    │  • Trait matching + scoring     │
                    │  • Installation constraints     │
                    │  • Sizing: 1200 CFM → modules  │
                    │                                 │
                    │  Output: EngineVerdict          │
                    │  • recommended: [MH-3000-SS]    │
                    │  • assembly: 2-stage (pre+main) │
                    │  • violations: []               │
                    │  • clarifications: ["width?"]   │
                    └───────────────┬───────────────┘
                                    │ REASONING_REPORT
                                    ▼
                    ┌───────────────────────────────┐
                    │     4. LLM SYNTHESIS           │
                    │  System prompt + Report →      │
                    │  Natural language response      │
                    │  with product recommendation    │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │     5. PERSIST TO GRAPH        │
                    │  Layer 4:                       │
                    │  Session → ActiveProject →     │
                    │  TagUnit(MH-3000-SS) →         │
                    │  ConversationTurn(turn_2)       │
                    └───────────────────────────────┘
```

---

## LLM Model Routing

| Component | Model | Provider | Purpose |
|---|---|---|---|
| Scribe | `gpt-5.2` (DEFAULT_MODEL) | OpenAI | Intent extraction, temp=0.0, 768 tokens |
| Synthesis | `gpt-5.2` (DEFAULT_MODEL) | OpenAI | Final narrative generation |
| Fallback | `gemini-2.0-flash` | Google | Alternative provider, selectable via dropdown |
| Judge | Multi-provider | OpenAI + Google + Anthropic | Parallel quality evaluation |
| Debate | Selected providers | Multi | Test case generation |

---

## Multi-Tenant Architecture

```
backend/tenants/
└── mann_hummel/                    # Active tenant
    ├── config.yaml                 # ALL domain configuration
    │   ├── domain:                 # id, name, graph_name
    │   ├── entity_patterns:        # product codes, families, materials
    │   ├── material_environment_rules:  # material hierarchy
    │   ├── geometric_constraints:  # dimension rules
    │   ├── clarification_rules:    # required parameters
    │   ├── assembly:               # shared properties for sync
    │   ├── scribe_hints:           # LLM extraction hints
    │   └── fallback_keywords:      # regex fallback maps
    ├── bulk_offer.py               # Tenant-specific offer logic
    └── prompts/
        ├── system_generic.txt      # Main system prompt template
        ├── synthesis.txt           # Response synthesis prompt
        ├── judge_system.txt        # Judge evaluation prompt
        └── ...                     # (8 prompt files total)
```

**Tenant switching**: `POST /config/domain/{domain_id}` → reloads `DomainConfig` singleton.

---

## Deployment

| Component | Platform | Config |
|---|---|---|
| Backend | Fly.io (fra region) | `fly.toml`, 1 GB RAM, shared CPU, always-on |
| Frontend | Fly.io | Separate app |
| FalkorDB | Cloud-hosted | Redis-wire protocol, port 6379 |
| Dev | Local | `./scripts/dev.sh` (backend :8000 + frontend :3000) |

---

## Key API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/consult/deep-explainable/stream` | POST | **Primary**: Graph Reasoning with SSE streaming |
| `/session/{id}` | GET/DELETE | Layer 4 session state CRUD |
| `/graph/stats` | GET | Knowledge graph statistics |
| `/graph/all` | GET | Full graph visualization data |
| `/config/domain/{id}` | POST | Switch active tenant |
| `/judge/batch` | POST | Batch evaluation with LLM judges |
| `/offers/bulk/process` | POST | Bulk offer generation |
| `/ingest/document` | POST | Document ingestion into graph |
| `/health` | GET | Health check |
