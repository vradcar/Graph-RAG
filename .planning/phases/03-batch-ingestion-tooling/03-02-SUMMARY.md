---
phase: 03-batch-ingestion-tooling
plan: 02
subsystem: ingest
tags: [batch, cli, dry-run, failure-isolation, tdd, BATCH-01, BATCH-02, BATCH-03]
requires:
  - src/ingest/batch_report.py (build_doc_report, capture_warnings, summarize_counts — Plan 03-01)
  - src/ingest/failure_log.py (log_failure — Plan 03-01)
  - src/ingest/manifest.py (load_manifest, get_doc)
  - data/processed/_*_corpus.json (Phase 2 cached extractions)
provides:
  - src/ingest/batch.py:ingest_one_doc
  - src/ingest/batch.py:iter_manifest_docs
  - src/ingest/batch.py:run_batch
  - scripts/batch_ingest.py (CLI entry point)
affects:
  - scripts/batch_ingest.py (Plan 03-03 wires non-dry-run Neo4j path)
  - src/ingest/batch.py (Plan 03-03 replaces NotImplementedError with live loader)
tech-stack:
  added: []
  patterns:
    - "per-doc try/except boundary — loop continues on failure, fail_fast opt-in"
    - "argparse.ArgumentParser.parse_args monkeypatching for in-process ingest calls"
    - "PYTHONPATH env injection for subprocess-based CLI tests"
key-files:
  created:
    - src/ingest/batch.py
    - scripts/batch_ingest.py
    - tests/integration/test_batch_core.py
    - tests/integration/test_batch_ingest_cli.py
    - tests/integration/test_batch_ingest_dry_run.py
  modified:
    - .gitignore (added reports/batch/ and reports/ingest_failures.log exclusions)
decisions:
  - Ingest called in-process via argparse.Namespace + monkeypatched parse_args (avoids subprocess overhead and env propagation issues)
  - Non-dry-run branch raises NotImplementedError with explicit pointer to Plan 03-03 (clean handoff)
  - CLI subprocess tests inject PYTHONPATH env var (no sys.path mutation needed in script itself)
  - Task 3 TDD tests were written as RED gate but passed immediately because batch.py was already implemented in Task 1 — documented in TDD Gate Compliance section
metrics:
  duration: ~20 minutes
  completed: 2026-05-03
requirements: [BATCH-01, BATCH-02, BATCH-03]
---

# Phase 03 Plan 02: Batch Ingest CLI + Orchestration Core Summary

**One-liner:** `scripts/batch_ingest.py --dry-run` orchestrates all 4 manifest docs through in-process extraction with per-doc try/except isolation, writes Pattern 2 JSON reports and a stdout summary table, logs failures as JSONL — no Neo4j required for verification.

## CLI Surface Delivered

```
scripts/batch_ingest.py
  [--dry-run]              # writes per-doc JSON, skips Neo4j entirely (BATCH-01)
  [--doc-id SLUG]          # restrict to one manifest entry while using batch reporting
  [--inferencer {groq,openrouter,gemini}]   # LLM backend selection
  [--force]                # bypass extraction cache
  [--no-scoped-delete]     # skip scoped delete in non-dry-run (Plan 03-03)
  [--report-dir PATH]      # default reports/batch/
  [--manifest PATH]        # default data/raw/manifest.json
  [--fail-fast]            # default off; stops on first failure when set
  [--verbose]              # enable INFO-level logging
  [--reset]                # NOT YET IMPLEMENTED; stub accepted for future Plan 03-03
```

Exit codes: `0` = all ok, `1` = any failure, `2` = non-dry-run (Plan 03-03 message).

## run_batch Return Shape

```python
[
  {
    "doc_id": str,
    "filename": str,
    "started_at": str,       # ISO-8601 UTC Z
    "finished_at": str,      # ISO-8601 UTC Z
    "runtime_seconds": float,
    "status": "ok" | "fail",
    "stage_completed": "extract" | "neo4j_load",
    "inferencer": str | None,
    "model": str | None,
    "dry_run": bool,
    "scoped_delete_ran": bool,
    "counts": {
      "nodes_total": int,
      "edges_total": int,
      "nodes_by_kind": {kind: int},
      "edges_by_relation": {relation: int},
    },
    "warnings": list[dict],
    "error": dict | None,    # {class, message, traceback_snippet} on failure
  },
  ...  # one per doc
]
```

## End-to-End Dry-Run Results

```
doc_id                           status     nodes   edges  runtime_s
-------------------------------- -------- ------- ------- ----------
t9_install_guide                 ok            35      26      0.004
t6_pro_install                   ok           110     150      0.002
thp9045_wiring_module            ok            17      20      0.001
t10_pro_user_guide               ok            50      52      0.001

summary: 4 ok / 0 fail / 0 skipped
```

## BATCH-01/02/03 Verification (No Neo4j Required)

