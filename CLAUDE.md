# SynapseOS — Claude Code Architectural Guidelines (v2.0)

## 1. THE GOLDEN RULE: STRICT DOMAIN AGNOSTICISM
- `backend/logic/universal_engine.py` is a **Dumb Processor**. It MUST NOT contain HVAC words (filter, housing, airflow).
- All domain-specific logic must be fetched as **Metadata** from the Graph (Neo4j).
- Use `property_key` from the graph to access values in `ProjectState`.
- If you need to add a "Kitchen" rule, add it to the **Graph**, not the Python code.

## 2. THE 4-LAYER KNOWLEDGE GRAPH
1.  **Layer 1 (Inventory):** `(:Item)` & `(:Trait)`. Hard facts about what we sell.
2.  **Layer 2 (Domain/Physics):** `(:Stressor)` & `(:CausalRule)`. How the world works (e.g., Grease blocks Pores).
3.  **Layer 3 (Playbook/Strategy):** `(:LogicGate)` & `(:Parameter)`. Decision trees and inquiry priority.
4.  **Layer 4 (State):** `(:Session)` & `(:Unit)`. The Digital Twin of the current project.

## 3. ASSEMBLY & MULTI-STAGE PROTOCOL
- When an `AssemblyRule` or `Protector` is required, the system splits an `item_n` into `item_n_stage_1`, `item_n_stage_2`.
- **Persistence:** These stages MUST be persisted in Layer 4 (Graph State).
- **Synchronization:** Shared parameters (Dimensions, Airflow) must be synced across all stages of an assembly automatically via `sync_assembly_params()`.
- **Output:** The LLM must receive ALL stages of the assembly to generate the final response.

## 4. CONTEXT LOCK & TRIPLE GUARD
Every parameter MUST flow through all 4 layers to prevent "Context Amnesia":
1. **Extraction** (Regex/LLM) -> 2. **TechnicalState** (Python) -> 3. **Graph State** (Layer 4) -> 4. **Prompt Context** (LLM).

**Clarification Suppression Rule:**
A parameter is "Resolved" only if it exists in Layer 4. Three guards must check this:
- **Engine guard**: `check_missing_parameters()` using key aliases.
- **Python guard**: `retriever.py` keyword filter.
- **LLM guard**: Prompt injection `✓ KNOWN: DO NOT ask`.

## 5. TECHNICAL STANDARDS & DATA PRECISION
- **Type Safety:** Always cast numeric inputs (airflow, width) to `int` or `float` immediately. Graph operators (>=, <=) fail on strings.
- **Weight Calibration:** Never estimate weights. Weights MUST be looked up from the specific column-row intersection in the graph based on `housing_length` and `size`.
- **JSON Integrity:** Gemini Flash truncates at 2048 tokens. Use `_repair_truncated_json()` if the JSON object is incomplete.
- **Streaming:** Use SSE events for "Thought Process" status updates. DO NOT stream raw JSON tokens.

## 6. CYGHER QUERY RULES
- **Driver Singleton:** Use `Database.get_driver()` to avoid SSL handshake latency.
- **Batching:** Never query in a loop. Use `UNWIND $list AS item` to perform bulk lookups.
- **Versioning:** Use `COALESCE(s.prop, $val)` for Neo4j property updates.

## 7. GRAPH-DRIVEN INTELLIGENCE (v2.7+)
Python is a processor, the Graph holds ALL intelligence:
- **State Continuity**: Active product family, assembly groups, resolved params — all persisted in Layer 4. On continuation turns, Python reads from graph state (`technical_state.detected_family`), not from query text. No role-specific or HVAC-specific fallback logic in Python.
- **Sibling Property Sync**: When a property is set on one assembly unit, Cypher propagates to siblings via `assembly_group_id` on TagUnit nodes. Python `_sync_assembly_params()` reads which properties to sync from `domain_config.yaml` (`assembly.shared_properties`), not from a hardcoded tuple.
- **Auto-Resolve**: `VariableFeature.auto_resolve=true + default_value` in the graph. Engine reads and applies BEFORE `check_missing_parameters()` — no Python knowledge of which params have defaults.
- **Prompt Templates**: NEVER include domain-specific examples in the generic system prompt (`DEEP_EXPLAINABLE_SYSTEM_PROMPT_GENERIC`). Use `[Application]`, `[Stressor]` placeholders that the LLM fills from the graph-supplied REASONING_REPORT via `to_prompt_injection()`.

### 8. Geometric Constraint Enforcement (v2.8)
- **Dimension constraint timing**: Width/length extraction MUST happen BEFORE `resolved_context` building and engine call. Constraints stored in `resolved_params` for cross-turn persistence via Layer 4.
- **`selection_priority`**: Graph property on `ProductFamily` nodes. Lower = preferred for protector role. Engine iterates candidates in priority order (Cypher `ORDER BY` + Python defense-in-depth sort). No role name checks in Python.
- **Arrangement geometry**: `compute_sizing_arrangement()` computes `horizontal_count`, `vertical_count`, `effective_width`, `effective_height`. When width-constrained, modules stack vertically. Effective dimensions (not module dimensions) are applied to tags.

## File Map
- `backend/logic/universal_engine.py`: The Agnostic Heart.
- `backend/database.py`: The Data Access Layer (Batch queries only).
- `backend/logic/session_graph.py`: Layer 4 State Manager (Cypher sibling sync).
- `backend/logic/state.py`: TechnicalState — working copy with config-driven assembly sync.
- `backend/retriever.py`: The Professional Persona & Narrative.
- `backend/domain_config.yaml`: Domain-specific configuration (assembly sync properties, etc.).
- `backend/config_loader.py`: Type-safe config loader (DomainConfig dataclass).

## For UI testing - use "Graph Reasoning" option from the top bar (initially it is the "LLM Only" button)

## For use case testing - do not use browser per default. Test with the same endpoints that are used for "Graph Reasoning" mode.

## For intent recognition - use llm. do not use regexp (only as fallback).