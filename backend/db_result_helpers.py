"""FalkorDB ↔ Neo4j result conversion helpers.

These functions convert FalkorDB's list-of-lists result format (QueryResult)
into the dict-based format that all 140 database.py methods currently expect.

After migration, every _query() closure in database.py will call these helpers
instead of iterating Neo4j Record objects.

Usage (post-migration):
    result = graph.query(cypher, params=params)
    rows = result_to_dicts(result)          # replaces [dict(r) for r in result]
    row  = result_single(result)            # replaces dict(result.single()) if result.peek() else default
    val  = result_value(result, "count", 0) # replaces record["count"] if record else 0
"""

from __future__ import annotations


def _unwrap_value(val):
    """Convert FalkorDB Node/Edge objects to plain dicts.

    FalkorDB returns Node/Edge objects when Cypher selects full nodes
    (e.g., RETURN n) instead of properties (e.g., RETURN n.name).
    Neo4j returns the same as dicts via record.data(), so we normalize here.

    Uses duck-typing (checks for .properties attribute) to avoid importing
    falkordb at module level — allows running against either driver.
    """
    if val is None:
        return None
    # FalkorDB Node: has .labels + .properties
    if hasattr(val, 'properties') and hasattr(val, 'labels'):
        return {"_id": val.id, "_labels": val.labels, **val.properties}
    # FalkorDB Edge: has .relation + .properties
    if hasattr(val, 'properties') and hasattr(val, 'relation'):
        return {"_id": val.id, "_type": val.relation, **val.properties}
    return val


def result_to_dicts(result) -> list[dict]:
    """Convert a FalkorDB QueryResult to list[dict].

    Replaces the Neo4j pattern: [dict(record) for record in result]
    which appears ~70 times in database.py.

    Args:
        result: FalkorDB QueryResult with .header and .result_set attributes.

    Returns:
        List of dicts, one per row, with column names as keys.
    """
    if not hasattr(result, 'result_set') or not result.result_set:
        return []
    headers = [h[1] for h in result.header]
    rows = []
    for row in result.result_set:
        d = {}
        for i, h in enumerate(headers):
            d[h] = _unwrap_value(row[i])
        rows.append(d)
    return rows


def result_single(result) -> dict | None:
    """Extract first row as dict, or None if empty.

    Replaces the Neo4j pattern: dict(result.single()) if result.peek() else {default}
    which appears ~15 times in database.py (including 3 peek() sites).

    Args:
        result: FalkorDB QueryResult.

    Returns:
        First row as dict, or None if no results.
    """
    rows = result_to_dicts(result)
    return rows[0] if rows else None


def result_value(result, key: str, default=None):
    """Extract a single value from the first row.

    Replaces patterns like: record["count"] if record else 0

    Args:
        result: FalkorDB QueryResult.
        key: Column name to extract.
        default: Value to return if no results or key missing.

    Returns:
        The value, or default.
    """
    row = result_single(result)
    if row is None:
        return default
    return row.get(key, default)
