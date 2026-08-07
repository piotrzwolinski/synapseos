# Diagnosis: Non-deterministic clarification option count

**Date:** 2026-08-07
**Status:** ✅ FIXED (2026-08-07). Root cause below was refined during implementation — see "ACTUAL ROOT CAUSE & FIX" at the bottom. The original hypothesis (LLM free-text contamination) was a *symptom amplifier*, not the root cause.

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

---

## ACTUAL ROOT CAUSE & FIX (2026-08-07)

Empirical + graph inspection revealed the true cause is a **graph data-model defect**, not LLM contamination (the LLM free-text path only amplified the visible symptom):

### The defect
- A **malformed `VariableFeature` node** (internal id 791; `parameter_name = NULL`, `feature_name = NULL`) was shared by `FAM_GDC` **and** `FAM_GDC_FLEX` and linked `[OPT_GDC_LEN_750, OPT_GDC_LEN_900, OPT_POLIS]` via `HAS_OPTION`.
- Because its `parameter_name` is NULL, `check_variable_features` computes an empty `param_key` that never matches a resolved param → it **always** surfaced as an unresolved clarification, dragging `OPT_POLIS` (an after-filter rail) into the housing-length options.
- `FAM_GDC_FLEX` had **no proper `housing_length` feature of its own** — it depended entirely on this malformed node (`FAM_GDC` also had the correct `VF_GDC_LENGTH`, so 791 was a duplicate for it).
- **`ACC_POLIS` is `INCOMPATIBLE_WITH` FAM_GDC / FAM_GDC_FLEX** (only `HAS_COMPATIBLE_ACCESSORY` with GDB/GDMI). So Polis was being offered exactly for the families it is incompatible with, while GDB/GDMI (where it is valid) never had it selectable.
- The `HAS_OPTION → OPT_POLIS` edge was **load-bearing**: `database.get_option_geometric_constraints` traversed `(:VariableFeature)-[:HAS_OPTION]->(:FeatureOption)` to find Polis's `min_required_housing_length=900`. So it could not simply be deleted.

The 2-vs-3 non-determinism = unstable `collect()` ordering + LLM free-text option authoring occasionally dropping the trailing (Polis) item. Removing Polis at the source makes the count deterministic.

### The fix (accessory model)
Migration: `backend/database/fix_polis_length_feature.py`
1. Added a proper `housing_length` VariableFeature `VF_GDC_FLEX_LENGTH` for `FAM_GDC_FLEX` (options 750/900).
2. Copied the geometric constraint (`min_required_housing_length=900` + physics text) onto `ACC_POLIS`.
3. Deleted the malformed node 791 (identified structurally as the NULL-param VariableFeature linking `OPT_POLIS`, not by unstable id).

Code: `backend/database.py` `get_option_geometric_constraints` — added a `UNION` branch that reads space-consuming **accessories** via `HAS_COMPATIBLE_ACCESSORY` (matched by selected options, `min_required_housing_length IS NOT NULL`). Polis's 900mm constraint now actually fires for GDB/GDMI (where it is compatible); GDC/GDC_FLEX correctly return nothing here (handled by the accessory-incompatibility validator).

Seed scripts made consistent so re-seeding never reintroduces the bug:
- `backend/database/apply_geometric_constraints.py` — now sets the constraint on `ACC_POLIS`; removed the harmful `HAS_OPTION` link + the incompatibility-with-750 step.
- `backend/database/update_polis_constraint.cypher` — same; constraint on `ACC_POLIS`, no length-feature link.

### Verification
- Same query run **5×** through the Graph Reasoning stream endpoint → **always exactly 2 options (750mm, 900mm), no Polis** (was 3/5 with Polis before the fix).
- `get_option_geometric_constraints('GDMI', ['polis'])` → constraint returned (min 900); `('GDC', ['polis'])` → `[]` (deferred to compatibility validator).
- Full regression: run `/test-hvac` (8 tests) — user-invoked.

### Sibling issue (out of scope, left untouched)
A second malformed NULL-identity VariableFeature (id 790) exists for `FAM_GDMI` linking GDMI length options (no Polis). Same defect class; does not cause the Polis bug. Should be cleaned up separately (verify GDMI has a proper `housing_length` feature first).
