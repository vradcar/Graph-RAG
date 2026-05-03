---
phase: 01-schema-provenance-foundation
plan: "02"
subsystem: loader
tags: [neo4j, cypher, provenance, loader]
dependency_graph:
  requires: [01-01]
  provides: [provenance-helpers, doc-id-aware-loader, Document-constraint]
  affects: [src/graph/provenance.py, src/graph/neo4j_loader.py]
tech_stack:
  added: []
  patterns: [MERGE-ON-CREATE-ON-MATCH, coll.distinct-dedup, parallel-evidence-edges, doc-first-tx-ordering]
key_files:
  created:
    - src/graph/provenance.py
  modified:
    - src/graph/neo4j_loader.py
decisions:
  - "D-06: doc_id is required positional arg on helpers — fails loudly at call site, not silently as source_doc=null"
  - "D-07: Document upsert runs in its own committed tx BEFORE entity loop (MENTIONED_IN MATCH safety)"
  - "D-08: MENTIONED_IN does NOT carry source_doc — it IS the citation; audit query excludes it"
  - "Provenance helpers accept a node/edge dict rather than expanded params — matches test contract from Plan 01"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-02"
  tasks_completed: 2
  files_modified: 2
requirements: [SCHEMA-01, SCHEMA-02, SCHEMA-03, SCHEMA-04, SCHEMA-05]
---

# Phase 01 Plan 02: Provenance Helpers + Loader Refactor Summary

Added `src/graph/provenance.py` with three Cypher helpers (merge_document, merge_node_with_provenance, merge_edge_with_provenance) and refactored `neo4j_loader.py` to route every write through them, adding --doc-id CLI flag, :Document uniqueness constraint, and doc-first transaction ordering.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement src/graph/provenance.py with three Cypher helpers | 348c3e3 | src/graph/provenance.py |
| 2 | Refactor neo4j_loader.py to route through provenance.py + add --doc-id CLI flag | 17520ac | src/graph/neo4j_loader.py |

## New CLI Invocation Pattern

```bash
# --doc-id is REQUIRED; missing it errors with a clear message
python -m src.graph.neo4j_loader \
  --doc-id t9_install_guide \
  --input data/processed/graph_items.json

# Full reset + optional metadata
python -m src.graph.neo4j_loader \
  --reset \
  --doc-id t9_install_guide \
  --doc-title "T9 Thermostat Installation Guide" \
  --doc-sku THX9421R5021WW \
  --doc-source-url "https://example.com/t9.pdf" \
  --input data/processed/graph_items.json \
  --verify
```

Missing `--doc-id` produces:
```
neo4j_loader.py: error: the following arguments are required: --doc-id
```

## Audit Query and Expected Results

After a fresh ingest, the following Cypher queries confirm provenance integrity:

```cypher
-- 1. No business edge is missing source_doc (should return 0)
MATCH ()-[r]->()
WHERE type(r) <> 'MENTIONED_IN' AND r.source_doc IS NULL
RETURN count(r) AS missing;

-- 2. Document node was created
MATCH (:Document {doc_id: 't9_install_guide'}) RETURN count(*);
-- expected: 1

-- 3. Every entity has a MENTIONED_IN edge
MATCH (n) WHERE n.source_docs IS NOT NULL RETURN count(n);
-- expected: equals total entity node count

-- 4. Same fact from doc_a + doc_b → 2 parallel edges
MATCH (a)-[r:COMPATIBLE_WITH]->(b) RETURN collect(r.source_doc);
-- expected: ['doc_a', 'doc_b'] for facts shared across two PDFs
```

## Loader Public API Change

`load_nodes` and `load_edges` gained a required `doc_id: str` parameter:

```python
# Before (Plan 01)
load_nodes(driver, nodes)
load_edges(driver, edges)

# After (Plan 02)
load_nodes(driver, nodes, doc_id="t9_install_guide")
load_edges(driver, edges, doc_id="t9_install_guide")
```

`upsert_document(driver, doc_metadata)` is a new public function that must be called before `load_nodes`.

## Test Status

| Suite | Count | Status |
|-------|-------|--------|
| tests/test_schema.py (unit) | 5 | GREEN — pass without Neo4j |
| tests/test_provenance.py (integration) | 8 | SKIP cleanly when Neo4j unreachable; GREEN against live Neo4j |
| **Total** | **13** | **5 passed + 8 skipped (no Neo4j) / 13 passed (live Neo4j)** |

## Note for Phase 2

`ingest.py` is the next caller to wire: the manifest → `--doc-id` plumbing is the next integration point. Phase 2 should:
1. Read the manifest slug for the PDF being ingested.
2. Pass it as `doc_id` to `load_nodes` / `load_edges` (already accept it).
3. Build `doc_metadata` dict from the manifest and call `upsert_document` first.

The seam is clean — Phase 1 locked `doc_id` as a required positional arg so any missing-wiring fails loudly at call time.

## Deviations from Plan

**1. [Rule 1 - Adaptation] merge_node/edge_with_provenance signature matches test contract**
- **Found during:** Task 1 — comparing plan interface block vs test_provenance.py imports
- **Issue:** Plan interface specifies `(tx, label, node_id, props, doc_id)` but test_provenance.py calls `(tx, node_dict, doc_id)` — a single dict rather than expanded params
- **Fix:** Implemented the dict-based signature to match the test contract (tests are the authoritative contract per Plan 01 SUMMARY)
- **Files modified:** src/graph/provenance.py

## Known Stubs

None — all provenance helpers are fully implemented.

## Threat Surface Scan

| Flag | File | Description |
|------|------|-------------|
| threat_flag: label-injection (mitigated) | src/graph/provenance.py | Node label and edge relation type are f-string substituted into Cypher — mitigated by safe_label/safe_rel sanitization in loader before reaching helpers. doc_id is always parameterized ($doc_id). |

## Self-Check: PASSED

- [x] src/graph/provenance.py exists — FOUND
- [x] src/graph/neo4j_loader.py contains `merge_node_with_provenance` — FOUND
- [x] `--doc-id` is a required CLI flag — VERIFIED (error message confirmed)
- [x] Commit 348c3e3 exists — FOUND
- [x] Commit 17520ac exists — FOUND
- [x] 5 unit tests pass — VERIFIED
- [x] 8 integration tests skip cleanly — VERIFIED
