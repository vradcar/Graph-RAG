---
phase: 03-batch-ingestion-tooling
plan: 03
subsystem: ingest
tags: [batch, neo4j, idempotency, scoped-delete, BATCH-01, BATCH-04]
requires:
  - src/ingest/batch.py (dry-run scaffold — Plan 03-02)
  - scripts/batch_ingest.py (CLI entry point — Plan 03-02)
  - src/graph/provenance.py (scoped_delete_doc, merge helpers — Plan 02-01)
  - src/graph/neo4j_loader.py (create_constraints, upsert_document, load_nodes, load_edges — Plan 02-02)
  - tests/conftest.py (neo4j_driver, clean_db fixtures)
provides:
  - src/ingest/batch.py:run_batch (non-dry-run path wired)
  - scripts/batch_ingest.py (exit code 3 on connectivity failure, --reset wired)
  - tests/integration/test_batch_ingest_neo4j.py (8 BATCH-04 integration tests)
affects:
  - src/graph/provenance.py (Rule 1 fix: node dedup guard in merge_node_with_provenance)
tech-stack:
  added: []
  patterns:
    - "single driver per run_batch invocation — with GraphDatabase.driver() as driver"
    - "verify_connectivity pre-flight — raises SystemExit caught in main() -> exit code 3"
    - "create_constraints once per invocation (after verify, before doc loop)"
    - "per-doc: scoped_delete_doc -> extract -> upsert_document -> load_nodes -> load_edges"
    - "stage attribution: 'scoped_delete' | 'extract' | 'neo4j_load' set before each step"
    - "node dedup guard: check node_id exists under any label before MERGE with new label"
key-files:
  created:
    - tests/integration/test_batch_ingest_neo4j.py
  modified:
    - src/ingest/batch.py
    - scripts/batch_ingest.py
    - src/graph/provenance.py
decisions:
  - "scoped_delete_doc called in _run_one_doc (not ingest_one_doc) for correct stage attribution — stage='scoped_delete' if delete fails, 'neo4j_load' if upsert/load fails"
  - "neo4j_loader imports (create_constraints, upsert_document, load_nodes, load_edges) moved to module level in batch.py so tests can patch them at src.ingest.batch.*"
  - "merge_node_with_provenance extended with pre-check for existing node_id under any label — prevents multi-label clones from breaking BATCH-04 idempotency"
  - "MENTIONED_IN edges excluded from duplicate-edge test because they legitimately appear once per doc-entity pair"
metrics:
  duration: ~45 minutes
  completed: 2026-05-03
requirements: [BATCH-01, BATCH-04]
---

# Phase 03 Plan 03: Non-Dry-Run Neo4j Path + BATCH-04 Integration Tests Summary

**One-liner:** Full-mode `scripts/batch_ingest.py` (no --dry-run) loads all 4 corpus docs into Neo4j with scoped-delete-before-load, produces identical graph state on two consecutive runs (197 nodes, 460 edges, 0 null source_doc edges), and 8 integration tests prove BATCH-04 idempotency, scoped-delete isolation, --reset, and connectivity pre-flight.

## Scoped Delete Invocation Pattern

`scoped_delete_doc` is called inside `_run_one_doc` (one level above `ingest_one_doc`):

```python
with driver.session() as s:
    s.execute_write(scoped_delete_doc, doc["doc_id"])
```

This runs BEFORE extraction and BEFORE the loader call. The stage tracking sets:
- `stage = "scoped_delete"` before the delete call (so a delete failure is attributed correctly)
- `stage = "extract"` before extraction
- `stage = "neo4j_load"` before `upsert_document`/`load_nodes`/`load_edges`

## Neo4j Loader Functions Used

From `src.graph.neo4j_loader`, composed explicitly per doc (mirrors `neo4j_loader.main()` L290-302):

```python
create_constraints(driver)            # ONCE per run_batch, before doc loop
...
# Per doc:
upsert_document(driver, doc_metadata) # :Document node upsert (D-07 ordering)
load_nodes(driver, nodes, doc_id)     # merge entities + MENTIONED_IN
load_edges(driver, edges, doc_id)     # merge typed edges with source_doc
```

There is NO `load_graph_items`, `load_doc`, or `ingest_to_neo4j` function — the four helpers are composed directly.

## Two-Run Idempotency Numbers (Real Run, 4-Doc Corpus)

| Metric | Run 1 | Run 2 | Equal? |
|--------|-------|-------|--------|
| Total nodes | 197 | 197 | YES |
| Total edges | 460 | 460 | YES |
| Edges with NULL source_doc (non-MENTIONED_IN) | 0 | 0 | YES |
| Duplicate business edges | 0 | 0 | YES |

Run performed 2026-05-03 against Neo4j 5.x at bolt://localhost:7687 with 4-doc cached corpus.

## BATCH-01 through BATCH-04 Verification

| Req | Verification |
|-----|-------------|
| BATCH-01: Full corpus in one command | `python scripts/batch_ingest.py` completes 4 docs, exit 0 |
| BATCH-02: Per-doc reports (Pattern 2 schema) | Inherited from Plan 03-02; still passes (29 integration tests) |
| BATCH-03: Failure isolation + JSONL log | Inherited from Plan 03-02; still passes |
| BATCH-04: Idempotent re-runs | `test_idempotent_re_run_node_counts` + `test_idempotent_re_run_no_duplicate_edges` — both pass |

