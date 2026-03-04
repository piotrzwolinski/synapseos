# AI Solutions Finder — Architecture Overview

## 1. System Overview

The AI Solutions Finder is an AI-powered knowledge graph engine built for Mann+Hummel's air filtration product portfolio. It combines structured product and domain knowledge with Large Language Models to provide intelligent product selection, technical consultation, and sales support.

The system uses **Graph Reasoning** — AI-guided traversal of the knowledge graph with a full reasoning chain — to deliver technical consultations, product selection, and constraint validation.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                             │
│                  Next.js 14 + React 18                      │
│                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐         │
│  │       Chat UI        │  │       Test Lab       │         │
│  │                      │  │                      │         │
│  └──────────────────────┘  └──────────────────────┘         │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS / SSE Streaming
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                        BACKEND                              │
│                   FastAPI (Python 3.12)                      │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              API Layer (REST + SSE)                   │   │
│  │  Authentication · Session Management · Streaming      │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │            Reasoning Engine                           │   │
│  │  Intent Recognition · Graph Traversal · Constraint    │   │
│  │  Validation · Product Selection · Response Assembly    │   │
│  └───────────┬──────────────────────────┬───────────────┘   │
│              │                          │                    │
│  ┌───────────▼──────────┐  ┌───────────▼───────────────┐   │
│  │   Knowledge Graph    │  │      LLM Provider         │   │
│  │   (FalkorDB)         │  │      (OpenAI GPT)         │   │
│  └──────────────────────┘  └───────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. The Knowledge Graph

The knowledge graph is the core intelligence layer. It encodes Mann+Hummel's product portfolio, physics rules, and sales logic in a structured, queryable format. It is organized in **4 layers**:

```
┌─────────────────────────────────────────────┐
│  Layer 4: Session State                     │  ← Per-conversation project state
│  Current project parameters, selections,    │    (the "Digital Twin")
│  resolved constraints                       │
├─────────────────────────────────────────────┤
│  Layer 3: Playbook                          │  ← Decision logic & inquiry flow
│  Decision trees, parameter priorities,      │
│  clarification sequences                    │
├─────────────────────────────────────────────┤
│  Layer 2: Domain Physics                    │  ← How the world works
│  Stressors, causal rules,                   │
│  environmental constraints                  │
├─────────────────────────────────────────────┤
│  Layer 1: Inventory                         │  ← What we sell
│  Products, traits, sizes, capacities,       │
│  installation constraints                   │
└─────────────────────────────────────────────┘
```

| Layer | Contents | Example |
|-------|----------|---------|
| **Layer 1 — Inventory** | Product families, traits, physical properties, sizing tables | OurAir SQ 2500 with its dimensions and capacity data |
| **Layer 2 — Physics** | Stressors, causal rules, environmental factors | "Grease" stressor in kitchen environments requires specific product traits |
| **Layer 3 — Playbook** | Decision trees, parameter priority, clarification logic | System asks about application type before dimensions |
| **Layer 4 — State** | Per-session project twin: resolved parameters, selected products | Session stores: Kitchen, 5000 m³/h, OurAir SQ 2500 selected |

**Key property:** Layer 4 persists across conversation turns, so the system never "forgets" what was discussed earlier in the session.

---

## 4. Graph Reasoning Flow

When a user asks a question in Graph Reasoning mode:

```
 User Query
     │
     ▼
 ┌────────────────┐
 │ Intent          │   Understands what the user is asking:
 │ Recognition     │   application, environment, dimensions,
 │ (LLM-based)    │   airflow, or a follow-up clarification
 └───────┬────────┘
         │
         ▼
 ┌────────────────┐
 │ Graph           │   Queries the 4-layer knowledge graph
 │ Traversal       │   to gather relevant facts, rules,
 │                 │   and constraints
 └───────┬────────┘
         │
         ▼
 ┌────────────────┐
 │ Reasoning       │   Applies domain rules, checks constraints,
 │ Engine          │   validates compatibility, selects products,
 │                 │   computes sizing
 └───────┬────────┘
         │
         ▼
 ┌────────────────┐
 │ Response        │   Generates a professional response with
 │ Assembly        │   product recommendations, reasoning chain,
 │ (LLM + Graph)  │   and any required clarification questions
 └───────┬────────┘
         │
         ▼
 Streamed Response
 (SSE real-time)
```


---

## 5. Key Capabilities

### 5.1 Intelligent Product Selection
The engine matches user requirements (application, environment, airflow, dimensions) against the knowledge graph to recommend suitable MH products. It handles:
- Environmental constraints (e.g., material compatibility for corrosive or high-temperature environments)
- Spatial constraints (available installation space vs. product dimensions)
- Capacity requirements (airflow volume → module count and arrangement)
- Multi-module arrangements for large installations

### 5.2 Constraint Validation
Every recommendation is validated against installation constraints stored in the graph. If a product cannot be installed in the specified environment or space, the system explains why and suggests alternatives.

