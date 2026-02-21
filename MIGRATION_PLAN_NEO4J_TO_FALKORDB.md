# Migration Plan: Neo4j → FalkorDB (v2 — Verified)

> **Status**: Ready for implementation
> **Created**: 2026-02-18 | **Revised**: 2026-02-19
> **Risk**: MEDIUM — Cypher is mostly compatible, but constraints, indexes, vector/fulltext APIs, and the Python driver all differ significantly

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Verified Cypher Compatibility](#2-verified-cypher-compatibility)
3. [Breaking Changes — What MUST Change](#3-breaking-changes--what-must-change)
4. [Phase 0: FalkorDB Setup & Data Migration](#4-phase-0-falkordb-setup--data-migration)
5. [Phase 1: Python Driver Swap (database.py)](#5-phase-1-python-driver-swap-databasepy)
6. [Phase 2: Session Graph & Adapter Layer](#6-phase-2-session-graph--adapter-layer)
7. [Phase 3: Vector Search API](#7-phase-3-vector-search-api)
8. [Phase 4: Fulltext Search API](#8-phase-4-fulltext-search-api)
9. [Phase 5: Index & Constraint DDL](#9-phase-5-index--constraint-ddl)
10. [Phase 6: Cypher Rewrites (Edge Cases)](#10-phase-6-cypher-rewrites-edge-cases)
11. [Phase 7: Utility Scripts](#11-phase-7-utility-scripts)
12. [Phase 8: bulk_offer.py](#12-phase-8-bulk_offerpy)
13. [Phase 9: Test Validation](#13-phase-9-test-validation)
14. [FalkorDB Cloud — Hosting Decision](#14-falkordb-cloud--hosting-decision)
15. [File-by-File Change Inventory](#15-file-by-file-change-inventory)
16. [Rollback Strategy](#16-rollback-strategy)
17. [Implementation Order](#17-implementation-order)

---

## 1. Executive Summary

### Verified findings (from FalkorDB official docs, Feb 2026)

The previous plan made optimistic assumptions. This revision is based on verified FalkorDB documentation and a thorough codebase audit.

**Codebase scope (audited):**
- `database.py`: 5,350 lines, **140 class methods**, **165 `session.run()` calls**, 98 inner `_query()` closures
- `session_graph.py`: 2 direct driver access methods (`_run_query`, `_run_write`)
- `bulk_offer.py`: 7 direct `driver.session()` calls (bypasses Neo4jConnection)
- `load_graph_schema.py`: 2 driver instantiations
- `database/*.py` scripts: 12 scripts, each with own `GraphDatabase.driver()` call
- `logic/engine_adapter.py`: 1 factory function with driver creation

### What's compatible (no Cypher changes needed)

| Feature | Usage Count | FalkorDB Status | Source |
|---------|-------------|-----------------|--------|
| `FOREACH` | 3 | ✅ [Supported](https://docs.falkordb.com/cypher/foreach.html) |
| `MERGE ON CREATE SET / ON MATCH SET` | 7 total | ✅ [Supported](https://docs.falkordb.com/cypher/merge.html) |
| `timestamp()` | 14 | ✅ [Supported](https://docs.falkordb.com/cypher/functions.html) |
| `COALESCE()` | ~30 | ✅ Supported |
| `CASE WHEN` | 15+ | ✅ Supported |
| `WITH` | 100+ | ✅ Supported |
| `UNWIND` | 2 | ✅ Supported |
| `OPTIONAL MATCH` | ~152 | ✅ Supported |
| `UNION ALL` | 6 | ✅ Supported |
| List comprehensions | 9 | ✅ Supported |
| `toInteger()`, `toFloat()`, `toString()` | 5+ | ✅ Supported |
| `ceil()`, `floor()`, `abs()` | Multiple | ✅ Supported |
| Variable-length paths `*0..5` | 1 | ✅ Supported |

**This means ~150 of ~165 `session.run()` call sites keep the SAME Cypher strings.** Only ~15 call sites need Cypher string changes (vector, fulltext, indexes, constraints, a few edge cases).

### What MUST change

| Change | Scope | Risk |
|--------|-------|------|
| Python driver: `neo4j` → `falkordb` | All DB access | **HIGH** — different result format (list-of-lists vs named dicts) |
| Result adaptation: `dict(record)` → helper method | 85 return statements | **HIGH** — most labor-intensive change |
| Vector search API: `db.index.vector.*` → `db.idx.vector.*` | 6 call sites | LOW |
| Fulltext search API: `db.index.fulltext.*` → `db.idx.fulltext.*` | 6 call sites | LOW |
| Constraints: Cypher DDL → Redis command `GRAPH.CONSTRAINT CREATE` | 3 constraints | **MEDIUM** — completely different API |
| Index creation: remove `IF NOT EXISTS`, remove names | 4 indexes + 2 vector | **MEDIUM** — syntax differs |
| `SHOW INDEXES` → `db.indexes()` procedure | 1 call site | LOW |
| `EXISTS {}` subquery → rewrite | 2 call sites | **MEDIUM** — may not be supported |
| Map projection `{.*}` → `properties()` | 1 call site | LOW |
| Connection config: Bolt URI → Redis host:port | All connection points | LOW |
| Exception handling: `neo4j.exceptions` → `redis.exceptions` | 1 location | LOW |

---

## 2. Verified Cypher Compatibility

### 2.1 FOREACH — COMPATIBLE ✅

All 3 usages use `FOREACH (_ IN CASE WHEN cond THEN [1] ELSE [] END | action)`.
FalkorDB supports this per [docs](https://docs.falkordb.com/cypher/foreach.html).

**Locations (no changes needed):**
- `database.py:1235` — `create_knowledge_candidate()`
- `database.py:2459` — `delete_learned_rule()` (1st)
- `database.py:2464` — `delete_learned_rule()` (2nd)

### 2.2 MERGE ON CREATE SET / ON MATCH SET — COMPATIBLE ✅

FalkorDB supports both per [docs](https://docs.falkordb.com/cypher/merge.html).

**Locations (no changes needed):**
- `database.py:1228` — `create_knowledge_candidate()` (ON CREATE SET)
- `database.py:1321` — `verify_knowledge_candidate()` (ON CREATE SET)
- `database.py:2302` — `save_learned_rule()` (ON CREATE SET)
- `database.py:2306` — `save_learned_rule()` (ON MATCH SET)
- `database.py:2312` — `save_learned_rule()` (ON CREATE SET)
- `database.py:2318` — `save_learned_rule()` (ON CREATE SET)
- `database.py:2322` — `save_learned_rule()` (ON MATCH SET)

### 2.3 timestamp() — COMPATIBLE ✅

Confirmed in [FalkorDB function list](https://docs.falkordb.com/cypher/functions.html). Returns milliseconds since epoch.

### 2.4 Known FalkorDB Limitations (from [docs](https://docs.falkordb.com/cypher/known-limitations.html))

| Limitation | Impact on Us |
|---|---|
| **Relationship uniqueness in patterns**: Unref'd relations only check existence, not enumerate | LOW — we always reference relationship aliases |
| **LIMIT with eager operations**: CREATE/SET/DELETE/MERGE execute before LIMIT | LOW — we don't combine writes with LIMIT |
| **Index `<>` filter**: Indexes can't optimize not-equal filters | LOW — we don't rely on `<>` index scans |
| **No regex operators** | LOW — we don't use regex in Cypher |
| **DELETE = DETACH DELETE always** | NONE — we already use DETACH DELETE |

---

## 3. Breaking Changes — What MUST Change

### 3.1 Result format: list-of-lists (CRITICAL)

**Neo4j** returns `Record` objects with named field access (`record["name"]`, `dict(record)`).
**FalkorDB** returns `QueryResult` with `result_set` as **list-of-lists** (positional access) and `header` as **list of `(type, name)` tuples**.

```python
# Neo4j
result = session.run("MATCH (n:Person) RETURN n.name, n.age")
for record in result:
    print(record["name"])  # named access

# FalkorDB
result = graph.query("MATCH (n:Person) RETURN n.name, n.age")
# result.header = [(1, 'n.name'), (1, 'n.age')]
# result.result_set = [['Alice', 30], ['Bob', 25]]
for row in result.result_set:
    print(row[0])  # positional access
```

**This is the single biggest migration task.** Every method that reads query results must be adapted.

### 3.2 Parameter passing (transparent)

FalkorDB's Python driver accepts `params=dict` and internally serializes to `CYPHER key=val` prefix. **No Cypher string changes needed for parameters.**

```python
# Both work the same from caller's perspective:
# Neo4j:  session.run(cypher, name="Alice")
# FalkorDB: graph.query(cypher, params={"name": "Alice"})
```

### 3.3 Constraints use Redis commands, not Cypher

**Neo4j:**
```cypher
CREATE CONSTRAINT IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS UNIQUE
```

**FalkorDB:**
```
GRAPH.CONSTRAINT CREATE graphname UNIQUE NODE Session PROPERTIES 1 id
```
- Requires existing index on the same property
- Async — returns `PENDING`, must poll for `OPERATIONAL`
- No `IF NOT EXISTS` — must handle idempotently

### 3.4 Index syntax differs

**Neo4j:**
```cypher
CREATE INDEX session_last_active IF NOT EXISTS FOR (s:Session) ON (s.last_active)
```

**FalkorDB:**
```cypher
CREATE INDEX FOR (s:Session) ON (s.last_active)
```
- No named indexes
- No `IF NOT EXISTS` — must catch "already exists" errors
- `SHOW INDEXES` → use `db.indexes()` procedure or `GRAPH.EXPLAIN`

### 3.5 `EXISTS {}` subquery predicate (2 usages)

Line 4201 and 4209 in `database.py`:
```cypher
WHERE EXISTS { (p)-[:HAS_TURN]->(:ConversationTurn) }
```

FalkorDB supports `exists(pattern)` as a function but `EXISTS {}` subquery syntax may not be supported. Needs rewrite to:
```cypher
WHERE exists((p)-[:HAS_TURN]->(:ConversationTurn))
```
Or:
```cypher
WHERE (p)-[:HAS_TURN]->(:ConversationTurn)
```

---

## 4. Phase 0: FalkorDB Setup & Data Migration

### 4.1 Hosting decision

| Option | Cost | Pros | Cons |
|--------|------|------|------|
| **Self-hosted Docker** | Free (infra cost only) | Full control, no vendor lock | Ops burden, no HA |
| **FalkorDB Cloud Free** | $0 | Quick start | No TLS, no HA, no persistence, no backups |
| **FalkorDB Cloud Startup** | From $73/GB/mo | TLS, backups every 12h | No HA, no VPC |
| **FalkorDB Cloud Pro** | From $350/8GB/mo | HA, multi-zone, TLS, cluster | Cost |

**Recommendation**: Start with self-hosted Docker for dev/test, move to Cloud Pro for production (comparable to Neo4j Aura).

### 4.2 Local dev setup

```bash
docker run -d --name falkordb -p 6379:6379 falkordb/falkordb:latest
```

### 4.3 Data migration strategy

FalkorDB provides an [official migration tool](https://docs.falkordb.com/operations/migration/neo4j-to-falkordb.html):

**Step 1: Generate config template**
```bash
python3 neo4j_to_csv_extractor.py --password $NEO4J_PASSWORD \
  --generate-template config.json --analyze-only
```

**Step 2: Extract from Neo4j**
```bash
python3 neo4j_to_csv_extractor.py --password $NEO4J_PASSWORD \
  --config config.json
```

**Step 3: Load into FalkorDB**
```bash
python3 falkordb_csv_loader.py synapse --port 6379 --batch-size 5000 --stats
```

**Alternative**: Re-seed from scripts (run `mh_hvac_traits.py` + other seeds against FalkorDB after driver swap). This is cleaner but slower and exercises more code.

**Recommended approach**: Use official migration tool for initial data, then verify with seed scripts.

---

## 5. Phase 1: Python Driver Swap (database.py)

This is the biggest phase. 140 methods, 165 `session.run()` calls.

### 5.1 Package swap

```diff
# requirements.txt
- neo4j>=6.1.0
+ falkordb>=1.4.0
```

Note: `falkordb` depends on `redis` internally — no need to add `redis` separately.

### 5.2 Environment variables

```diff
# .env
- NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
- NEO4J_USER=neo4j
- NEO4J_PASSWORD=secret
- NEO4J_DATABASE=neo4j
+ FALKORDB_HOST=localhost
+ FALKORDB_PORT=6379
+ FALKORDB_PASSWORD=
+ FALKORDB_GRAPH=synapse
```

### 5.3 Constructor rewrite

```python
# BEFORE
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired

class Neo4jConnection:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI")
        self.user = os.getenv("NEO4J_USER")
        self.password = os.getenv("NEO4J_PASSWORD")
        self.database = os.getenv("NEO4J_DATABASE", "neo4j")
        self.driver = None

    def connect(self):
        if not self.driver:
            self.driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_acquisition_timeout=30,
                keep_alive=True,
            )
        return self.driver

# AFTER
from falkordb import FalkorDB
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

class Neo4jConnection:  # Keep class name to avoid renaming across 50+ import sites
    def __init__(self):
        self._host = os.getenv("FALKORDB_HOST", "localhost")
        self._port = int(os.getenv("FALKORDB_PORT", "6379"))
        self._password = os.getenv("FALKORDB_PASSWORD") or None
        self._graph_name = os.getenv("FALKORDB_GRAPH", "synapse")
        self.database = self._graph_name  # backward compat for session_graph.py
        self._fdb = None
        self._graph = None

    def connect(self):
        """Return the FalkorDB graph object (replaces returning driver)."""
        if not self._graph:
            self._fdb = FalkorDB(
                host=self._host,
                port=self._port,
                password=self._password,
            )
            self._graph = self._fdb.select_graph(self._graph_name)
        return self._graph

    def close(self):
        # FalkorDB uses Redis connections — close handled by garbage collection
        self._graph = None
        self._fdb = None

    def reconnect(self):
        self.close()
        return self.connect()
```

### 5.4 Helper methods (the adaptation layer)

These convert FalkorDB's list-of-lists back to dicts for backward compatibility:

```python
def _query(self, cypher: str, params: dict = None) -> list[dict]:
    """Execute read query, return list of dicts (Neo4j-compatible shape)."""
    graph = self.connect()
    result = graph.ro_query(cypher, params or {})
    if not result.result_set:
        return []
    headers = [h[1] for h in result.header]
    return [
        {headers[i]: row[i] for i in range(len(headers))}
        for row in result.result_set
    ]

def _query_single(self, cypher: str, params: dict = None) -> dict | None:
    """Execute read query, return first row as dict or None."""
    rows = self._query(cypher, params)
    return rows[0] if rows else None

def _write(self, cypher: str, params: dict = None) -> list[dict]:
    """Execute write query, return list of dicts."""
    graph = self.connect()
    result = graph.query(cypher, params or {})
    if not result.result_set:
        return []
    headers = [h[1] for h in result.header]
    return [
        {headers[i]: row[i] for i in range(len(headers))}
        for row in result.result_set
    ]

def _write_void(self, cypher: str, params: dict = None) -> None:
    """Execute write query, ignore result."""
    graph = self.connect()
    graph.query(cypher, params or {})
```

### 5.5 Retry logic adaptation

```python
def _execute_with_retry(self, query_func, max_retries=2):
    """Execute with retry on connection failure."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return query_func()
        except (RedisConnectionError, RedisTimeoutError) as e:
            last_error = e
            if attempt < max_retries:
                self.reconnect()
            else:
                raise
        except Exception as e:
            error_msg = str(e).lower()
            if "connection" in error_msg or "timeout" in error_msg:
                last_error = e
                if attempt < max_retries:
                    self.reconnect()
                else:
                    raise
            else:
                raise
    raise last_error
```

### 5.6 Method conversion — the 4 patterns

The 140 methods use inner `_query()` closures that call `driver.session()` → `session.run()`. After migration, they call the helper methods instead.

**Pattern A: List collection (70 methods) — `[dict(record) for record in result]`**
```python
# BEFORE
def some_method(self, ...):
    def _query():
        driver = self.connect()
        with driver.session(database=self.database) as session:
            result = session.run("""MATCH (n) RETURN n.name, n.age""", ...)
            return [dict(record) for record in result]
    return self._execute_with_retry(_query)

# AFTER
def some_method(self, ...):
    def _query():
        return self._query("""MATCH (n) RETURN n.name, n.age""", {...})
    return self._execute_with_retry(_query)
```

**Pattern B: Single record + field extraction (20 methods)**
```python
# BEFORE
record = result.single()
return record["count"] if record else 0

# AFTER
row = self._query_single(cypher, params)
return row["count"] if row else 0
```

**Pattern C: Boolean check (3 methods)**
```python
# BEFORE
record = result.single()
return record is not None

# AFTER
row = self._query_single(cypher, params)
return row is not None
```

**Pattern D: Write-only / fire-and-forget (9 methods)**
```python
# BEFORE
session.run(cypher, params)

# AFTER
self._write_void(cypher, params)
```

**Pattern E: Peek guard (3 methods — lines 4081, 4244, 4333)**
```python
# BEFORE
proj = dict(proj_result.single()) if proj_result.peek() else {...}

# AFTER
row = self._query_single(cypher, params)
proj = dict(row) if row else {...}
```

**Pattern F: Multi-query in single session (~8 methods)**
These methods run multiple queries within one `session`. Since FalkorDB doesn't have sessions (each `graph.query()` is independent), these just become sequential `self._query()` / `self._write()` calls. No behavioral change.

### 5.7 FalkorDB Node/Edge objects

**CRITICAL**: When Cypher returns a full node (`RETURN n` instead of `RETURN n.name`), FalkorDB returns a `Node` object (not a dict). The `Node` object has `.id`, `.labels`, and `.properties` attributes. Same for `Edge` objects.

Our code mostly returns projected properties (`RETURN n.name AS name`), which come back as scalars. But a few methods may return full nodes — these need manual handling:

```python
# If a method returns full nodes, extract properties:
from falkordb import Node, Edge

def _to_dict(val):
    """Convert FalkorDB Node/Edge to dict, leave scalars as-is."""
    if isinstance(val, Node):
        return {"id": val.id, "labels": val.labels, **val.properties}
    if isinstance(val, Edge):
        return {"id": val.id, "type": val.relation, **val.properties}
    return val
```

This should be integrated into the `_query()` helper.

### 5.8 The `warmup()` method

```python
# BEFORE
def warmup(self):
    driver = self.connect()
    with driver.session(database=self.database) as session:
        session.run("RETURN 1").single()

# AFTER
def warmup(self):
    graph = self.connect()
    result = graph.query("RETURN 1")
    # result.result_set = [[1]]
```

---

## 6. Phase 2: Session Graph & Adapter Layer

### 6.1 `backend/logic/session_graph.py`

Only 2 methods access the driver directly:

```python
# BEFORE
def _run_query(self, cypher: str, params: dict = None) -> list:
    with self.db.driver.session(database=self.db.database) as session:
        result = session.run(cypher, params or {})
        return [record.data() for record in result]

def _run_write(self, cypher: str, params: dict = None) -> None:
    with self.db.driver.session(database=self.db.database) as session:
        session.run(cypher, params or {})

# AFTER — delegate to database.py helpers
def _run_query(self, cypher: str, params: dict = None) -> list:
    return self.db._query(cypher, params)

def _run_write(self, cypher: str, params: dict = None) -> None:
    self.db._write_void(cypher, params)
```

**Note**: `_run_query` previously used `record.data()` (returns nested dicts with node properties). The `_query()` helper returns flat dicts from `result.header`. If any `session_graph.py` method accesses nested node properties, it may need the `_to_dict()` Node handling.

Check: `get_project_state()` at line 462 uses `collect(t {.*})` — this returns map projections. See Phase 6.

### 6.2 `backend/logic/engine_adapter.py`

The factory function `create_engine_adapter()` (line 318) already has FalkorDB support as the primary option. The Neo4j fallback (lines 352-359) uses `GraphDatabase.driver()` — just needs the same driver swap pattern.

### 6.3 `backend/main.py`

`main.py` imports `from database import db` — the module-level singleton. Since we're changing `Neo4jConnection.__init__()`, this requires no changes to `main.py` itself.

The startup event calls `db.warmup()` and `db.init_session_schema()` — both methods change internally (Phases 1 and 5), but the call site doesn't change.

---

## 7. Phase 3: Vector Search API

### 7.1 API difference

| | Neo4j | FalkorDB |
|---|---|---|
| **Procedure** | `db.index.vector.queryNodes` | `db.idx.vector.queryNodes` |
| **Parameters** | `(index_name, top_k, embedding)` | `(label, attribute, top_k, vecf32(embedding))` |
| **Key diff** | Named index | Label + attribute + `vecf32()` wrapper |

### 7.2 The 6 call sites

| # | Line | Method | Neo4j Index | → FalkorDB Label | → FalkorDB Attribute |
|---|---|---|---|---|---|
| 1 | ~376 | `vector_search_concepts()` | `concept_embeddings` | `Concept` | `embedding` |
| 2 | ~738 | `hybrid_retrieval()` | `concept_embeddings` | `Concept` | `embedding` |
| 3 | ~805 | `check_safety_risks()` | `concept_embeddings` | `Concept` | `embedding` |
| 4 | ~892 | `get_similar_cases()` | `concept_embeddings` | `Concept` | `embedding` |
| 5 | ~2371 | `get_semantic_rules()` | `learned_rules_embeddings` | `Keyword` | `embedding` |
| 6 | ~2575 | `vector_search_applications()` | `application_embeddings` | `Application` | `embedding` |

### 7.3 Conversion pattern

```python
# BEFORE
CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
YIELD node, score

# AFTER
CALL db.idx.vector.queryNodes('Concept', 'embedding', $top_k, vecf32($embedding))
YIELD node, score
```

**Note**: The `vecf32()` function wraps the embedding list. FalkorDB requires this for vector queries.

**Note**: The `$index_name` parameter is removed — replaced by hardcoded label + attribute strings. This is simpler but less flexible.

---

## 8. Phase 4: Fulltext Search API

### 8.1 API difference

| | Neo4j | FalkorDB |
|---|---|---|
| **Procedure** | `db.index.fulltext.queryNodes` | `db.idx.fulltext.queryNodes` |
| **Parameters** | `("index_name", term)` | `('Label', term)` |
| **Key diff** | Named index | Label name |

### 8.2 The 6 call sites

| # | Line | Method | Neo4j Index → FalkorDB Label |
|---|---|---|---|
| 1 | ~1137 | `search_by_project_name()` | `project_fulltext` → `Project` |
| 2 | ~1912 | `search_product_variants()` | `product_variant_fulltext` → `ProductVariant` |
| 3 | ~2094 | `configuration_graph_search()` | `product_variant_fulltext` → `ProductVariant` |
| 4 | ~2142 | `configuration_graph_search()` | `filter_cartridge_fulltext` → `FilterCartridge` |
| 5 | ~2167 | `configuration_graph_search()` | `filter_consumable_fulltext` → `FilterConsumable` |
| 6 | ~2195 | `configuration_graph_search()` | `material_spec_fulltext` → `MaterialSpec` |

### 8.3 Conversion pattern

```python
# BEFORE
CALL db.index.fulltext.queryNodes("product_variant_fulltext", $term)
YIELD node AS pv, score

# AFTER
CALL db.idx.fulltext.queryNodes('ProductVariant', $term)
YIELD node AS pv, score
```

---

## 9. Phase 5: Index & Constraint DDL

This is more complex than the original plan assumed. FalkorDB uses completely different APIs for constraints.

### 9.1 Regular (range) index creation

```python
# BEFORE (Neo4j)
"CREATE INDEX session_last_active IF NOT EXISTS FOR (s:Session) ON (s.last_active)"

# AFTER (FalkorDB) — no names, no IF NOT EXISTS
"CREATE INDEX FOR (s:Session) ON (s.last_active)"
# Must catch "already exists" errors
```

**Files to change:**
- `database.py:4173-4178` — `init_session_schema()` (4 indexes)

### 9.2 Vector index creation

```python
# BEFORE (Neo4j)
CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
FOR (c:Concept) ON (c.embedding)
OPTIONS {indexConfig: {
    `vector.dimensions`: 3072,
    `vector.similarity_function`: 'cosine'
}}

# AFTER (FalkorDB)
CREATE VECTOR INDEX FOR (c:Concept) ON (c.embedding)
OPTIONS {dimension: 3072, similarityFunction: 'cosine'}
```

**Key changes:**
- No `IF NOT EXISTS` — catch errors
- No index name
- `indexConfig` wrapper removed
- `vector.dimensions` → `dimension`
- `vector.similarity_function` → `similarityFunction`

**Files to change:**
- `database.py:352` — `create_vector_index()`
- `database.py:2258` — `ensure_learned_rules_index()`

### 9.3 Fulltext index creation

```python
# BEFORE (Neo4j Cypher DDL)
CREATE FULLTEXT INDEX product_variant_fulltext IF NOT EXISTS
FOR (n:ProductVariant) ON EACH [n.code, n.name, n.description]

# AFTER (FalkorDB procedure)
CALL db.idx.fulltext.createNodeIndex('ProductVariant', 'code', 'name', 'description')
```

**Files to change:**
- `database/apply_indexes.py` — fulltext index creation loop

### 9.4 Unique constraints — REQUIRES COMPLETELY DIFFERENT APPROACH

**Neo4j** uses Cypher DDL:
```cypher
CREATE CONSTRAINT IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS UNIQUE
```

**FalkorDB** uses a Redis command (NOT Cypher):
```
GRAPH.CONSTRAINT CREATE synapse UNIQUE NODE Session PROPERTIES 1 id
```

**Requirements:**
1. An exact-match index must exist on the property BEFORE creating the constraint
2. The constraint is created asynchronously — returns `PENDING`
3. Must poll `db.constraints()` to check if status is `OPERATIONAL`
4. No `IF NOT EXISTS` — must handle idempotently

**Implementation:**
```python
def _ensure_unique_constraint(self, label: str, property: str):
    """Create a unique constraint (FalkorDB-style)."""
    graph = self.connect()
    # Step 1: Ensure index exists
    try:
        graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{property})")
    except Exception:
        pass  # already exists
    # Step 2: Create constraint via raw Redis command
    try:
        self._fdb.connection.execute_command(
            "GRAPH.CONSTRAINT", "CREATE", self._graph_name,
            "UNIQUE", "NODE", label, "PROPERTIES", "1", property
        )
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise
```

**Constraints to create (from `init_session_schema`):**
| Label | Property |
|---|---|
| `Session` | `id` |
| `ActiveProject` | `id` |
| `ExpertReview` | `id` |

### 9.5 `SHOW INDEXES` replacement

Line 2247: `ensure_learned_rules_index()` uses `SHOW INDEXES WHERE name = $index_name`.

FalkorDB has a `db.indexes()` procedure:
```python
# AFTER
result = graph.query("CALL db.indexes()")
# Check if vector index exists for Keyword.embedding
```

Or simply try to create the index and catch the error:
```python
try:
    graph.query("""
        CREATE VECTOR INDEX FOR (k:Keyword) ON (k.embedding)
        OPTIONS {dimension: 3072, similarityFunction: 'cosine'}
    """)
except Exception as e:
    if "already exists" not in str(e).lower():
        raise
```

---

## 10. Phase 6: Cypher Rewrites (Edge Cases)

### 10.1 `EXISTS {}` subquery → pattern predicate

Lines 4201, 4209 in `get_expert_conversations()`:

```python
# BEFORE
WHERE EXISTS { (p)-[:HAS_TURN]->(:ConversationTurn) }

# AFTER — use pattern predicate (openCypher standard)
WHERE (p)-[:HAS_TURN]->(:ConversationTurn)
```

### 10.2 Map projection `{.*}`

Line 4313 in `submit_expert_review()`:

```python
# BEFORE
RETURN er {.*} AS review

# AFTER — use properties() function
RETURN properties(er) AS review
```

Note: FalkorDB may support `{.*}` — test first. If it works, no change needed.

### 10.3 `collect(t {.*})` in session_graph.py

`get_project_state()` at line 462 uses map projection inside `collect()`. If `{.*}` isn't supported:

```python
# BEFORE
collect(t {.*}) AS tags

# AFTER
collect(properties(t)) AS tags
```

---

## 11. Phase 7: Utility Scripts

### 11.1 Shared connection utility

Create `backend/database/db_connection.py`:

```python
"""Shared FalkorDB connection for utility scripts."""
import os
from falkordb import FalkorDB
from dotenv import load_dotenv

def get_graph(env_path="../.env", graph_name=None):
    """Get a FalkorDB graph connection."""
    load_dotenv(dotenv_path=env_path)
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    password = os.getenv("FALKORDB_PASSWORD") or None
    graph = graph_name or os.getenv("FALKORDB_GRAPH", "synapse")

    fdb = FalkorDB(host=host, port=port, password=password)
    return fdb.select_graph(graph)
```

### 11.2 Scripts to convert (12 files)

Each script replaces its `main()` connection block:

```python
# BEFORE
from neo4j import GraphDatabase
driver = GraphDatabase.driver(uri, auth=(user, password))
with driver.session(database=database) as session:
    session.run(cypher, params)
driver.close()

# AFTER
from database.db_connection import get_graph
graph = get_graph(env_path="../../.env")
graph.query(cypher, params)
```

**NOTE**: Scripts that call `session.run()` and iterate records need the same adaptation as database.py (list-of-lists → named dicts). Most seed scripts just run writes (MERGE/CREATE) and don't read results, so the conversion is simpler.

| Script | Priority | Complexity |
|--------|----------|------------|
| `mh_hvac_traits.py` | HIGH | Medium — 1060 lines, many session.run() calls |
| `seed_hvac.py` | HIGH | Medium |
| `init_graph.py` | HIGH | Low — schema setup |
| `apply_indexes.py` | HIGH | Medium — index DDL changes |
| `update_embeddings.py` | HIGH | Medium — vector index DDL |
| `backup_graph.py` | MEDIUM | Medium |
| `add_accessory_compatibility.py` | LOW | Low |
| `add_catalog_enrichment.py` | LOW | Low |
| `add_physics_mitigation.py` | LOW | Low |
| `add_powder_coating.py` | LOW | Low |
| `add_variable_features.py` | LOW | Low |
| `add_gdp_auto_resolve.py` | LOW | Low |

### 11.3 `load_graph_schema.py`

Has 2 driver instantiations. Same pattern as above.

---

## 12. Phase 8: bulk_offer.py

`bulk_offer.py` has 7 methods that bypass `Neo4jConnection` entirely — they call `db.connect()` to get the raw driver, then open `driver.session()` directly.

```python
# BEFORE
driver = db.connect()
with driver.session(database=db.database) as session:
    result = session.run(cypher, params)
    return [dict(record) for record in result]

# AFTER — use db helper methods
return db._query(cypher, params)
```

**Locations:**
- `_load_housing_variants()` (line 559)
- `_load_capacity_rules()` (line 583)
- `_load_filters_for_class()` (line 632)
- `_load_competitor_context()` (line 1366)
- `_load_all_mh_filters()` (line 1391)
- `_graph_lookup_competitor()` (line 1643)
- `_graph_fuzzy_lookup()` (line 1688)

---

## 13. Phase 9: Test Validation

### 13.1 Update test mocks

The mock fixtures in `conftest.py` mock `Neo4jConnection` methods. Since we're keeping the class name and method signatures, most mocks should work unchanged. However:

- Mock `_query()`, `_query_single()`, `_write()`, `_write_void()` if any test accesses them directly
- Update `mock_db.connect()` to return a FalkorDB graph mock instead of a driver mock
- Tests that mock `driver.session()` need updating

### 13.2 Validation steps

After each phase:

```bash
# 1. Unit tests (always)
cd backend && ./venv/bin/python -m pytest tests/ -v --tb=short

# 2. Live contract tests (after FalkorDB is running)
FALKORDB_HOST=localhost FALKORDB_PORT=6379 \
  ./venv/bin/python -m pytest tests/test_database_contract.py -v

# 3. Smoke test
curl -X POST http://localhost:8000/consult/deep-explainable/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "I need a 600x600 filter for kitchen ventilation", "session_id": "migration_test"}'

# 4. Full regression
# Use /test-hvac skill
```

### 13.3 Key risk: Node/Edge object handling

The biggest test risk is methods that return full graph nodes instead of projected properties. FalkorDB returns `Node` objects (with `.id`, `.labels`, `.properties`) where Neo4j returns `Record` objects (with dict-like access). The `_to_dict()` helper in the `_query()` method must handle this correctly.

---

## 14. FalkorDB Cloud — Hosting Decision

| | Neo4j Aura (current) | FalkorDB Cloud Pro | Self-hosted Docker |
|---|---|---|---|
| **Cost** | ~$65/mo (Free tier available) | From $350/8GB/mo | Infra only |
| **HA** | ✅ | ✅ | Manual |
| **TLS** | ✅ | ✅ | Manual |
| **Backups** | Automated | Every 12h | Manual |
| **Performance** | Good | ~6-10x faster (GraphBLAS) | Same as Cloud |
| **Persistence** | ✅ | ✅ | ✅ (with volume) |

**FalkorDB's value proposition**: Significantly faster query execution due to GraphBLAS sparse matrix engine. Our use case (knowledge graph for real-time HVAC reasoning) benefits from low latency.

---

## 15. File-by-File Change Inventory

### Core files (MUST change)

| File | Changes | Effort |
|------|---------|--------|
| `backend/database.py` | Constructor, helpers, 165 session.run rewrites, 6 vector, 6 fulltext, 2 vector index DDL, 4 range index DDL, 3 constraint DDL, 1 SHOW INDEXES, 2 EXISTS{}, 1 map projection, exception handling | **LARGE** |
| `backend/logic/session_graph.py` | `_run_query`/`_run_write` → delegate to db helpers, verify `{.*}` compatibility | **SMALL** |
| `backend/bulk_offer.py` | 7 methods: replace `driver.session()` with `db._query()` | **MEDIUM** |
| `backend/requirements.txt` | `neo4j>=6.1.0` → `falkordb>=1.4.0` | **TRIVIAL** |
| `.env` | Connection vars | **TRIVIAL** |

### Adapter files (SHOULD change)

| File | Changes | Effort |
|------|---------|--------|
| `backend/logic/engine_adapter.py` | Factory function Neo4j fallback (lines 352-359) | **SMALL** |
| `backend/load_graph_schema.py` | 2 driver instantiations | **SMALL** |

### Utility scripts (CAN change later)

| File | Effort | Priority |
|------|--------|----------|
| `database/mh_hvac_traits.py` | MEDIUM | After core works |
| `database/seed_hvac.py` | MEDIUM | After core works |
| `database/init_graph.py` | SMALL | After core works |
| `database/apply_indexes.py` | MEDIUM (DDL changes) | After core works |
| `database/update_embeddings.py` | MEDIUM (vector DDL) | After core works |
| 7 more `database/add_*.py` | LOW each | LOW priority |

### Files with ZERO changes

| File | Why |
|------|-----|
| `backend/logic/universal_engine.py` | Pure Python, no DB |
| `backend/logic/verdict_adapter.py` | Pure Python, no DB |
| `backend/logic/scribe.py` | LLM calls only (except `_build_env_app_mapping` which calls db methods — works if signatures unchanged) |
| `backend/logic/state.py` | Pure Python dataclass |
| `backend/retriever.py` | Calls db methods (not driver) |
| `backend/chat.py` | Calls db methods |
| `backend/auth.py` | No DB calls |
| `backend/config_loader.py` | No DB calls |
| `frontend/**` | No backend changes |

---

## 16. Rollback Strategy

### Pre-migration checklist

- [ ] Export full Neo4j graph via official migration tool (CSV)
- [ ] Tag git: `git tag pre-falkordb-migration`
- [ ] Verify all tests pass on current Neo4j setup
- [ ] Run `/test-hvac` full regression
- [ ] Document Neo4j Aura connection details in secure storage
- [ ] **Keep Neo4j Aura running during migration** (read-only)

### Rollback

If migration fails:
1. `git checkout pre-falkordb-migration`
2. Restore Neo4j Aura connection (still running)
3. All data is still in Neo4j

---

## 17. Implementation Order

```
Phase 0: FalkorDB Docker setup + data migration (via official tool)
         Test: Can query graph data via redis-cli / FalkorDB browser

Phase 1: database.py driver swap
  1a: Add falkordb to requirements.txt, update .env
  1b: Rewrite constructor + connect() + helper methods (_query, _write, etc.)
  1c: Rewrite _execute_with_retry for Redis exceptions
  1d: Convert methods batch-by-batch (~15 methods per batch)
      → Run unit tests after each batch
  1e: Handle Node/Edge object conversion in helper methods

Phase 2: session_graph.py + engine_adapter.py
         → Run unit tests

Phase 3: Vector search API (6 call sites)
         → Run live vector search test

Phase 4: Fulltext search API (6 call sites)
         → Run live fulltext search test

Phase 5: Index & constraint DDL
  5a: Range indexes (remove IF NOT EXISTS, remove names)
  5b: Vector indexes (new OPTIONS syntax)
  5c: Fulltext indexes (procedure syntax)
  5d: Unique constraints (GRAPH.CONSTRAINT CREATE)
  5e: Replace SHOW INDEXES
         → Run init_session_schema(), verify with db.indexes()

Phase 6: Cypher edge cases
  6a: EXISTS {} → pattern predicate (2 sites)
  6b: {.*} map projection → properties() (1-2 sites)
         → Run affected tests

Phase 7: Utility scripts (shared connection utility + 12 scripts)
         → Run seed scripts against FalkorDB, verify data

Phase 8: bulk_offer.py (7 methods)
         → Run bulk offer tests

Phase 9: Full regression
  9a: All unit tests (305)
  9b: Live contract tests
  9c: /test-hvac full regression
  9d: Manual smoke test via UI ("Graph Reasoning" mode)
  9e: Performance comparison (query latency before/after)
```

**Each phase is independently testable.** The mock-based test suite validates Python logic. The live contract tests validate FalkorDB compatibility.

**Estimated total effort**: ~600-800 lines of code changes across 20+ files. The majority (Phase 1d) is mechanical pattern replacement.