## Integration Test Results

| Test | Description | Result |
|------|-------------|--------|
| `test_idempotent_re_run_node_counts` | Two runs → identical node+edge+relation counts | PASS |
| `test_idempotent_re_run_no_duplicate_edges` | Zero dup business edges after 2 runs | PASS |
| `test_scoped_delete_preserves_other_docs` | Deleting t9 leaves t6 edges/nodes intact | PASS |
| `test_no_scoped_delete_flag_skips_delete` | --no-scoped-delete sets scoped_delete_ran=False | PASS |
| `test_reset_flag_wipes_db_before_loop` | Sentinel gone, 4 docs loaded | PASS |
| `test_verify_connectivity_failure_exits_3` | Unreachable Neo4j → exit code 3 | PASS |
| `test_loader_failure_marks_stage_neo4j_load` | stage_completed='neo4j_load' on loader failure | PASS |
| `test_no_null_source_doc_after_full_run` | 0 non-MENTIONED_IN edges with NULL source_doc | PASS |

Grand total (all phases): 90 prior + 8 new = 98 tests passing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Multi-label node_id clones breaking BATCH-04 idempotency**
- **Found during:** Task 1 verification — edge count grew 494→497 between runs
- **Issue:** LLM extraction assigned the same `node_id` (e.g., `thermostat`) to nodes with different labels (`Thermostat` from t9, `Product` from t6). The original `merge_node_with_provenance` always MERGEd by `(label, node_id)`, creating separate nodes per label. After `scoped_delete` removed one label instance, re-ingest recreated it. Then `merge_edge_with_provenance`'s `MATCH (a {node_id: $source_id})` found both nodes and created two edges where only one existed before.
- **Fix:** Extended `merge_node_with_provenance` with a pre-check: if any node with `node_id` already exists (under any label), update it in-place instead of creating a new-label clone. New nodes are still created with their canonical label when no prior `node_id` exists.
- **Files modified:** `src/graph/provenance.py`
- **Commit:** ed16347

**2. [Rule 1 - Bug] Test duplicate-edge query included MENTIONED_IN false positives**
- **Found during:** Task 2 test development
- **Issue:** The duplicate-edge detection Cypher used `b.node_id` to group edges. Document nodes use `doc_id` not `node_id`, so all MENTIONED_IN edges appeared as duplicates (b.node_id=NULL). MENTIONED_IN is legitimately multi-valued (one per doc-entity pair).
- **Fix:** Added `WHERE type(r) <> 'MENTIONED_IN'` to `_duplicate_edge_count` helper in the test.
- **Files modified:** `tests/integration/test_batch_ingest_neo4j.py`
- **Commit:** 69361c2

**3. [Rule 1 - Bug] upsert_document import inside function prevented mock patching**
- **Found during:** Task 2 `test_loader_failure_marks_stage_neo4j_load`
- **Issue:** `batch.py` originally imported `upsert_document` inside the function body. The test needed to patch at `src.ingest.batch.upsert_document` but the attribute didn't exist at module level.
- **Fix:** Moved `create_constraints`, `upsert_document`, `load_nodes`, `load_edges`, and `scoped_delete_doc` imports to module level in `batch.py`.
- **Files modified:** `src/ingest/batch.py`
- **Commit:** ed16347

**4. [Rule 1 - Bug] Stage attribution incorrect for neo4j_load failures**
- **Found during:** Task 2 `test_loader_failure_marks_stage_neo4j_load`
- **Issue:** `_run_one_doc` called `ingest_one_doc` which internally ran both extraction AND loading. When loading raised, the exception propagated with `stage` still set to `"extract"`.
- **Fix:** Split extraction and loading into separate steps in `_run_one_doc`: step 2a sets `stage="extract"` and calls `_extract_to_graph_items`; step 2b sets `stage="neo4j_load"` and calls `upsert_document`+`load_nodes`+`load_edges`. The exception is now caught with the correct stage.
- **Files modified:** `src/ingest/batch.py`
- **Commit:** ed16347

## TDD Gate Compliance

| Task | RED commit (`test:`) | GREEN commit (`feat:`) |
|------|----------------------|------------------------|
| 1 (batch.py non-dry-run) | 5f07bdf | ed16347 |
| 2 (integration tests) | 5f07bdf (same RED) | 69361c2 |

## Known Stubs

None — all Plan 03-02 stubs resolved. `--reset` is wired. Non-dry-run path is live.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced. The `merge_node_with_provenance` fix uses parameterized Cypher (`$node_id`) — no string interpolation.

## Self-Check: PASSED

- `src/ingest/batch.py` — FOUND
- `scripts/batch_ingest.py` — FOUND
- `src/graph/provenance.py` — FOUND (contains merge_node_with_provenance pre-check)
- `tests/integration/test_batch_ingest_neo4j.py` — FOUND (8 tests)
- RED commit 5f07bdf — present
- GREEN commit ed16347 — present
- Test commit 69361c2 — present
- 98 tests total pass (90 prior + 8 new)
- Two-run idempotency: 197 nodes, 460 edges both runs — VERIFIED
- BATCH-04 invariant: 0 null source_doc edges — VERIFIED
