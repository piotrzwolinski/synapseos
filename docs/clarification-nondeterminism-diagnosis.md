# Diagnosis: Non-deterministic clarification option count

**Date:** 2026-08-07
**Status:** Diagnosed, NOT yet fixed. This doc is the return point before implementing the fix.

## Symptom

Identical query produces clarification questions with a **different number of options** across runs.

Query: `I need a GDC-FLEX carbon housing 600x600 for indoor ventilation. FZ material, 1750 m³/h. How many carbon cartridges does it hold?`

- Run A: housing-length clarification shows **2 options** (750mm, 900mm)
- Run B: housing-length clarification shows **3 options** (750mm, 900mm, **"Polis (After-filter Rail)"**)

Core numeric answer ("14 cartridges", single module, 1750 m³/h) is identical in both — that part comes from the engine, not LLM prose.

## Root cause

The clarification option list is **authored by the LLM (Gemini) as free text**, not emitted as a structured field from the graph.

1. **"Polis" is NOT a housing-length option.** In the graph, GDC family has exactly two housing-length `FeatureOption` nodes: `OPT_GDC_LEN_750`, `OPT_GDC_LEN_900` (seeded in `backend/database/add_variable_features.py:137-144`). "Polis (After-filter Rail)" is an `Accessory` node `ACC_POLIS` (`min_housing_length=900`), seeded in `backend/database/add_accessory_compatibility.py:55-60`.

2. **Both get injected into the same text prompt, in adjacent sections:**
   - `backend/logic/universal_engine.py:560-574` — "MISSING CONFIGURATION PARAMETERS" section lists 750/900 as text (`mp.options[:5]`).
   - `backend/logic/universal_engine.py:576-593` — separate "ACCESSORY COMPATIBILITY" section injects Polis.

3. **Gemini synthesizes the final user-facing text** at `backend/retriever.py:2908-2916` (`temperature=0.0`, `max_output_tokens=4096`). Even at temp 0, Gemini is not bit-deterministic (MoE routing / batching). Because the options are free text the model reassembles — with a compatible accessory sitting adjacent in the prompt — it non-deterministically folds Polis into the housing-length option list.

## Contributing factor: non-deterministic Cypher ordering

Several `collect()` queries lack `ORDER BY` on the option nodes, so FalkorDB returns options in unspecified order, nudging the LLM toward including/dropping the trailing item:

- `backend/database.py:2846-2867` (`get_variable_features`) — `collect({...}) AS options`, no `ORDER BY o.*` (only `ORDER BY f.feature_name`).
- `backend/logic/reasoning_engine.py:587-601` (`get_discriminators_for_items`) — no `ORDER BY o.*` (only `ORDER BY d.priority`).
- `backend/database.py:3511-3526` (accessory compatibility) — `collect(DISTINCT other_acc.name)`, no `ORDER BY`.

Secondary truncation vectors: `max_output_tokens=4096` + `_repair_truncated_json()` (`retriever.py:2522-2601`) can silently drop trailing array elements; `mp.options[:5]` (`universal_engine.py:569`) and `[:N]` caps combined with unordered `collect()` = non-deterministic *set*, not just order.

## Planned fix (in priority order)

1. **Primary:** Stop letting Gemini author the option list for structured clarifications. Emit graph options as a structured field to the frontend (the `options` path exists at `engine_adapter.py:221-231` / `reasoning_engine.py:157`) instead of free text the model rewrites.
2. **Prompt isolation:** Do not place the "ACCESSORY COMPATIBILITY" section adjacent to parameter options in the same prompt, or clearly label accessories as not being length options.
3. **Graph determinism (defense-in-depth):** Add `ORDER BY o.value` (or a `sort_order` property) inside/after the `collect()` in `database.py:2846-2867`, `reasoning_engine.py:592-599`, and `database.py:3526`.

## Regression check before merging

Run `/test-hvac` (8-test regression runner) — the fix touches the clarification render path.

## Key files

- `backend/logic/universal_engine.py`
- `backend/logic/verdict_adapter.py`
- `backend/logic/reasoning_engine.py`
- `backend/retriever.py`
- `backend/database.py`
- `backend/database/add_variable_features.py`
- `backend/database/add_accessory_compatibility.py`
