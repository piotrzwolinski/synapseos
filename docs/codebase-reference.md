# AI Solutions Finder — Codebase Reference

This document describes the backend structure and key integration points.

---

## 1. Project Structure

```
backend/
├── main.py                    ← FastAPI server, all API endpoints
├── retriever.py               ← Graph Reasoning pipeline orchestration
├── database.py                ← FalkorDB connection manager
├── llm_router.py              ← LLM provider routing (OpenAI / Gemini)
├── config_loader.py           ← Configuration loader (YAML → validated objects)
├── auth.py                    ← JWT authentication
│
├── logic/                     ← Core reasoning modules
│   ├── state.py               ← Session state management
│   ├── session_graph.py       ← Layer 4 graph persistence
│   └── dimension_tables.py    ← Dimension and material lookups
│
└── tenants/
    └── mann_hummel/
        ├── config.yaml        ← All MH-specific configuration
        └── prompts/           ← 5 prompt templates (see Prompt Reference)
```

---

## 2. Query Pipeline (High Level)

When a query arrives at `/consult/deep-explainable/stream`:

```
User Query
    │
    ▼
┌──────────────────┐
│ Intent Extraction │   LLM parses what the user is asking
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ State Update      │   Merges new info into the session's
│                   │   cumulative project specification
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Reasoning Engine  │   Queries the knowledge graph,
│                   │   evaluates constraints, selects products
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ LLM Response      │   Generates professional response
│ Generation        │   from reasoning results
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ State Persistence │   Saves session state to Layer 4
└──────────────────┘
```

The response streams back as Server-Sent Events (SSE) with status updates during processing.

---

## 3. Key Components

### 3.1 FastAPI Server (`main.py`)

The application entry point. Handles:
- HTTP request routing to the reasoning pipeline
- SSE streaming for real-time responses
- JWT authentication middleware
- Server startup (database warmup, cache initialization)

### 3.2 LLM Router (`llm_router.py`)

Routes LLM calls to the configured provider:

| Model Prefix | Provider |
|-------------|----------|
| `gpt-*` | OpenAI |
| `gemini-*` | Google Gemini |

Default model: `gpt-5.2`

Parameters available: `model`, `temperature`, `max_output_tokens`, `json_mode`

### 3.3 Configuration Loader (`config_loader.py`)

Loads MH-specific configuration from `tenants/mann_hummel/config.yaml` into a validated `DomainConfig` object.

**Key features:**
- Pydantic validation on all config sections
- Singleton — loaded once, cached in memory
- Hot reload via `POST /config/domain/{id}/reload` (no restart needed)
- Prompt templates loaded from `tenants/mann_hummel/prompts/`

**What DomainConfig contains:**

| Category | Data |
|----------|------|
| Product definitions | Product family codes, material codes, option codes |
| Material rules | Material hierarchy with corrosion classes, demanding environment constraints |
| Product rules | Capabilities, limitations, installation warnings |
| Geometry | Dimension mapping (filter → housing), housing length derivation |
| Clarification | Required parameters with priority ordering |
| Assembly | Properties shared across assembly stages |

**Helper methods** generate formatted rule sections for prompt injection:
- `get_material_rules_prompt()` — material hierarchy + demanding environments
- `get_product_rules_prompt()` — product capabilities + warnings
- `get_geometric_rules_prompt()` — dimension constraints
- `get_accessory_rules_prompt()` — accessory compatibility

### 3.4 Database Connection (`database.py`)

Manages the FalkorDB connection (Redis wire protocol, Cypher queries).

- Singleton connection with automatic retry on failure
- Environment-variable configuration: `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_PASSWORD`
- Query caching with 5-minute TTL
- Connection warmup on server startup

### 3.5 Session State (`logic/state.py`)

Tracks the cumulative project specification across conversation turns. Each session maintains:

| Data | Description |
|------|-------------|
| Active product family | Currently selected product type |
| Application & environment | Detected application type and installation environment |
| Per-product specs | Dimensions, airflow, material, housing length per product in the project |
| Resolved parameters | All user-provided values accumulated across turns |
| Pending clarification | Which parameter is currently being asked about |

**Key behavior:** New values override previous ones; unmentioned parameters are preserved.

### 3.6 Layer 4 Persistence (`logic/session_graph.py`)

Persists session state as graph nodes in FalkorDB for cross-turn memory:

| Node | Purpose |
|------|---------|
| `Session` | Root node per conversation |
| `ActiveProject` | Current project context |
| `TagUnit` | Individual product specification |
| `ConversationTurn` | Message history |

API access: `GET /session/graph/{session_id}` returns the full state.

### 3.7 Dimension Tables (`logic/dimension_tables.py`)

Provides lookup functions with a priority chain:

```
Graph data (loaded at startup) → Config (config.yaml) → Defaults
```

| Function | Returns |
|----------|---------|
| `get_dimension_map()` | Filter size → housing size |
| `get_corrosion_map()` | Material code → corrosion class |
| `derive_housing_length()` | Filter depth + product → housing length |

---

## 4. Authentication (`auth.py`)

JWT-based authentication with two roles:

| Role | Access |
|------|--------|
| `admin` | Full access to all endpoints |
| `expert` | Consultation + review endpoints |

Token flow:
1. `POST /auth/login` with username/password → JWT token
2. Include `Authorization: Bearer <token>` on all subsequent requests
3. Tokens expire after 24 hours

---

## 5. SSE Streaming Protocol

The primary endpoint (`/consult/deep-explainable/stream`) returns Server-Sent Events:

| Event Type | When | Content |
|-----------|------|---------|
| `status` | During processing | Step description (e.g., "Analyzing intent…") |
| `reasoning` | After engine completes | Reasoning chain data |
| `response` | Final | Structured JSON with product recommendations |
| `error` | On failure | Error details |

**Frontend consumption:** Open an `EventSource` connection, parse each event by type, render progressively.

---

## 6. Adding or Modifying MH Data

| What to change | Where | Restart needed? |
|---------------|-------|----------------|
| Product rules, material constraints | `config.yaml` | No — reload via API |
| Prompt behavior | `prompts/*.txt` | No — reload via API |
| Products, traits, stressors, constraints | FalkorDB graph (Cypher queries) | No — read at query time |
| Dimension mappings | `config.yaml` → `dimension_mapping` | No — reload via API |
| Clarification questions and order | `config.yaml` → `clarification_rules` | No — reload via API |
| API endpoints or server behavior | Python code | Yes — server restart |
