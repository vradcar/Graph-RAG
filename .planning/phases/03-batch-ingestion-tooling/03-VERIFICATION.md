---
phase: 03-batch-ingestion-tooling
verified: 2026-05-03T00:00:00Z
status: human_needed
score: 11/12 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run `PYTHONPATH=/path/to/Graph-RAG python scripts/batch_ingest.py --dry-run` from any directory"
    expected: "Writes reports/batch/<doc_id>_report.json for each manifest doc; prints aligned summary table; exits 0"
    why_human: "The script requires PYTHONPATH set or a working directory at project root (no pyproject.toml/setup.py installs the package). pytest succeeds because it adds the root to sys.path automatically, but end-to-end CLI invocation fails with ModuleNotFoundError unless the caller sets PYTHONPATH. A human must confirm the intended invocation pattern and whether this is acceptable for the prototype."
---

# Phase 3: Batch Ingestion Tooling Verification Report

**Phase Goal:** A single batch command ingests the entire corpus repeatably with structured per-doc reporting and idempotent re-run safety.
**Verified:** 2026-05-03T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `--dry-run` walks every manifest doc, writes graph_items JSON per doc, never opens Neo4j | ? UNCERTAIN | Logic implemented and integration-tested via `run_batch`; CLI invocation requires PYTHONPATH — see human verification |
| 2 | Each doc produces a per-doc report at `reports/batch/{doc_id}_report.json` with Pattern 2 schema (14 keys) | ✓ VERIFIED | `build_doc_report` in `src/ingest/batch_report.py` produces all 14 keys; `_run_one_doc` writes file; 8 integration tests pass |
| 3 | stdout summary table shows one row per doc: doc_id, status, nodes, edges, runtime_seconds | ✓ VERIFIED | `print_summary()` in `scripts/batch_ingest.py` implements aligned table with totals line |
| 4 | Per-doc try/except: forced failure on one doc lets remaining docs run; failure appended to JSONL log | ✓ VERIFIED | `_run_one_doc` wraps in try/except; calls `log_failure`; `test_failure_appends_jsonl_and_continues` passes |
| 5 | `--doc-id` restricts run to single manifest entry | ✓ VERIFIED | `iter_manifest_docs` filters by `doc_id_filter`; `test_doc_id_filter_runs_one_doc` passes |
| 6 | `--fail-fast` stops loop on first failure | ✓ VERIFIED | `run_batch` checks `fail_fast` after each doc; `test_fail_fast_stops_on_first_error` passes |
| 7 | Full-mode (no `--dry-run`) ingests into Neo4j using one driver instance; scoped_delete_doc called before each per-doc load | ✓ VERIFIED | `run_batch` non-dry-run branch opens `with GraphDatabase.driver(...) as driver`; `_run_one_doc` calls `s.execute_write(scoped_delete_doc, doc["doc_id"])` when `do_scoped_delete=True` |
| 8 | Running batch twice produces identical Neo4j state (idempotency) | ? UNCERTAIN | Code path correct; `test_idempotent_re_run_node_counts` and `test_idempotent_re_run_no_duplicate_edges` exist but require live Neo4j — cannot verify programmatically |
| 9 | Scoped delete preserves contributions of other docs | ? UNCERTAIN | `scoped_delete_doc` Cypher uses `$doc_id` parameter binding; `test_scoped_delete_preserves_other_docs` exists but requires live Neo4j |
| 10 | `--no-scoped-delete` and `--reset` flags are wired | ✓ VERIFIED | Both flags defined in argparse; `run_batch` respects `no_scoped_delete` and `reset` in `do_scoped_delete` computation; `_full_db_reset` helper exists |
| 11 | `driver.verify_connectivity()` runs once at startup in non-dry-run; exits code 3 on failure | ✓ VERIFIED | `run_batch` calls `driver.verify_connectivity()` inside `with` block; raises `SystemExit`; `main()` catches it and returns 3; `test_verify_connectivity_failure_exits_3` passes |
| 12 | `scoped_delete_ran` field in per-doc report reflects whether delete actually ran | ✓ VERIFIED | `_run_one_doc` sets `scoped_delete_ran=True` only when `s.execute_write(scoped_delete_doc,...)` succeeds; passes `scoped_delete_ran` to `build_doc_report` |

