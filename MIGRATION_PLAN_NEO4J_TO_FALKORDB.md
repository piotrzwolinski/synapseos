# Migration Plan: Neo4j → FalkorDB

> **Status**: Ready for implementation
> **Created**: 2026-02-18
> **Estimated scope**: ~400 lines of code changes across 5 core files + 15 utility scripts
> **Risk**: LOW — all Cypher query strings are compatible as-is, only the Python driver layer changes

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Cypher Compatibility Analysis](#2-cypher-compatibility-analysis)
3. [Phase 1: Python Driver Swap](#3-phase-1-python-driver-swap)
4. [Phase 2: Vector Search API Migration](#4-phase-2-vector-search-api-migration)
5. [Phase 3: Fulltext Search API Migration](#5-phase-3-fulltext-search-api-migration)
6. [Phase 4: Index Creation Migration](#6-phase-4-index-creation-migration)
7. [Phase 5: Utility Scripts Migration](#7-phase-5-utility-scripts-migration)
8. [Phase 6: Test Validation](#8-phase-6-test-validation)
9. [File-by-File Change Inventory](#9-file-by-file-change-inventory)
10. [Rollback Strategy](#10-rollback-strategy)

---

## 1. Executive Summary

### What stays the same (no changes needed)

FalkorDB supports the openCypher standard and **all** of these Neo4j features we use:

| Feature | Usage Count | Status |
|---------|-------------|--------|
| `FOREACH` | 6 usages | ✅ Supported |
| `MERGE ... ON CREATE SET / ON MATCH SET` | 3 usages | ✅ Supported |
| `timestamp()` | 14 usages | ✅ Supported |
| `COALESCE()` | 50+ usages | ✅ Supported |
| `CASE WHEN` | 15+ usages | ✅ Supported |
| `WITH` clauses | 100+ usages | ✅ Supported |
| `UNWIND` | 4 usages | ✅ Supported |
| List comprehensions `[x IN list WHERE ...]` | 9 usages | ✅ Supported |
| `toInteger()`, `toFloat()`, `toString()` | 5+ usages | ✅ Supported |
| `ceil()`, `floor()`, `abs()` | Multiple | ✅ Supported |
| APOC procedures | 0 usages | N/A (not used) |

**This means ~300 out of ~317 `session.run()` call sites keep the SAME Cypher strings — only the Python driver wrapper changes.**

> The codebase has **317 `session.run()` calls** across 21 files (164 in `database.py`, 38 in seed scripts, ~100 in utility scripts, rest scattered). Only ~13 call sites (7 vector + 6 fulltext) need Cypher string changes.

### What must change

| Change | Files | Lines |
|--------|-------|-------|
| Python driver: `neo4j` → `falkordb` | 2 core + 15 scripts | ~200 lines |
| Vector search API: `db.index.vector.*` → `db.idx.vector.*` | 1 file | ~30 lines |
| Fulltext search API: `db.index.fulltext.*` → `db.idx.fulltext.*` | 1 file | ~20 lines |
| Vector index creation DDL | 3 files | ~15 lines |
| Fulltext index creation DDL | 1 file | ~10 lines |
| Connection string & config | 2 files | ~10 lines |
| Result object API | 2 core files | ~120 lines |

---

## 2. Cypher Compatibility Analysis

### 2.1 FOREACH — NO CHANGES NEEDED ✅

All 6 FOREACH usages use the `FOREACH (_ IN CASE WHEN cond THEN [1] ELSE [] END | action)` pattern. FalkorDB supports this per [docs](https://docs.falkordb.com/cypher/foreach.html).

**Locations (for reference only, no changes):**
- `database.py:1235` — `infer_knowledge_candidate()`
- `database.py:2459` — `delete_learned_rule()` (1st)
- `database.py:2464` — `delete_learned_rule()` (2nd)
- `session_graph.py:157` — `lock_material()`
- `session_graph.py:181` — `set_detected_family()`
- `session_graph.py:451` — `upsert_tag()` DimensionModule link

### 2.2 ON CREATE SET — NO CHANGES NEEDED ✅

FalkorDB MERGE supports ON CREATE SET and ON MATCH SET per [docs](https://docs.falkordb.com/cypher/merge.html).

**Locations (for reference only):**
- `database.py:1227-1231` — `infer_knowledge_candidate()`
- `database.py:1320-1324` — verified source creation
- `database.py:2301-2324` — learned rules (Keyword, Requirement)

### 2.3 timestamp() — NO CHANGES NEEDED ✅

FalkorDB supports `timestamp()` as a scalar function per [docs](https://docs.falkordb.com/cypher/functions.html). Returns milliseconds since epoch.

**Locations (for reference only):**
- `session_graph.py` — 13 usages (ensure_session, set_project, lock_material, set_detected_family, set_pending_clarification, set_accessories, set_assembly_group, set_resolved_params, set_vetoed_families, store_turn ×2, upsert_tag)
- `database.py:4277` — `submit_expert_review()`

---

## 3. Phase 1: Python Driver Swap

**This is the biggest change.** Neo4j uses the `neo4j` Python package with a `GraphDatabase.driver()` / `session.run()` pattern. FalkorDB uses the `falkordb` package with a `FalkorDB()` / `graph.query()` pattern.

### 3.1 Package swap

```diff
# requirements.txt
- neo4j>=5.0
+ falkordb>=1.4.0
+ redis>=5.0  # FalkorDB uses Redis protocol
```

### 3.2 Connection configuration

FalkorDB uses Redis protocol (host:port) instead of Bolt URIs.

```diff
# Environment variables
- NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
- NEO4J_USER=neo4j
- NEO4J_PASSWORD=secret
+ FALKORDB_HOST=localhost       # or cloud hostname
+ FALKORDB_PORT=6379            # Redis port
+ FALKORDB_PASSWORD=secret      # optional
+ FALKORDB_GRAPH=synapse        # graph name (replaces database name)
```

### 3.3 Core: `backend/database.py` — Neo4jConnection class

This is the main file. 5,300 lines, 132 `driver.session()` calls, 164 `session.run()` calls, 55 `.single()` calls, 3 `.peek()` calls.

**Strategy**: Create a thin adapter layer inside `Neo4jConnection.__init__()` so that all 92 methods keep working with minimal changes.

#### 3.3.1 Constructor change

```python
# BEFORE (Neo4j)
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired

class Neo4jConnection:
    def __init__(self, uri, user, password, database="neo4j"):
        self.driver = GraphDatabase.driver(
            uri, auth=(user, password),
            max_connection_lifetime=3600,
            max_connection_pool_size=50,
            connection_acquisition_timeout=30,
            keep_alive=True,
        )
        self.database = database

# AFTER (FalkorDB)
from falkordb import FalkorDB

class Neo4jConnection:  # Keep class name for backward compat
    def __init__(self, host, port, password=None, graph_name="synapse"):
        self._fdb = FalkorDB(host=host, port=port, password=password)
        self._graph = self._fdb.select_graph(graph_name)
        self.database = graph_name  # backward compat for session_graph.py
```

#### 3.3.2 Query execution pattern change

Every method in `database.py` follows this pattern:

```python
# BEFORE (Neo4j) — appears 132 times
with self.driver.session(database=self.database) as session:
    result = session.run(cypher, params)
    record = result.single()
    return record["field"] if record else None

# AFTER (FalkorDB)
result = self._graph.query(cypher, params)
if result.result_set and len(result.result_set) > 0:
    return result.result_set[0][0]  # positional access
return None
```

**CRITICAL DIFFERENCE**: FalkorDB returns `result.result_set` as a list of lists (positional), NOT a list of dicts (named). You need to access by column index, not by key name.

#### 3.3.3 Helper methods to minimize changes

Add these helper methods to `Neo4jConnection` to keep method bodies as similar as possible:

```python
def _query(self, cypher: str, params: dict = None) -> list[dict]:
    """Execute read query, return list of dicts (Neo4j-compatible shape)."""
    result = self._graph.ro_query(cypher, params or {})
    if not result.result_set:
        return []
    # Convert positional results to named dicts using header
    headers = result.header
    return [
        {h[1]: row[i] for i, h in enumerate(headers)}
        for row in result.result_set
    ]

def _query_single(self, cypher: str, params: dict = None) -> dict | None:
    """Execute read query, return first row as dict or None."""
    rows = self._query(cypher, params)
    return rows[0] if rows else None

def _write(self, cypher: str, params: dict = None) -> list[dict]:
    """Execute write query, return list of dicts."""
    result = self._graph.query(cypher, params or {})
    if not result.result_set:
        return []
    headers = result.header
    return [
        {h[1]: row[i] for i, h in enumerate(headers)}
        for row in result.result_set
    ]
```

#### 3.3.4 Method-by-method conversion pattern

Each of the 92 methods follows ONE of these patterns:

**Pattern A: Single value (55 methods)**
```python
# BEFORE
with self.driver.session(database=self.database) as session:
    result = session.run(cypher, params)
    record = result.single()
    return record["count"] if record else 0

# AFTER
row = self._query_single(cypher, params)
return row["count"] if row else 0
```

**Pattern B: List of records (35 methods)**
```python
# BEFORE
with self.driver.session(database=self.database) as session:
    result = session.run(cypher, params)
    return [dict(record) for record in result]

# AFTER
return self._query(cypher, params)
```

**Pattern C: Write + ignore result (12 methods)**
```python
# BEFORE
with self.driver.session(database=self.database) as session:
    session.run(cypher, params)

# AFTER
self._write(cypher, params)
```

**Pattern D: Peek check (3 methods)**
```python
# BEFORE
with self.driver.session(database=self.database) as session:
    result = session.run(cypher, params)
    return dict(result.single()) if result.peek() else {}

# AFTER
row = self._query_single(cypher, params)
return dict(row) if row else {}
```

### 3.4 Core: `backend/logic/session_graph.py`

This file uses `self.db.driver.session()` directly in 2 places (`_run_query` and `_run_write`).

```python
# BEFORE
def _run_query(self, cypher: str, params: dict = None) -> list:
    with self.db.driver.session(database=self.db.database) as session:
        result = session.run(cypher, params or {})
        return [record.data() for record in result]

def _run_write(self, cypher: str, params: dict = None) -> None:
    with self.db.driver.session(database=self.db.database) as session:
        session.run(cypher, params or {})

# AFTER — delegate to database.py helper methods
def _run_query(self, cypher: str, params: dict = None) -> list:
    return self.db._query(cypher, params)

def _run_write(self, cypher: str, params: dict = None) -> None:
    self.db._write(cypher, params)
```

### 3.5 Connection initialization: `backend/main.py`

```python
# BEFORE
db = Neo4jConnection(
    uri=os.environ["NEO4J_URI"],
    user=os.environ["NEO4J_USER"],
    password=os.environ["NEO4J_PASSWORD"],
)

# AFTER
db = Neo4jConnection(
    host=os.environ["FALKORDB_HOST"],
    port=int(os.environ.get("FALKORDB_PORT", 6379)),
    password=os.environ.get("FALKORDB_PASSWORD"),
    graph_name=os.environ.get("FALKORDB_GRAPH", "synapse"),
)
```

### 3.6 Exception handling

```python
# BEFORE
from neo4j.exceptions import ServiceUnavailable, SessionExpired

# AFTER
from redis.exceptions import ConnectionError, TimeoutError
# Map: ServiceUnavailable → ConnectionError, SessionExpired → TimeoutError
```

---

## 4. Phase 2: Vector Search API Migration

### 4.1 API difference

| | Neo4j | FalkorDB |
|---|---|---|
| **Query** | `CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)` | `CALL db.idx.vector.queryNodes($label, $attribute, $top_k, vecf32($embedding))` |
| **Yield** | `YIELD node, score` | `YIELD node, score` |
| **Parameters** | Index name, k, raw list | Label, attribute, k, `vecf32()` wrapped |

### 4.2 Changes in `backend/database.py`

**7 vector search call sites to change:**

#### 4.2.1 `vector_search_concepts()` (line ~376)
```python
# BEFORE
cypher = """
CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
YIELD node, score
RETURN node.name AS concept, node.description AS description, score
"""
params = {"index_name": "concept_embeddings", "top_k": k, "embedding": embedding}

# AFTER
cypher = """
CALL db.idx.vector.queryNodes('Concept', 'embedding', $top_k, vecf32($embedding))
YIELD node, score
RETURN node.name AS concept, node.description AS description, score
"""
params = {"top_k": k, "embedding": embedding}
```

#### 4.2.2 `hybrid_retrieval()` (line ~738)
```python
# BEFORE
CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
YIELD node as concept, score WHERE score > $min_score

# AFTER
CALL db.idx.vector.queryNodes('Concept', 'embedding', $top_k, vecf32($embedding))
YIELD node as concept, score WHERE score > $min_score
```

#### 4.2.3 `check_safety_risks()` (lines ~805, ~892)
Same pattern — replace `db.index.vector.queryNodes($index_name, ...)` with `db.idx.vector.queryNodes('Concept', 'embedding', ...)`.

#### 4.2.4 `get_semantic_rules()` (line ~2371)
```python
# BEFORE
CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
YIELD node AS keyword, score

# AFTER
CALL db.idx.vector.queryNodes('Keyword', 'embedding', $top_k, vecf32($embedding))
YIELD node AS keyword, score
```

#### 4.2.5 `vector_search_applications()` (line ~2575)
```python
# BEFORE
CALL db.index.vector.queryNodes('application_embeddings', $top_k, $embedding)
YIELD node AS app, score

# AFTER
CALL db.idx.vector.queryNodes('Application', 'embedding', $top_k, vecf32($embedding))
YIELD node AS app, score
```

### 4.3 Mapping table: Neo4j index names → FalkorDB (label, attribute)

| Neo4j Index Name | FalkorDB Label | FalkorDB Attribute |
|---|---|---|
| `concept_embeddings` | `Concept` | `embedding` |
| `application_embeddings` | `Application` | `embedding` |
| `learned_rules_embeddings` | `Keyword` | `embedding` |

---

## 5. Phase 3: Fulltext Search API Migration

### 5.1 API difference

| | Neo4j | FalkorDB |
|---|---|---|
| **Query** | `CALL db.index.fulltext.queryNodes("index_name", $term)` | `CALL db.idx.fulltext.queryNodes('Label', $term)` |
| **Yield** | `YIELD node, score` | `YIELD node, score` |
| **Key diff** | Named index | Label name |

### 5.2 Changes in `backend/database.py`

**6 fulltext search call sites to change:**

| Method | Line | Neo4j Index | FalkorDB Label |
|---|---|---|---|
| `search_by_project_name()` | ~1137 | `project_fulltext` | `Project` |
| `search_product_variants()` | ~1912 | `product_variant_fulltext` | `ProductVariant` |
| `configuration_graph_search()` | ~2094 | `product_variant_fulltext` | `ProductVariant` |
| `configuration_graph_search()` | ~2142 | `filter_cartridge_fulltext` | `FilterCartridge` |
| `configuration_graph_search()` | ~2167 | `filter_consumable_fulltext` | `FilterConsumable` |
| `configuration_graph_search()` | ~2195 | `material_spec_fulltext` | `MaterialSpec` |

**Pattern:**
```python
# BEFORE
CALL db.index.fulltext.queryNodes("product_variant_fulltext", $term)
YIELD node AS pv, score

# AFTER
CALL db.idx.fulltext.queryNodes('ProductVariant', $term)
YIELD node AS pv, score
```

### 5.3 Mapping table: Neo4j fulltext index names → FalkorDB labels

| Neo4j Index Name | FalkorDB Label | Properties Indexed |
|---|---|---|
| `project_fulltext` | `Project` | `name` |
| `product_variant_fulltext` | `ProductVariant` | `code`, `name`, `description` |
| `filter_cartridge_fulltext` | `FilterCartridge` | `code`, `name` |
| `filter_consumable_fulltext` | `FilterConsumable` | `code`, `name` |
| `material_spec_fulltext` | `MaterialSpec` | `code`, `name` |

---

## 6. Phase 4: Index Creation Migration

### 6.1 Vector index creation

```python
# BEFORE (Neo4j DDL)
CREATE VECTOR INDEX {index_name} IF NOT EXISTS
FOR (c:Concept) ON (c.embedding)
OPTIONS {indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
}}

# AFTER (FalkorDB DDL)
CREATE VECTOR INDEX FOR (c:Concept) ON (c.embedding)
OPTIONS {dimension: 768, similarityFunction: 'cosine'}
```

**Key differences:**
- No `IF NOT EXISTS` (check existence first or use procedure)
- `indexConfig` wrapper removed
- `vector.dimensions` → `dimension`
- `vector.similarity_function` → `similarityFunction`

**Files to change:**
- `database.py:352` — `create_vector_index()`
- `database.py:2258` — `create_learned_rules_index()`
- `database/update_embeddings.py:74` — `create_vector_indexes()`

### 6.2 Fulltext index creation

```python
# BEFORE (Neo4j DDL)
CREATE FULLTEXT INDEX product_variant_fulltext IF NOT EXISTS
FOR (n:ProductVariant) ON EACH [n.code, n.name, n.description]

# AFTER (FalkorDB procedure)
CALL db.idx.fulltext.createNodeIndex('ProductVariant', 'code', 'name', 'description')
```

**Files to change:**
- `database/apply_indexes.py:57` — index creation loop

### 6.3 Regular (B-tree) index creation

```python
# BEFORE (Neo4j)
CREATE INDEX session_last_active IF NOT EXISTS FOR (s:Session) ON (s.last_active)

# AFTER (FalkorDB) — same syntax but without IF NOT EXISTS
CREATE INDEX FOR (s:Session) ON (s.last_active)
```

**Files to change:**
- `database.py:4139-4144` — `ensure_indexes()`
- `database/apply_indexes.py:69` — index loop
- `database/init_graph.py:52-55, 119-122` — schema setup
- `database/mh_hvac_traits.py:929-939` — `create_indexes()`

> **Note**: FalkorDB may silently succeed if index already exists. Test this behavior and add `try/except` if needed.

---

## 7. Phase 5: Utility Scripts Migration

These are one-time seeding/migration scripts in `backend/database/`. They each instantiate their own `GraphDatabase.driver()` and are run manually.

### Scripts requiring driver swap (15 files):

| Script | Driver Calls | Priority |
|---|---|---|
| `mh_hvac_traits.py` | 1 (line 1060) | HIGH — main seed script |
| `seed_hvac.py` | 1 (line 663) | HIGH — initial data |
| `init_graph.py` | 1 (line 97) | HIGH — schema init |
| `apply_indexes.py` | 1 (line 19) | HIGH — index creation |
| `update_embeddings.py` | 1 (line 277) | MEDIUM — vector embedding |
| `backup_graph.py` | 1 (line 101) | MEDIUM — backup utility |
| `fix_inventory_logic.py` | 1 (line 221) | LOW — one-time fix |
| `add_accessory_compatibility.py` | 1 (line 220) | LOW — one-time add |
| `add_catalog_enrichment.py` | 1 (line 397) | LOW — one-time add |
| `add_physics_mitigation.py` | 1 (line 335) | LOW — one-time add |
| `add_powder_coating.py` | 1 (line 137) | LOW — one-time add |
| `add_variable_features.py` | 1 (line 187) | LOW — one-time add |
| `add_gdp_auto_resolve.py` | 1 (line 95) | LOW — one-time add |

**Each script follows the same pattern:**
```python
# BEFORE
driver = GraphDatabase.driver(uri, auth=(user, password))
with driver.session(database="neo4j") as session:
    session.run(cypher, params)

# AFTER
from falkordb import FalkorDB
fdb = FalkorDB(host=host, port=port, password=password)
graph = fdb.select_graph(graph_name)
graph.query(cypher, params)
```

**Recommendation**: Create a shared utility function `get_graph_connection()` that all scripts use, so the connection logic is in one place.

### Additional files:

| File | Change |
|---|---|
| `load_graph_schema.py` | 2 driver instantiations (lines 78, 157) |
| `logic/engine_adapter.py` | 1 driver instantiation (line 359) — used for FalkorDB reasoning engine |
| `bulk_offer.py` | Uses `self.db.driver.session()` — 7 calls, same pattern as database.py |

---

## 8. Phase 6: Test Validation

### 8.1 Existing test suite (305 tests)

The regression test suite built for this migration covers ALL critical paths:

```bash
cd backend && ./venv/bin/python -m pytest tests/ -v
# Expected: 305 passed, 32 skipped (live DB), 0 failures
```

| Test File | Tests | What It Guards |
|---|---|---|
| `test_engine_pipeline.py` | 36 | Trait engine logic with mocked DB |
| `test_scribe_unit.py` | 18 | Intent extraction (LLM mock) |
| `test_verdict_adapter.py` | 14 | EngineVerdict → Report conversion |
| `test_session_graph_unit.py` | 26 | Layer 4 state management + FOREACH patterns |
| `test_api_endpoints.py` | 14 | HTTP contract (FastAPI + auth) |
| `test_vector_fulltext.py` | 12 | Vector/fulltext consumers (mocked) |
| `test_database_contract.py` | 32 | Live DB return shapes (skipped without DB) |
| `test_state.py` | 16 | TechnicalState serialization |

### 8.2 Migration validation steps

After each phase, run:

```bash
# 1. Unit tests (always)
./venv/bin/python -m pytest tests/ -v --tb=short

# 2. Live DB contract tests (after FalkorDB is running)
FALKORDB_HOST=localhost FALKORDB_PORT=6379 \
  ./venv/bin/python -m pytest tests/test_database_contract.py -v

# 3. End-to-end smoke test
curl -X POST http://localhost:8000/consult/deep-explainable/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "I need a 600x600 filter for kitchen ventilation", "session_id": "migration_test"}'

# 4. Full regression (8 scenarios)
# Use /test-hvac skill
```

### 8.3 Key test expectations

The `conftest.py` mock_db fixture defines the **contract** (return shapes) that any DB backend must satisfy. After migration, the live `test_database_contract.py` tests must pass — they verify that FalkorDB returns data in the same shapes as Neo4j.

---

## 9. File-by-File Change Inventory

### Core files (MUST change)

| File | Lines | Changes | Effort |
|---|---|---|---|
| `backend/database.py` | 5,316 | Driver swap, helper methods, 132 session→query rewrites, 7 vector API, 6 fulltext API, index DDL | **LARGE** |
| `backend/logic/session_graph.py` | 843 | `_run_query`/`_run_write` delegate to db helpers (2 methods) | **SMALL** |
| `backend/main.py` | ~200 | Connection init, env vars | **SMALL** |
| `backend/requirements.txt` | 1 | `neo4j` → `falkordb` + `redis` | **TRIVIAL** |
| `.env` / config | — | Connection vars | **TRIVIAL** |

### Utility scripts (CAN change later)

| File | Changes | Priority |
|---|---|---|
| `database/mh_hvac_traits.py` | Driver swap | After core works |
| `database/seed_hvac.py` | Driver swap | After core works |
| `database/init_graph.py` | Driver swap + index DDL | After core works |
| `database/apply_indexes.py` | Driver swap + index DDL | After core works |
| `database/update_embeddings.py` | Driver swap + vector DDL | After core works |
| 10 more `database/add_*.py` | Driver swap | LOW priority |
| `load_graph_schema.py` | Driver swap | After core works |
| `logic/engine_adapter.py` | Driver swap | After core works |
| `bulk_offer.py` | Session pattern swap | After core works |

### Files with ZERO changes

| File | Why |
|---|---|
| `backend/logic/universal_engine.py` | Pure Python logic, no DB calls |
| `backend/logic/verdict_adapter.py` | Pure Python logic, no DB calls |
| `backend/logic/scribe.py` | LLM calls only, no DB calls (except `_build_env_app_mapping` which calls db methods) |
| `backend/logic/state.py` | Pure Python dataclass |
| `backend/logic/graph_reasoning.py` | Pure Python dataclasses |
| `backend/retriever.py` | Calls db methods (not driver directly) — works if db methods keep same signatures |
| `backend/chat.py` | Calls db methods — works if signatures unchanged |
| `backend/auth.py` | No DB calls |
| `backend/config_loader.py` | No DB calls |
| `frontend/**` | No backend changes |
| All test files | Mock-based, no real DB |

---

## 10. Rollback Strategy

### Pre-migration checklist

- [ ] Export full Neo4j graph dump: `neo4j-admin dump --database=neo4j --to=backup.dump`
- [ ] Tag git: `git tag pre-falkordb-migration`
- [ ] Verify all 305 tests pass on current Neo4j setup
- [ ] Run `/test-hvac` full regression on current setup
- [ ] Document current Neo4j Aura connection details

### Data migration

FalkorDB uses a different storage format. Options:
1. **Re-seed from scripts** — Run `mh_hvac_traits.py` + other seed scripts against FalkorDB (cleanest)
2. **Cypher export/import** — Export all nodes/relationships as Cypher CREATE statements, replay against FalkorDB
3. **APOC export** — Not applicable (no APOC in FalkorDB)

**Recommendation**: Option 1 (re-seed). The seed scripts are the source of truth and will exercise the new driver.

### Rollback

If migration fails:
1. `git checkout pre-falkordb-migration`
2. Restore Neo4j Aura connection
3. All data is still in Neo4j Aura (read-only during migration)

---

## Implementation Order

```
Phase 1a: Add falkordb to requirements.txt, create helper methods in database.py
Phase 1b: Convert _run_query/_run_write in session_graph.py (2 lines)
Phase 1c: Convert connection init in main.py
Phase 1d: Convert 92 methods in database.py (mechanical, pattern-based)
    → Run tests after each batch of ~10 methods
Phase 2:  Vector search API (7 call sites in database.py)
Phase 3:  Fulltext search API (6 call sites in database.py)
Phase 4:  Index creation DDL (4 files)
Phase 5:  Utility scripts (15 files, low priority)
Phase 6:  Full regression testing
```

**Each phase is independently testable.** The mock-based test suite (305 tests) validates Python logic. The live contract tests validate FalkorDB compatibility.
