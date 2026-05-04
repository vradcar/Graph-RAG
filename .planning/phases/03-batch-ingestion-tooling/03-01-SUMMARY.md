---
phase: 03-batch-ingestion-tooling
plan: 01
subsystem: ingest
tags: [batch, idempotency, provenance, reporting, failure-log, tdd]
requires:
  - src/graph/provenance.py (existing merge_* helpers)
  - src/ingest/manifest.py (load_manifest)
provides:
  - src/graph/provenance.py:scoped_delete_doc
  - src/ingest/batch_report.py:summarize_counts
  - src/ingest/batch_report.py:build_doc_report
  - src/ingest/batch_report.py:capture_warnings
  - src/ingest/failure_log.py:log_failure
affects:
  - scripts/batch_ingest.py (Wave 1 will compose these primitives)
tech-stack:
  added: []
  patterns: ["JSONL append-only failure log", "logging.Handler context manager", "scoped Cypher delete by source_doc"]
key-files:
  created:
    - src/ingest/batch_report.py
    - src/ingest/failure_log.py
    - tests/unit/test_scoped_delete.py
    - tests/unit/test_batch_report.py
    - tests/unit/test_failure_log.py
  modified:
    - src/graph/provenance.py (appended scoped_delete_doc)
decisions:
  - A1 (MENTIONED_IN direction) confirmed implemented as (entity)-[:MENTIONED_IN]->(:Document) — matches merge_node_with_provenance L118
  - JSONL log uses ensure_ascii=False so non-ASCII messages survive verbatim
  - build_doc_report stays pure: caller supplies timestamps + scoped_delete_ran flag
  - capture_warnings defaults to 4 documented loggers; caller can override via kwarg
metrics:
  duration: ~25 minutes
  completed: 2026-05-03
requirements: [BATCH-02, BATCH-03, BATCH-04]
---

# Phase 03 Plan 01: Wave 0 Helpers Summary

**One-liner:** Three pure helpers — scoped Cypher delete by `source_doc`, per-doc batch report builder + warning-capture context manager, and JSONL failure-log appender — fully unit-tested against mocks so Wave 1 can compose them in `scripts/batch_ingest.py` without re-validating primitives.

## What Was Built

### 1. `src/graph/provenance.py:scoped_delete_doc(tx, doc_id) -> dict[str, int]`

5-step Cypher sequence run inside a single `session.execute_write` so partial failure rolls back atomically:

1. Drop business edges with `r.source_doc = $doc_id`
2. Drop `MENTIONED_IN` edges from each entity to `:Document {doc_id: $doc_id}` — direction `(entity)-[:MENTIONED_IN]->(:Document)` matches `merge_node_with_provenance` L118 (A1 verified)
3. Prune `$doc_id` from every node's `source_docs[]` array
4. Detach-delete nodes whose `source_docs` is now empty (excluding `:Document`)
5. Detach-delete the `:Document` node itself

Each step uses `WITH …, count(…) AS c … RETURN c` and the helper wraps `tx.run().single()` in `(rec["c"] if rec else 0)` so empty results return 0 instead of crashing. Returns `{"edges": int, "mentioned_in": int, "nodes_pruned": int, "orphans": int, "document": int}` for the per-doc report.

### 2. `src/ingest/batch_report.py`

Three exports:

- `summarize_counts(graph_items: dict) -> dict` — Counter-based aggregation. Missing `kind` collapses to `"Unknown"`, missing `relation` to `"UNKNOWN"`. No Neo4j read needed — works in `--dry-run`.
- `build_doc_report(*, doc, graph_items, started_at, finished_at, inferencer, model, dry_run, scoped_delete_ran, warnings, error, stage_completed=None) -> dict` — assembles the full Pattern 2 schema with all 14 keys. Status derives from `error` (`"ok"` if None else `"fail"`); `stage_completed` defaults to `"neo4j_load"` on ok, `"extract"` on fail. Accepts both datetime and `time.perf_counter()` timestamps; runtime rounded to 3 decimals; ISO-8601 strings end in `'Z'`.
- `capture_warnings(loggers=DEFAULT_WARNING_LOGGERS) -> ContextManager[list[dict]]` — installs a WARNING-level `logging.Handler` on the four documented loggers (`src.pipeline.ingest`, `src.graph.neo4j_loader`, `src.ingest.entity_extractor`, `src.ingest.normalizer`). Records dict has `{logger, level, message}`. Handlers always removed in `finally` so exceptions inside the block leave the logging tree clean.