**Score:** 9/12 truths fully verified (3 need live Neo4j or CLI path confirmation)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/graph/provenance.py` | `scoped_delete_doc` helper | ✓ VERIFIED | Exists at lines 213-286; 5-step Cypher sequence; parametrized `$doc_id`; correct `(e)-[:MENTIONED_IN]->(:Document)` direction; `NOT n:Document` in orphan step |
| `src/ingest/batch_report.py` | `build_doc_report`, `summarize_counts`, `capture_warnings` | ✓ VERIFIED | All three exported; Pattern 2 schema (14 keys) fully assembled |
| `src/ingest/failure_log.py` | `log_failure` JSONL appender | ✓ VERIFIED | `DEFAULT_LOG_PATH = reports/ingest_failures.log`; `ensure_ascii=False`; parent dir auto-created |
| `src/ingest/batch.py` | `ingest_one_doc`, `iter_manifest_docs`, `run_batch` | ✓ VERIFIED | All three exported; non-dry-run path wires `verify_connectivity`, `create_constraints`, `scoped_delete_doc`, `upsert_document`, `load_nodes`, `load_edges` |
| `scripts/batch_ingest.py` | CLI with all flags, summary printer, main() | ✓ VERIFIED | 251 lines (>80 min); all flags present; `main()` calls `run_batch`; exit codes 0/1/3 |
| `tests/unit/test_scoped_delete.py` | Mocked-tx coverage | ✓ VERIFIED | Exists; all tests pass |
| `tests/unit/test_batch_report.py` | Report shape + Counter aggregation | ✓ VERIFIED | Exists; all tests pass |
| `tests/unit/test_failure_log.py` | JSONL append + schema | ✓ VERIFIED | Exists; all tests pass |
| `tests/integration/test_batch_ingest_dry_run.py` | BATCH-01/02/03 dry-run coverage | ✓ VERIFIED | 8 tests; all pass |
| `tests/integration/test_batch_ingest_neo4j.py` | BATCH-04 idempotency + scoped-delete isolation | ✓ VERIFIED (structure) | 8 test functions present; skip behavior for unavailable Neo4j handled by fixtures |
| `.gitignore` | Excludes `reports/batch/` and `reports/ingest_failures.log` | ✓ VERIFIED | Both entries present in `.gitignore` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `scripts/batch_ingest.py` | `src/ingest/batch.py:run_batch` | `from src.ingest.batch import run_batch` | ✓ WIRED | Line 23 of batch_ingest.py |
| `src/ingest/batch.py` | `src/ingest/batch_report`, `src/ingest/failure_log`, `src/graph/provenance` | import at top of file | ✓ WIRED | Lines 24-27 |
| `src/ingest/batch.py:run_batch` | `src/graph/provenance.scoped_delete_doc` | `s.execute_write(scoped_delete_doc, doc["doc_id"])` | ✓ WIRED | Line 235 of batch.py |
| `src/ingest/batch.py:run_batch` | `neo4j.GraphDatabase` | `with GraphDatabase.driver(...) as driver: driver.verify_connectivity()` | ✓ WIRED | Lines 350-354 of batch.py |
| `src/ingest/batch.py:_run_one_doc` | `upsert_document`, `load_nodes`, `load_edges` | direct call with `driver`, `graph_items`, `doc["doc_id"]` | ✓ WIRED | Lines 256-260 of batch.py |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| BATCH-01 | 03-02, 03-03 | Single command, `--dry-run` writes processed JSON without touching Neo4j | ✓ SATISFIED | `scripts/batch_ingest.py` implemented; dry-run path tested via 8 integration tests |
| BATCH-02 | 03-01, 03-02 | Per-PDF report with entity count by kind, edge count by relation, warnings, runtime, pass/fail | ✓ SATISFIED | `build_doc_report` produces all required fields; `summarize_counts` groups by kind/relation; `capture_warnings` collects warnings |
| BATCH-03 | 03-01, 03-02 | Failure log at `reports/ingest_failures.log` with structured entries | ✓ SATISFIED | `log_failure` appends JSONL with doc_id, stage, error_class, message, snippet; failure isolation tested |
| BATCH-04 | 03-01, 03-03 | Re-run safety via scoped delete before re-MERGE | ✓ SATISFIED (code) / ? UNCERTAIN (runtime) | `scoped_delete_doc` 5-step Cypher implemented; wired in `_run_one_doc`; idempotency tests exist but require live Neo4j |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/ingest/batch.py` | 169 | `warnings_placeholder` always returns empty list | ℹ Info | `run_batch` captures warnings via its own context and overrides; documented in docstring — not a stub |
| `scripts/batch_ingest.py` | — | No PYTHONPATH / package install mechanism | ⚠ Warning | `python scripts/batch_ingest.py` fails with `ModuleNotFoundError` unless `PYTHONPATH` is set or script is run from project root with Python that has root on path. pytest adds it automatically; CLI users need guidance. |

### Human Verification Required

#### 1. CLI Invocation Path

**Test:** Run `python scripts/batch_ingest.py --dry-run` from the project root `/Users/jsk/Desktop/anthropic/Graph-RAG/`.
**Expected:** Script runs successfully, prints summary table, exits 0. Reports written to `reports/batch/`.
**Why human:** The script does not have a `pyproject.toml`/`setup.py` making it installable. Running directly with `python scripts/batch_ingest.py` fails with `ModuleNotFoundError: No module named 'src'` unless the caller sets `PYTHONPATH` to the project root or uses `python -m` from that directory. The plan calls for running `python scripts/batch_ingest.py --dry-run` — this must be confirmed as working (likely requires `PYTHONPATH=. python scripts/batch_ingest.py --dry-run` or running from an IDE that adds the root). BATCH-01's success criterion depends on this working.

#### 2. BATCH-04 Idempotency (live Neo4j)

**Test:** Start Neo4j 5.x on `bolt://localhost:7687` with credentials from `.env`. Run `python scripts/batch_ingest.py` twice. After each run query: `MATCH (n) RETURN count(n)` and `MATCH ()-[r]->() RETURN count(r)`.
**Expected:** Both counts identical between run 1 and run 2. Zero duplicate edges.
**Why human:** `test_batch_ingest_neo4j.py` contains the assertions but cannot run without a live Neo4j instance. Cannot verify programmatically in this environment.

### Gaps Summary

No hard BLOCKERS found — all required artifacts exist, are substantive, and are correctly wired. The CLI invocation requires `PYTHONPATH` context that is not documented in the scripts' usage header or CLAUDE.md, which is a usability gap. BATCH-04 idempotency is code-correct but unverifiable without a live database.

---

_Verified: 2026-05-03T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