| Requirement | How Verified |
|-------------|-------------|
| BATCH-01: `--dry-run` end-to-end, no Neo4j | `test_dry_run_does_not_touch_neo4j` — monkeypatches `neo4j.GraphDatabase.driver` to raise; run_batch completes |
| BATCH-01: single command, all 4 docs | `test_dry_run_walks_all_manifest_docs` + end-to-end CLI run |
| BATCH-02: per-doc reports with 14-key Pattern 2 schema | `test_report_schema_matches_pattern_2` — asserts all 14 keys + type checks |
| BATCH-02: stdout summary table | `test_print_summary_outputs_header_and_totals` + CLI end-to-end |
| BATCH-03: failure isolation, loop continues | `test_failure_appends_jsonl_and_continues` — monkeypatches one doc to fail |
| BATCH-03: JSONL log written | `mock_log.call_count == 1` assertion with `mock_log.call_args[0][0] == "t6_pro_install"` |
| BATCH-03: `--fail-fast` stops on first failure | `test_fail_fast_stops_on_first_error` — asserts `len(reports) == 1` |
| `--doc-id` restricts to single doc | `test_doc_id_filter_runs_single_doc` + `test_doc_id_filter_runs_one_doc` |
| Unknown `--doc-id` lists available doc_ids | `test_unknown_doc_id_lists_available` |

## BATCH-04 and Non-Dry-Run Branch

BATCH-04 (idempotent re-runs against live Neo4j) is NOT wired in this plan. The non-dry-run branch in `run_batch` and `ingest_one_doc` raises `NotImplementedError` with an explicit pointer to Plan 03-03. The script exits with code 2 and prints a clear message instructing the user to use `--dry-run`.

Plan 03-03 will:
1. Replace the `NotImplementedError` branch in `run_batch` with `GraphDatabase.driver(...)` init
2. Wire `scoped_delete_doc` from `src.graph.provenance` into `ingest_one_doc` when `scoped_delete=True`
3. Call the existing `src.graph.neo4j_loader` load path for each doc

## Test Counts and Runtime

| File | Tests | Runtime | Status |
|------|-------|---------|--------|
| `tests/integration/test_batch_core.py` | 13 | — | PASS |
| `tests/integration/test_batch_ingest_cli.py` | 8 | 0.19s | PASS |
| `tests/integration/test_batch_ingest_dry_run.py` | 8 | 0.13s | PASS |
| **Integration subtotal** | **29** | **0.32s** | **PASS** |
| `tests/unit` (all) | 61 | ~0.35s | PASS |
| **Grand total** | **90** | **0.35s** | **PASS** |

## Deviations from Plan

### Auto-fixed Issues

None required.

### Minor Adjustments

**Task 3 TDD pre-pass:** The plan's Task 3 tests were intended as a RED gate, but because `batch.py` was already fully implemented by Task 1, the integration tests in `test_batch_ingest_dry_run.py` passed immediately without a RED phase. This is expected — Task 3's purpose is coverage, not new functionality. The RED/GREEN cycle was properly observed for Tasks 1 and 2.

**CLI subprocess PYTHONPATH:** The CLI test harness uses `PYTHONPATH=WORKTREE` env injection rather than relying on `python -m scripts.batch_ingest` module invocation. This avoids adding a `__main__.py` to `scripts/` and keeps the test pattern consistent with subprocess testing.

## Known Stubs

| Stub | File | Line | Reason |
|------|------|------|--------|
| Non-dry-run `NotImplementedError` | `src/ingest/batch.py` | ~100, ~160 | Intentional — Plan 03-03 wires the live Neo4j path |
| `--reset` flag no-op | `scripts/batch_ingest.py` | argparse | Accepted but not implemented per plan note; Plan 03-03 scope |

## Threat Flags

None — this plan introduces no new network endpoints, auth paths, or trust boundaries. The CLI is a local tool that writes to local filesystem paths only.

## Self-Check: PASSED

Verified after writing this SUMMARY:

- `src/ingest/batch.py` — FOUND
- `scripts/batch_ingest.py` — FOUND
- `tests/integration/test_batch_core.py` — FOUND
- `tests/integration/test_batch_ingest_cli.py` — FOUND
- `tests/integration/test_batch_ingest_dry_run.py` — FOUND
- `.gitignore` excludes `reports/batch/` and `reports/ingest_failures.log` — VERIFIED
- Commits: 083b876, 13ee5f1, bd94c3c, acee2c8, dad68bd — all present
- 90 tests pass in 0.35s

## TDD Gate Compliance

| Task | RED commit (`test:`) | GREEN commit (`feat:`) |
|------|----------------------|------------------------|
| 1 (batch.py core) | 083b876 | 13ee5f1 |
| 2 (scripts/batch_ingest.py) | bd94c3c | acee2c8 |
| 3 (integration tests) | N/A — tests written after impl; implementation existed from Task 1 | dad68bd |
