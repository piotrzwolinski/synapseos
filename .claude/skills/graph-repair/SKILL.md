---
name: graph-repair
description: Diagnose and fix bugs in the SynapseOS Graph Reasoning pipeline. Use when given a bug report, test failure audit, or screenshot showing incorrect engine output (wrong airflow, dimension mismatch, missing assembly, wrong clarifications, LLM hallucination, etc.).
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Glob, Edit, Write, Bash, Task, mcp__neo4j__read_neo4j_cypher
argument-hint: "[symptom description or 'diagnose <screenshot>']"
---

# Graph Repair — Bug Diagnosis & Fix Workflow

You are a senior backend engineer debugging the SynapseOS Graph Reasoning pipeline. Given a bug report or test failure, you systematically trace the issue through the pipeline, identify the root cause, and fix it.

## DIAGNOSIS WORKFLOW

When given a bug report, follow these steps IN ORDER:

### Step 1: CLASSIFY the symptom

Read the bug description and classify it into one of these categories:

| Symptom | Layer | Start Looking At |
|---------|-------|-----------------|
| Wrong airflow suggestions / button values | Retriever | `_generate_airflow_options_from_graph()` in retriever.py:2832 |
| Wrong product family selected / no pivot | Engine | `process_query()` Step 4 (vetoes) in universal_engine.py:2660 |
| Missing assembly / wrong assembly stages | Engine | `build_assembly()` Step 5c in universal_engine.py:2080+ |
| Wrong dimensions on product card | State/Prompt | `extract_tags_from_query()` in state.py:954, then prompt injection |
| LLM says something wrong about dimensions/physics | Prompt | `to_prompt_injection()` in universal_engine.py:225 |
| Clarification asked when param already known | Guard | Triple guard: engine→adapter→retriever (see below) |
| Clarification NOT asked when it should be | Engine | `check_missing_parameters()` in universal_engine.py |
| Wrong material detected | State | `extract_material_from_query()` in state.py |
| Installation constraint not triggered | Engine | `check_installation_constraints()` + graph data |
| No alternatives shown when blocked | Engine | `find_alternatives_for_violation()` in universal_engine.py |
| Wrong module count / sizing | Engine | `compute_sizing_arrangement()` in universal_engine.py:1642 |
| State lost between turns | Session | `get_project_state()` in session_graph.py:447, `from_dict()` in state.py:700 |
| Button click not routed correctly | Retriever | `pending_clarification` handling, Scribe `clarification_answers` |

### Step 2: TRACE the data flow

The full pipeline is:

```
User Query
  ↓
[1] main.py:840 — consult_deep_explainable_stream() — SSE endpoint
  ↓
[2] retriever.py — main orchestrator:
    ├─ Load graph state → TechnicalState.from_dict() (state.py:700)
    ├─ Scribe LLM (scribe.py:200) → SemanticIntent extraction
    ├─ Merge Scribe + Regex fallback → tags, params, context
    ├─ Engine call → engine.process_query() (universal_engine.py:2660)
    ├─ Verdict adapter → adapt() (verdict_adapter.py:668)
    ├─ Prompt injection → report.to_prompt_injection()
    ├─ LLM call → Gemini generates response text
    ├─ Clarification enrichment → _generate_airflow_options_from_graph()
    └─ Persist → session_graph.upsert_tag() + store_turn()
  ↓
[3] SSE events → Frontend renders cards, buttons, text
```

### Step 3: VERIFY graph data

Before fixing code, check if the graph data is correct using Neo4j MCP:

```
Common diagnostic queries — see references/diagnostic-queries.md
```

### Step 4: FIX the issue

Apply the fix in the correct layer. See references/fix-patterns.md for patterns.

### Step 5: VERIFY the fix

- If graph data was changed: run a verification query
- If code was changed: describe what to test (use `/test-hvac` skill or manual test)

## KEY PIPELINE LOCATIONS (with line numbers)

### Retriever (retriever.py)
- `_generate_airflow_options_from_graph()` — line 2832 — builds airflow button suggestions
- Engine call: `engine.process_query(query, product_hint=..., context=...)` — line 1355
- `_get_trait_engine()` — line 1305 — singleton engine factory

### Engine (logic/universal_engine.py)
- `process_query()` — line 2660 — MAIN ENTRY, full pipeline
- `detect_stressors()` — Step 1
- `get_causal_rules()` — Step 2 (line 669)
- `get_candidate_products()` — Step 3 (line 696)
- `evaluate_logic_gates()` — Step 4a (line 893)
- `build_assembly()` — Step 5c (line 2080+)
- `check_installation_constraints()` — Step 5e2
- `calculate_capacity()` — Step 5f3 (line 1489)
- `compute_sizing_arrangement()` — Step 5f (line 1642)
- `assemble_verdict()` — Step 7 (line 2420)
- `EngineVerdict.to_prompt_injection()` — line 225

### Adapter (logic/verdict_adapter.py)
- `adapt()` — line 668 — converts EngineVerdict → GraphReasoningReport
- `_map_clarifications()` — line 959 — builds clarification questions
- `TraitBasedReport.to_prompt_injection()` — overrides base

### State (logic/state.py)
- `TechnicalState` — line 153 — dataclass with all session state
- `extract_tags_from_query()` — line 954 — regex tag parsing
- `extract_material_from_query()` — word-boundary matching
- `to_compact_summary()` — line 519 — token-efficient state for Scribe
- `from_dict()` / `to_dict()` — lines 700/662 — serialization

### Scribe (logic/scribe.py)
- `extract_semantic_intent()` — line 200 — LLM intent extraction
- `resolve_derived_actions()` — action resolution from intent

### Session Graph (logic/session_graph.py)
- `upsert_tag()` — line 318 — create/update TagUnit + sibling sync
- `store_turn()` — line 267 — conversation persistence
- `get_recent_turns()` — line 298 — Scribe context
- `get_project_state()` — line 447 — full state load

### SSE Endpoint (main.py)
- `consult_deep_explainable_stream()` — line 840
- Complete event assembly — line 322/479

## COMMON BUG PATTERNS

See references/common-bugs.md for known patterns and their fixes.

## TRIPLE GUARD (Clarification Suppression)

When a parameter is resolved, THREE guards must suppress re-asking:

1. **Engine guard**: `check_missing_parameters()` — checks key aliases in resolved_context
2. **Adapter guard**: `_map_clarifications()` — returns `[]` when `verdict.has_installation_block`
3. **Retriever guard**: `needs_clarification = False` when `suitability.is_suitable == False`

If a clarification leaks through, check ALL THREE guards.