### 5.3 Sales Recovery (Alternatives)
When a constraint blocks a product, the system automatically searches for:
- Alternative configurations of the same product (e.g., different material)
- Alternative products from other MH families that satisfy the requirements
- All alternatives are validated against the same rules to ensure they are viable

### 5.4 Multi-Turn Conversations
The system maintains full context across conversation turns via Layer 4 (Session State). Users can refine requirements incrementally without repeating information.

### 5.5 Smart Clarifications
When critical parameters are missing, the system asks targeted clarification questions in priority order — driven by the Playbook layer in the graph.

### 5.6 Assembly Support
For products that require pre-filtration or multi-stage configurations, the system automatically detects this need and recommends the complete assembly — including all stages and their specifications.

---

## 6. Platform Features

### Chat Interface
- Real-time streaming responses (Server-Sent Events)
- Live reasoning chain visualization during inference
- Session history with full project state

### Test Lab & AI-as-Judge
- Automated test suite execution against the reasoning engine
- Multi-LLM evaluation (AI-as-Judge) scoring response quality across dimensions
- Batch testing with historical result tracking and comparison
- Test case generation from product catalog PDFs


### Graph Audit
- Multi-LLM debate system for validating graph data integrity
- Automated detection of missing, inconsistent, or contradictory rules

---

## 7. Customization for Mann+Hummel

All MH-specific knowledge is maintained separately from the core engine:

- **Product catalog** — encoded as graph nodes (ProductFamily, Trait, DimensionModule, CapacityRule)
- **Physics rules** — stressor-to-trait relationships (e.g., Grease → requires NEUTRALIZATION)
- **Installation constraints** — material/environment compatibility, spatial limits
- **Prompt templates** — MH-branded professional language and response style
- **Configuration** — material hierarchies, dimension rules, clarification priorities

Adding new products, rules, or constraints is a **graph data operation** — no code changes required. The engine reads all intelligence from the graph at query time.

---

## 8. Deployment Infrastructure

```
                     Microsoft Azure — West Europe
  ┌──────────────────────────────────────────────────┐
  │                                                  │
  │   ┌──────────────┐     ┌──────────────────┐     │
  │   │  Frontend     │     │   Backend        │     │
  │   │  Next.js      │────▶│   FastAPI        │     │
  │   │  Container    │     │   Container      │     │
  │   │  Port 3000    │     │   Port 8000      │     │
  │   └──────────────┘     └────────┬─────────┘     │
  │                                  │               │
  │                         ┌────────▼─────────┐     │
  │                         │   FalkorDB       │     │
  │                         │   Graph Database │     │
  │                         │   Persistent Vol │     │
  │                         │   Port 6379      │     │
  │                         └──────────────────┘     │
  │                                                  │
  └──────────────────────────────────────────────────┘
```

| Component | Technology | Deployment |
|-----------|-----------|-----------|
| Frontend | Next.js 14, containerized (Docker) | Azure Container Apps |
| Backend | FastAPI (Python 3.12), containerized (Docker) | Azure Container Apps |
| Database | FalkorDB (graph DB, Redis protocol) | Azure Container Apps + persistent volume |
| LLM | OpenAI GPT (external API calls) | — |
| Region | West Europe | HTTPS enforced on all traffic |

### Security
- JWT authentication (24h token expiry)
- Role-based access control: **Admin** and **Expert** roles
- HTTPS enforced on all endpoints
- Non-root container execution
- API key management for LLM providers (server-side only)

---

## 9. Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS, Radix UI |
| Visualization | react-force-graph-2d (interactive graph rendering) |
| Backend | Python 3.12, FastAPI, Server-Sent Events (SSE) |
| Graph Database | FalkorDB (Cypher query language, Redis wire protocol) |
| LLM Providers | OpenAI GPT |
| Deployment | Docker containers on Azure |
| Authentication | JWT (Bearer tokens, HS256) |

---

## 10. Data Flow Summary

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌───────────┐
│  User    │───▶│ Frontend │───▶│   Backend    │───▶│ FalkorDB  │
│  Browser │◀───│ Next.js  │◀───│   FastAPI    │◀───│ Graph DB  │
└──────────┘    └──────────┘    └──────┬───────┘    └───────────┘
   SSE stream      REST/SSE           │
                                      │
                               ┌──────▼───────┐
                               │  LLM APIs    │
                               │  OpenAI GPT  │
                               └──────────────┘
```

1. User sends a query via the chat interface
2. Frontend opens an SSE connection to the backend
3. Backend extracts intent using LLM, queries the knowledge graph
4. Reasoning engine processes MH domain rules and constraints from the graph
5. LLM generates the final response using graph-supplied context
6. Response streams back in real-time with reasoning chain visible in the UI
7. Session state is persisted in Layer 4 for multi-turn continuity
