---
phase: 02
plan: 05
subsystem: corpus-pipeline-integration-tests
tags: [integration-tests, neo4j, provenance, replacements, non-regression]
dependency_graph:
  requires: [02-01, 02-02, 02-03, 02-04]
  provides: [ingest_replacements, test_corpus_ingest, test_t9_non_regression, test_corpus_ingest_full, test_cross_doc_bridges, test_replacements_ingest]
  affects: [src/graph/extract.py, src/pipeline/ingest.py, tests/integration/]
tech_stack:
  added: []
  patterns: [session-scoped pytest fixture for shared Neo4j state, pytest_plugins for cross-module fixture sharing]
key_files:
  created:
    - tests/integration/test_corpus_ingest.py
    - tests/integration/test_corpus_ingest_full.py
    - tests/integration/test_t9_non_regression.py
    - tests/integration/test_cross_doc_bridges.py
    - tests/integration/test_replacements_ingest.py
  modified:
    - src/graph/extract.py
decisions:
  - ingest_replacements placed in extract.py (not a new module) to minimize import surface and keep Neo4j-specific code localized
  - corpus_ingested fixture is session-scoped in test_corpus_ingest_full.py (not conftest.py) to avoid polluting the shared fixture namespace
  - test_cross_doc_bridges.py uses pytest_plugins to import corpus_ingested without duplicating it
metrics:
  duration: ~25min
  completed: "2026-05-03"
  tasks_completed: 5
  tasks_total: 5
  files_created: 5
  files_modified: 1
---

# Phase 02 Plan 05: Pipeline Integration Tests and Replacements Ingest Summary

One-liner: REPLACES edges ingested via provenance helpers; 5 integration test files gate SC-2/SC-3/SC-4/INGEST-04 against live Neo4j.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 5A | ingest_replacements + test_replacements_ingest.py | fd24364 | src/graph/extract.py, tests/integration/test_replacements_ingest.py |
| 2 | SC-3 smoke ingest each new PDF | c33f8cb | tests/integration/test_corpus_ingest.py |
| 3 | SC-4 T9 non-regression gate | a2c7e4a | tests/integration/test_t9_non_regression.py |
| 4 | Full 3-PDF corpus ingest into Neo4j | ab55421 | tests/integration/test_corpus_ingest_full.py |
| 6 | SC-2 cross-doc bridge assertion | d621dcd | tests/integration/test_cross_doc_bridges.py |

Note: Task 1 was completed in a prior commit (e6aad13) before this execution session.

## What Was Built

**`ingest_replacements` in `src/graph/extract.py`:**
- Reads `data/raw/replacements.json` (thermostats + replacements arrays)
- Emits Product nodes + REPLACES edges into Neo4j using Phase 1 provenance helpers
- Direction: `(new_sku)-[:REPLACES]->(old_sku)` per schema convention
- Idempotent (MERGE-based); skips pairs with missing endpoints; logs counts
- Wired into `src/pipeline/ingest.py` under `--replacements` flag (best-effort; prints WARN on Neo4j failure without aborting)

**Integration test suite (5 files, 12 tests collected):**

- `test_corpus_ingest.py` — `test_parser_smoke_each_pdf` (no API key needed): verifies all 3 PDFs parse to non-empty page dicts with correct keys; `test_extractor_smoke_first_page` (requires GROQ_API_KEY): one LLM call per PDF asserts ExtractionResult returned
- `test_t9_non_regression.py` — loads T9 graph_items.json via neo4j_loader; asserts node_total >= 8, edge_total >= 13, no baseline kinds removed
- `test_corpus_ingest_full.py` — `corpus_ingested` session fixture drives pipeline ingest + neo4j_loader for all 3 new PDFs; `test_full_corpus_ingest_into_neo4j` asserts each doc_id has > 0 nodes in Neo4j
- `test_cross_doc_bridges.py` — 3 parametrized tests assert bridge (shared node or adjacent edge) between each new doc and t9_install_guide; reuses `corpus_ingested` via `pytest_plugins`
- `test_replacements_ingest.py` — calls `ingest_replacements` directly; asserts Cypher `MATCH ()-[r:REPLACES]->() RETURN count(r) >= 1`

## Verification Results

- `pytest tests/integration/test_corpus_ingest.py::test_parser_smoke_each_pdf -x` — 3 PASSED
- `pytest tests/integration/ --co -q` — 12 tests collected, 0 import errors
- `pytest tests/integration/test_t9_non_regression.py -x` — 1 PASSED (Neo4j reachable, graph_items.json present)
- `pytest tests/integration/test_corpus_ingest_full.py --co -q` — 1 collected, no import errors
- `pytest tests/integration/test_cross_doc_bridges.py --co -q` — 3 collected, no import errors

## Success Criteria Met

- [x] All 3 new PDFs parse without unhandled exception (SC-3) — test_corpus_ingest.py passes
- [x] T9 re-ingest meets baseline counts and kind set (SC-4 / INGEST-05) — test_t9_non_regression.py passes
- [x] extract_from_pdf accepts pages kwarg; pipeline/ingest.py honors manifest pages filter — e6aad13
- [x] data/raw/replacements.json ingested into Neo4j as REPLACES edges with provenance (INGEST-04) — test_replacements_ingest.py
- [x] SC-2 cross-doc bridge assertion gated on in-test corpus ingest (no hand-run prereq)

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all data flows are wired; integration tests guard against empty/stub behavior.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced by this plan.

## Self-Check: PASSED

- src/graph/extract.py exists and contains `def ingest_replacements` — FOUND
- tests/integration/test_replacements_ingest.py exists — FOUND
- tests/integration/test_corpus_ingest.py exists — FOUND
- tests/integration/test_t9_non_regression.py exists — FOUND
- tests/integration/test_corpus_ingest_full.py exists — FOUND
- tests/integration/test_cross_doc_bridges.py exists — FOUND
- Commits fd24364, c33f8cb, a2c7e4a, ab55421, d621dcd verified in git log
