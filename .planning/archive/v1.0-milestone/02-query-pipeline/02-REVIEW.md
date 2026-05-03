---
phase: 02-query-pipeline
reviewed: 2026-04-15T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - src/retrieval/graph_retriever.py
  - src/llm/generate.py
  - src/pipeline/query.py
  - src/pipeline/evaluate.py
  - data/eval/queries.json
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-04-15
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

The query pipeline is well-structured with good patterns: instructor for structured LLM output, entity resolution with validation against the graph, and a clean separation between retrieval and generation. Key concerns are a hardcoded password fallback in settings.yaml flowing into two pipeline files, and missing error handling for LLM/Neo4j failures.

## Critical Issues

### CR-01: Hardcoded Neo4j password used as fallback

**File:** `src/pipeline/query.py:32` and `src/pipeline/evaluate.py:29`
**Issue:** Both files use `os.getenv("NEO4J_PASSWORD", settings["graph"]["neo4j_password"])` which falls back to `config/settings.yaml` where `neo4j_password: "password"` is hardcoded. If the env var is unset, the pipeline silently connects with the default password. This is a credentials-in-code issue -- the YAML file is checked into git.
**Fix:** Remove `neo4j_password` from `settings.yaml` entirely. Require the env var and fail explicitly:
```python
neo4j_password = os.getenv("NEO4J_PASSWORD")
if not neo4j_password:
    print("ERROR: NEO4J_PASSWORD environment variable is required", file=sys.stderr)
    sys.exit(1)
```

## Warnings

### WR-01: No error handling around LLM calls

**File:** `src/retrieval/graph_retriever.py:48-63` and `src/llm/generate.py:60-71`
**Issue:** LLM API calls (`client.chat.completions.create`) can raise network errors, rate limit errors, or validation errors from instructor. Neither call site has try/except, so any transient failure crashes the entire pipeline with an unhandled exception and no user-friendly message.
**Fix:** Wrap LLM calls in try/except and return a sensible fallback or re-raise with context:
```python
try:
    result = client.chat.completions.create(...)
except Exception as e:
    print(f"LLM call failed: {e}", file=sys.stderr)
    return []  # or a not_found QueryAnswer
```

### WR-02: `load_all_node_ids` accesses private `_driver` attribute

**File:** `src/retrieval/graph_retriever.py:34`
**Issue:** `store._driver.session()` accesses a private attribute of `Neo4jGraphStore`. If the store's internal implementation changes, this breaks silently. The same pattern appears at line 98.
**Fix:** Add a public `run_query` or `session` method to `Neo4jGraphStore` and use that instead. Alternatively, add `load_all_node_ids` as a method on the store class.

### WR-03: `resolve_entities` can return IDs not in `known_ids` list

**File:** `src/retrieval/graph_retriever.py:63`
**Issue:** The LLM is instructed to only return known IDs, but `instructor` with `max_retries=2` does not enforce this constraint at the schema level. The `graph_retrieve` function does validate against `store.has_node()` (line 131), which is good, but there is no validation that returned IDs are from `known_ids` specifically -- only that they exist in Neo4j. An LLM hallucination that happens to match a real node ID would pass through.
**Fix:** Validate against the `known_ids` set, not just `has_node`:
```python
known_set = set(known_ids)
valid_ids = [nid for nid in resolved if nid in known_set]
```

## Info

### IN-01: Duplicated Neo4j connection boilerplate

**File:** `src/pipeline/query.py:29-34` and `src/pipeline/evaluate.py:26-31`
**Issue:** The settings loading and Neo4j credential resolution is copy-pasted between `query.py` and `evaluate.py`. Any change to connection logic must be duplicated.
**Fix:** Extract a shared helper (e.g., `src/common/connections.py`) that returns `(store, client, model)`.

### IN-02: RELATION_QUERIES is hardcoded and may drift from schema

**File:** `src/retrieval/graph_retriever.py:67-84`
**Issue:** The relation type strings (`COMPATIBLE_WITH`, `REPLACES`, etc.) are hardcoded. If the extraction phase adds new relation types, this file must be manually updated or those relations will be missed by targeted queries (though BFS would still find them).
**Fix:** Consider querying Neo4j for relationship types dynamically: `CALL db.relationshipTypes()`, or at minimum add a comment noting this coupling.

---

_Reviewed: 2026-04-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
