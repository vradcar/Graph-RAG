---
phase: 02-query-pipeline
fixed_at: 2026-04-15T00:00:00Z
review_path: .planning/phases/02-query-pipeline/02-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-04-15
**Source review:** .planning/phases/02-query-pipeline/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0

## Fixed Issues

### CR-01: Hardcoded Neo4j password used as fallback

**Files modified:** `src/pipeline/query.py`, `src/pipeline/evaluate.py`, `config/settings.yaml`
**Commit:** b9a549e
**Applied fix:** Removed `neo4j_password` from settings.yaml, changed both pipeline files to require NEO4J_PASSWORD env var and exit with error if missing. Added missing `import sys` to evaluate.py.

### WR-01: No error handling around LLM calls

**Files modified:** `src/retrieval/graph_retriever.py`, `src/llm/generate.py`
**Commit:** aef85f2
**Applied fix:** Wrapped `client.chat.completions.create` in try/except in both `resolve_entities` (returns empty list on failure) and `generate_answer` (returns not_found QueryAnswer on failure), with stderr logging.

### WR-02: Private `_driver` access

**Files modified:** `src/graph/store.py`, `src/retrieval/graph_retriever.py`
**Commit:** 2a1f4a4
**Applied fix:** Added public `run_cypher(query, **params)` method to `Neo4jGraphStore`. Updated `load_all_node_ids` and `retrieve_graph_context` in graph_retriever.py to use `store.run_cypher()` instead of `store._driver.session()`.

### WR-03: Validate resolved entity IDs against known_ids set

**Files modified:** `src/retrieval/graph_retriever.py`
**Commit:** d2fb8b1
**Applied fix:** Changed validation in `graph_retrieve` from `store.has_node(nid)` to membership check against `set(known_ids)`, preventing hallucinated IDs that happen to exist in Neo4j from passing through.

---

_Fixed: 2026-04-15_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
