# Common Bug Patterns — Known Issues and Their Root Causes

## 1. Material `'rf' in 'airflow'` (Substring Match Bug)
**Symptom:** Wrong material detected (RF instead of FZ) when query contains "airflow"
**Root cause:** `extract_material_from_query()` used `if kw in query_lower` — `'rf'` matched inside `'airflow'`
**Fix:** `re.search(r'\b' + re.escape(kw) + r'\b', query_lower)` for word boundary matching
**File:** state.py, `extract_material_from_query()`

## 2. Default Tag Missing (Airflow Without Dimensions)
**Symptom:** Airflow value detected but nowhere to store it (no tags extracted)
**Root cause:** Query like "25,000 m³/h, max height 1000mm" has airflow but no dimension pattern → `extract_tags_from_query()` returns empty
**Fix:** Create default "item_1" tag when airflow detected in query but no tags exist
**File:** retriever.py, before airflow extraction section

## 3. Height/Width Constraint Natural Order
**Symptom:** "max height 1000mm" not detected as constraint
**Root cause:** Regex only matched "max 1000mm height" and "height max 1000mm" but NOT "max height 1000mm"
**Fix:** Added `_natural` pattern: `max(?:imum)?\s+(?:available\s+)?(?:height|...)\s+(?:is\s+)?(\d+)\s*(?:mm)?`
**File:** retriever.py, constraint extraction section

## 4. Numeric Normalization
**Symptom:** "6,000 m³/h" or "25 000 m³/h" not parsed as numbers
**Root cause:** Comma/space thousand separators not stripped before regex
**Fix:** `_normalize_numeric_string()` strips separators. Applied BEFORE all airflow regex patterns.
**File:** retriever.py for airflow, state.py `_normalize_numeric_in_text()` for tag extraction

## 5. Graph State Loading Empty Tags
**Symptom:** State seems lost, project-level data (material, family) not restored
**Root cause:** `if graph_state.get("tags")` returns False for empty list `[]`
**Fix:** `if graph_state.get("tags") or graph_state.get("project")`
**File:** retriever.py, graph state loading section

## 6. False ATEX Triggering
**Symptom:** ATEX gate fires for non-explosive environments (e.g., office)
**Root cause:** ENV_ATEX keyword "ex" substring-matched inside "context" from Scribe-augmented query
**Fix:** Changed keyword from "ex" → "ex zone"; replaced keyword matching with Scribe-based environment detection
**File:** universal_engine.py `detect_stressors()`, ENV_ATEX graph node keywords

## 7. Orphan Assembly Tags
**Symptom:** Stale tags from previous assembly remain after re-evaluation
**Root cause:** Assembly splits item_1 → item_1_stage_1 + item_1_stage_2, but if assembly not needed next turn, old stages persist
**Fix:** Defense-in-depth cleanup after engine call — remove leaked orphans when assembly_group exists
**File:** retriever.py, after engine call section

## 8. Prompt Contamination
**Symptom:** LLM makes domain-specific assumptions not backed by graph
**Root cause:** Hardcoded domain text in system prompt (e.g., "Kitchen exhaust contains grease")
**Fix:** Replace with generic placeholders `[Application] exposes [Stressor]` — LLM fills from graph-supplied REASONING_REPORT
**File:** retriever.py, DEEP_EXPLAINABLE_SYSTEM_PROMPT_GENERIC

## 9. Dimension Lock Override
**Symptom:** User requests 600x600 but system picks 1200x600 (larger module)
**Root cause:** `compute_sizing_arrangement()` picked largest-fitting module instead of exact match
**Fix:** Check explicit dimensions FIRST, space constraints only for arrangement geometry
**File:** universal_engine.py:1642, `compute_sizing_arrangement()`

## 10. Sibling Sync Not Propagating
**Symptom:** Assembly stages have different dimensions when they should be synced
**Root cause:** `assembly_group_id` not set on TagUnit, or sync properties not in `domain_config.yaml`
**Fix:** Ensure `assembly_group_id` is persisted on TagUnit; check `assembly.shared_properties` in domain_config.yaml
**File:** session_graph.py:318 (`upsert_tag`), domain_config.yaml

## 11. Per-Tag Airflow Reference (Multi-Size Bug)
**Symptom:** All tags get same airflow reference button regardless of size
**Root cause:** `_generate_airflow_options_from_graph()` uses `break` after first tag — only generates options for ONE size
**Fix:** Iterate ALL unique sizes, deduplicate by airflow value
**File:** retriever.py:2832

## 12. `import os` Scope Bug
**Symptom:** `UnboundLocalError: local variable 'os' referenced before assignment`
**Root cause:** A local `import os` inside a function makes Python treat `os` as local throughout the ENTIRE function
**Fix:** Move `import os` to module level, or use the import before any reference
**File:** Any file with function-scoped imports

## 13. Dual Endpoint Trap
**Symptom:** Button clicks don't trigger engine / lose state
**Root cause:** Turn 1 uses streaming endpoint, but clarification clicks used non-streaming endpoint (which has NO state management)
**Fix:** Route all graph-reasoning clicks through streaming path via `sendMessage(overrideMessage)`
**File:** frontend chat.tsx

## 14. JSON Truncation from Gemini
**Symptom:** Malformed JSON in LLM response, missing closing brackets
**Root cause:** Gemini hits `max_output_tokens` mid-object
**Fix:** `_repair_truncated_json()` closes open strings + brackets
**File:** retriever.py:2870
**Config:** Set `max_output_tokens=2048` (was 1024)

## 15. Backend Log Buffering
**Symptom:** print() statements in SSE streaming handlers don't appear in logs
**Root cause:** Python stdout buffering when running with output redirect
**Fix:** Use `PYTHONUNBUFFERED=1` when starting uvicorn