### 3. `src/ingest/failure_log.py:log_failure(doc_id, stage, exc, *, log_path=None) -> Path`

Append-only JSONL line per failure. Default path `reports/ingest_failures.log`; `log_path` kwarg lets tests redirect to `tmp_path`. Fields: `ts` (UTC ISO `Z`), `doc_id`, `stage`, `error_class`, `message`, `snippet` (`traceback.format_exc(limit=10)`). Uses `ensure_ascii=False` so non-ASCII messages survive verbatim. Auto-creates parent dir. Returns the path written so callers can echo it in CLI output.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `scoped_delete_doc` lives in `provenance.py` (not a new file) | Follows ARM in 03-RESEARCH.md — sits next to `merge_document` / `merge_node_with_provenance` / `merge_edge_with_provenance` so all write helpers are co-located |
| `build_doc_report` is pure (caller supplies timestamps) | Keeps the helper deterministic and unit-testable; no `datetime.now()` inside |
| `ensure_ascii=False` in JSONL writer | Modern JSONL convention; preserves unicode in extracted product names / specs |
| Default capture loggers as a documented constant | Caller can override for tests or new modules without a code edit |

## Confirmation: A1 (MENTIONED_IN direction)

**Implemented direction matches the loader:** the Cypher in `scoped_delete_doc` step 2 is

```
MATCH (e)-[m:MENTIONED_IN]->(:Document {doc_id: $doc_id})
```

which mirrors `merge_node_with_provenance` L118:

```
MERGE (n)-[m:MENTIONED_IN]->(d)
```

where `d` is the `:Document` node. Test `test_mentioned_in_direction_matches_loader` locks this contract.

## Test Counts

| File | Tests | Status |
|------|-------|--------|
| `tests/unit/test_scoped_delete.py` | 6 | PASS |
| `tests/unit/test_batch_report.py` | 10 | PASS |
| `tests/unit/test_failure_log.py` | 7 | PASS |
| **Total** | **23** | **PASS in 0.12 s** |

(Plan called out 8 batch_report tests; landed with 10 — added `test_summarize_counts_missing_kind_collapses_to_unknown` and `test_capture_warnings_cleans_up_on_exception` for explicit coverage of the two edge cases. Plan called out 21 total; landed at 23.)

Zero Neo4j dependency — every test uses `MagicMock` (scoped delete) or `tmp_path` (failure log) or stdlib logging (capture_warnings).

## Dependencies

**No `requirements.txt` change.** Phase 3 Wave 0 is pure stdlib + already-pinned `neo4j` driver types only (`ManagedTransaction` is a type hint, not a runtime call).

## Deviations from Plan

None — plan executed exactly as written. Only addition is two extra unit tests beyond the 21 specified, both directly supporting the documented behaviour.

## Deferred Issues

None.

## Threat Flags

None — these helpers introduce no new network surface, no new auth paths, and no new write paths (scoped_delete_doc is a delete primitive composed by Wave 1, not an external endpoint).

## Self-Check: PASSED

Verified after writing this SUMMARY (run inside the worktree at `/Users/jsk/Desktop/anthropic/Graph-RAG/.claude/worktrees/agent-a0d62837/`):

- `src/graph/provenance.py` (modified) — FOUND
- `src/ingest/batch_report.py` — FOUND
- `src/ingest/failure_log.py` — FOUND
- `tests/unit/test_scoped_delete.py` — FOUND
- `tests/unit/test_batch_report.py` — FOUND
- `tests/unit/test_failure_log.py` — FOUND
- All commits present on `worktree-agent-a0d62837` branch (b43e936, 43a314d, 3c56ae4, c86b05d, 7028292, 68ed699)
- Final verification: 23 passed in 0.12 s; import smoke test clean

## TDD Gate Compliance

All three tasks followed RED -> GREEN. Per-task commits:

| Task | RED commit (`test:`) | GREEN commit (`feat:`) |
|------|----------------------|------------------------|
| 1 | b43e936 | 43a314d |
| 2 | 3c56ae4 | c86b05d |
| 3 | 7028292 | 68ed699 |

No REFACTOR commits — implementations were minimal-but-complete on first GREEN.
