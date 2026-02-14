# Fix Patterns — Where and How to Fix Each Bug Type

## Pattern 1: Wrong Clarification Button Values (e.g., wrong airflow suggestions)

**Root cause:** `_generate_airflow_options_from_graph()` in retriever.py:2832

**Current bug:** Uses `break` on line 2865 — only generates options for the FIRST tag with dimensions. Multi-tag queries (different sizes) get the same reference airflow for all tags.

**Fix pattern:**
```python
# WRONG: breaks after first tag
for tag in technical_state.tags.values():
    if tag.housing_width and tag.housing_height:
        ref = db_conn.get_reference_airflow_for_dimensions(tag.housing_width, tag.housing_height)
        options.append(...)
        break  # <-- BUG: all tags get same reference

# RIGHT: generate per-tag options
seen_airflows = set()
for tag_id, tag in technical_state.tags.items():
    if tag.housing_width and tag.housing_height:
        ref = db_conn.get_reference_airflow_for_dimensions(tag.housing_width, tag.housing_height)
        if ref and ref.get("reference_airflow_m3h"):
            ref_airflow = int(ref["reference_airflow_m3h"])
            if ref_airflow not in seen_airflows:
                seen_airflows.add(ref_airflow)
                label = ref.get("label", f"{tag.housing_width}x{tag.housing_height}")
                options.append({
                    "value": str(ref_airflow),
                    "description": f"{ref_airflow} m³/h (Reference for {label})",
                })
```

**Verification:** Test with multi-size query. Each unique size should get its own reference airflow button.

---

## Pattern 2: LLM Hallucinating Dimensions / Physics

**Root cause:** LLM generates text based on user's original query, NOT from graph-validated data.

**Where to fix:** `to_prompt_injection()` in universal_engine.py:225 or verdict_adapter.py

**Fix pattern:** Add explicit dimension data to the prompt injection so LLM reads from engine output, not from user text:

```python
# In to_prompt_injection(), add:
lines.append(f"VERIFIED DIMENSIONS FROM GRAPH:")
for tag_id, tag_data in self.tag_data.items():
    lines.append(f"  {tag_id}: Width={tag_data['width']}mm, Height={tag_data['height']}mm")
lines.append("Use ONLY these verified dimensions in your response. Do NOT repeat raw user dimensions.")
```

**Verification:** Check that LLM response uses graph-mapped dimensions (300x600) not user dimensions (305x610).

---

## Pattern 3: State Lost Between Turns

**Diagnosis:**
1. Check `get_project_state()` returns correct data (query Neo4j Layer 4)
2. Check `TechnicalState.from_dict()` correctly restores all fields
3. Check `resolved_params` are being persisted and restored

**Common causes:**
- `if graph_state.get("tags")` returns False for empty tags — use `if graph_state.get("tags") or graph_state.get("project")`
- `assembly_group` not being restored from `from_dict()`
- `detected_family` not falling back to Layer 4 on continuation turns

**Where to fix:** state.py:700 (`from_dict`) or session_graph.py:447 (`get_project_state`)

---

## Pattern 4: Assembly Not Triggered

**Diagnosis:**
1. Query `get_causal_rules_for_stressors()` — are there CRITICAL rules?
2. Check if stressor detection found the right stressors
3. Check if product has the demanded trait (would prevent veto → no assembly needed)
4. Query `get_dependency_rules_for_stressors()` — are DependencyRule nodes linked?

**Common causes:**
- Missing `EnvironmentalStressor -[:DEMANDS_TRAIT]-> PhysicalTrait` relationship
- DependencyRule not linked to the right stressor via `TRIGGERED_BY_STRESSOR`
- Stressor keywords missing from `keywords` property

**Where to fix:** Graph data (seed script or direct Cypher), NOT Python code.

---

## Pattern 5: Clarification Leak (asking for already-known param)

**The Triple Guard — check all 3:**

1. **Engine guard** (universal_engine.py): `check_missing_parameters()` checks `context.get(property_key)` and aliases. Ensure the param's `property_key` matches what's in `resolved_context`.

2. **Adapter guard** (verdict_adapter.py:959): `_map_clarifications()` returns `[]` when `verdict.has_installation_block`. Check if the block flag is set.

3. **Retriever guard** (retriever.py): `needs_clarification = False` when `suitability.is_suitable == False`. Check the boolean logic.

**Also check:**
- `pending_clarification` tracking — is it consumed after use?
- Key aliases: `property_key` in graph vs key in `resolved_context`

---

## Pattern 6: Wrong Product Selected / No Pivot

**Pipeline:** `detect_stressors()` → `evaluate_rules()` → veto check → pivot/assembly

**Diagnosis:**
1. Are the right stressors detected? (Check Application keywords, Environment detection)
2. Are the right rules loaded? (DEMANDS_TRAIT relationships)
3. Does the product have the demanded trait? (HAS_TRAIT)
4. Is the veto reason NEUTRALIZATION (triggers assembly) or MISSING_TRAIT (triggers pivot)?

**Where to fix:** Usually graph data — missing EXPOSES_TO, DEMANDS_TRAIT, or HAS_TRAIT relationships.

---

## Pattern 7: Wrong Module Count / Sizing

**Pipeline:** `compute_sizing_arrangement()` in universal_engine.py:1642

**Diagnosis:**
1. Is the correct DimensionModule selected? (explicit dims lock vs largest-fitting)
2. Is effective_airflow correct for this product+module? (CapacityRule + SizeProperty)
3. Are space constraints (`max_width_mm`, `max_height_mm`) passed correctly?

**Common bugs:**
- Explicit dimensions not locking: check `context.get(primary_axis.replace("_mm", ""))` mapping
- Wrong effective_airflow: missing SizeProperty nodes for module/family combination
- Overflow recalculation: stacked modules exceeding secondary constraint

---

## Pattern 8: Adding New Graph Data

When the fix requires new graph nodes/relationships:

1. Write a seed script in `backend/database/` following naming convention
2. Use ID prefixes: `APP_`, `FAM_`, `STRESSOR_`, `TRAIT_`, `IC_`, `GATE_`, `DEP_`, `HC_`, `DIM_`, `CAP_`
3. Run the seed script
4. Update `docs/current_schema.txt` if new node types/relationships added
5. Verify with diagnostic query

See the `graph-builder` skill for detailed patterns.
