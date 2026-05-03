---
phase: 02-corpus-curation-extractor-hardening
plan: 01
subsystem: ingest-infrastructure
tags: [manifest, test-isolation, baseline-fixture, conftest]
dependency_graph:
  requires: []
  provides:
    - data/raw/manifest.json
    - src/ingest/manifest.py (load_manifest, get_doc)
    - tests/fixtures/t9_baseline.json
    - tests/conftest.py (NEO4J_TEST_URI isolation, idempotent clean_db)
    - tests/regressions/__init__.py
    - tests/integration/__init__.py
  affects:
    - All Phase 2 Wave 1 tasks (manifest loader input)
    - INGEST-05 non-regression gate (baseline fixture)
    - All integration tests (conftest isolation)
tech_stack:
  added: []
  patterns:
    - Per-doc manifest JSON with pages filter for trilingual PDFs
    - NEO4J_TEST_URI env-var preference for test isolation
    - Setup+teardown clean_db fixture (idempotent delete on yield exit)
key_files:
  created:
    - data/raw/manifest.json
    - src/ingest/manifest.py
    - tests/unit/__init__.py
    - tests/unit/test_manifest.py
    - tests/fixtures/__init__.py
    - tests/fixtures/t9_baseline.json
    - tests/regressions/__init__.py
    - tests/integration/__init__.py
  modified:
    - tests/conftest.py
decisions:
  - "Manifest uses pages: [1, 4] (inclusive, 1-indexed) for THP9045 English-only page filter"
  - "clean_db is now setup+teardown — runs DETACH DELETE both before and after each test to prevent left-over nodes from polluting the next session"
  - "NEO4J_TEST_URI preferred over NEO4J_URI in neo4j_driver fixture; chosen var is printed at fixture setup for observability"
metrics:
  duration: ~8 minutes
  completed: "2026-05-03"
  tasks_completed: 3
  tasks_total: 3
  files_created: 8
  files_modified: 1
---

# Phase 02 Plan 01: Wave 0 Prerequisites — Manifest, Baseline, Test Isolation Summary

Wave 0 groundwork for Phase 2: manifest loader, T9 baseline snapshot, and conftest test-isolation fix.

## What Was Built

**Task 1 — manifest.json + manifest loader**

4-entry `data/raw/manifest.json` covering t9_install_guide, t6_pro_install, thp9045_wiring_module, and t10_pro_user_guide. Includes the critical `pages: [1, 4]` filter for the THP9045 trilingual document (English-only pages 1-4; FR/ES translations on pages 5-12 are excluded). `src/ingest/manifest.py` exposes `load_manifest(path)` and `get_doc(doc_id, path)` as the canonical loader API. All Phase 2 Wave 1 tasks consume these helpers.

**Task 2 — T9 v1.0 baseline fixture**

`tests/fixtures/t9_baseline.json` captures the Run 1 baseline from `_t9_baseline.txt` exactly: 8 nodes (Product×3, Accessory×4, Document×1), 13 edges (MENTIONED_IN×7, COMPATIBLE_WITH×5, REPLACES×1). This fixture is the assertion target for INGEST-05 non-regression gate.

**Task 3 — conftest.py isolation + package inits**

`tests/conftest.py` updated: `neo4j_driver` now prefers `NEO4J_TEST_URI` env var over `NEO4J_URI`, and logs the chosen variable at fixture setup. `clean_db` changed from setup-only to setup+teardown — `MATCH (n) DETACH DELETE n` runs both before the test and on yield exit, preventing test-leftover nodes from polluting subsequent sessions (the Phase 1 STATE.md isolation concern is now addressed). Package init files created for `tests/regressions/` and `tests/integration/`.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | ef1191e | feat(02-01): add manifest.json + manifest loader module |
| 2 | 2aa5caf | feat(02-01): snapshot T9 v1.0 baseline as JSON fixture |
| 3 | 1ac6da2 | feat(02-01): test isolation in conftest.py + regressions/integration packages |

## Verification Results

- `pytest tests/unit/test_manifest.py -x` — 5 passed
- `pytest tests/test_provenance.py tests/test_neo4j_store.py --co -q` — 13 tests collected (0 errors)
- `pytest tests/ --co -q --ignore=tests/test_streamlit_app.py` — 54 tests collected (0 errors)
- All acceptance criteria checks passed (manifest 4 entries, pages filter present, loader exports 2 functions)

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — this plan is infrastructure/configuration only; no data flow stubs introduced.

## Pre-existing Issue (Out of Scope)

`tests/test_streamlit_app.py` fails collection with `ModuleNotFoundError: No module named 'streamlit'`. This is a pre-existing environment issue unrelated to this plan. All 54 other tests collect cleanly. Logged to deferred-items for a future plan to add streamlit to dev dependencies.

## Self-Check

File existence checks:
- data/raw/manifest.json — FOUND
- src/ingest/manifest.py — FOUND
- tests/fixtures/t9_baseline.json — FOUND
- tests/regressions/__init__.py — FOUND
- tests/integration/__init__.py — FOUND
- tests/conftest.py (modified) — FOUND

Commit existence checks:
- ef1191e — FOUND
- 2aa5caf — FOUND
- 1ac6da2 — FOUND

## Self-Check: PASSED
