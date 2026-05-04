---
phase: 04-multi-document-quality-verification
plan: "01"
subsystem: data-fixtures
tags: [query-set, corpus, vector-baseline, tdd, quality]
dependency_graph:
  requires:
    - 03-batch-ingestion-tooling  # Neo4j graph populated with 4-PDF corpus
  provides:
    - data/eval/multi_doc_queries.json  # consumed by 04-02 comparison runner
    - data/raw/doc_chunks_corpus.json   # consumed by 04-02 vector-mode baseline
    - tests/unit/test_multi_doc_queries.py  # guards QUALITY-01 invariants
  affects:
    - 04-02  # comparison runner reads both artifacts from this plan
tech_stack:
  added: []
  patterns:
    - pymupdf (fitz) for PDF text extraction (inline python -c invocation, no new module)
    - pytest module-scope fixtures for JSON loaded once per session
key_files:
  created:
    - data/eval/multi_doc_queries.json
    - data/raw/doc_chunks_corpus.json
    - tests/unit/test_multi_doc_queries.py
  modified: []
decisions:
  - "Used RCHT9610WF and THX321WFS3001W tokens in mq03 instead of prose 'T9/T10' so extract_candidate_entities regex resolves at least one graph anchor"
  - "Capped doc_chunks_corpus.json at 8 chunks per PDF (evenly-spaced) to meet the <200KB target while preserving representative coverage"
  - "thp9045_wiring_module restricted to pages 1-4 per manifest notes (trilingual; English only)"
metrics:
  duration: "~8 minutes"
  completed: "2026-05-04"
  tasks_completed: 3
  files_created: 3
---

# Phase 04 Plan 01: Query Set & Corpus Fixture Authoring Summary

**One-liner:** Curated 7 cross-PDF HVAC query set with THP9045/UWP-WALLPLATE/C-WIRE bridges plus 28-chunk per-PDF corpus fixture enabling fair vector-mode baseline in Plan 02.

## What Was Built

### Task 1: data/raw/doc_chunks_corpus.json

Per-PDF text chunks generated from all 4 corpus PDFs using pymupdf (inline python -c invocation — no helper module committed):

| doc_id | Chunks | PDF pages used |
|--------|--------|----------------|
| t9_install_guide | 8 | 1-17 (all) |
| t6_pro_install | 8 | 1-44 (all) |
| thp9045_wiring_module | 4 | 1-4 (English only) |
| t10_pro_user_guide | 8 | 1-36 (all) |
| **Total** | **28** | |

- File size: 41,988 bytes (well under 200KB target)
- Each chunk has `{id: "<doc_id>:chunk-NN", text: "...", source_doc: "<doc_id>"}` shape
- `source_doc` field is passthrough metadata Plan 02 reads for vector-mode coverage calculation
- Legacy `data/raw/doc_chunks.json` untouched

### Task 2: data/eval/multi_doc_queries.json

7 curated cross-PDF questions, each requiring graph traversal across >=2 doc sources:

| id | question summary | source_docs | graph_only |
|----|-----------------|-------------|------------|
| mq01 | THP9045A1023 compatible thermostats | thp9045, t9, t6_pro | true |
| mq02 | UWP-WALLPLATE HVAC types across T9 and T6 Pro | t9, t6_pro | true |
| mq03 | RCHT9610WF shared HVAC types with THX321WFS3001W | t9, t10_pro | false |
| mq04 | THP9045A1023 + RCHT9610WF compatibility | thp9045, t9 | false |
| mq05 | UWP-WALLPLATE accessories across docs | t9, t6_pro, t10_pro | true |
| mq06 | C-WIRE wiring config cross-doc presence | t9, t6_pro, t10_pro | false |
| mq07 | TH1110D replacement + wiring (replacement fallback) | t6_pro, t9 | false |

**Final count:** 7 queries, 3 graph_only=true (satisfies QUALITY-04 precondition of >=2)

### Task 3: tests/unit/test_multi_doc_queries.py

7 invariant tests guarding the query set schema:

1. `test_query_set_has_at_least_6_questions` — file loads, is list, len >= 6
2. `test_every_query_has_required_fields` — all 7 required fields present
3. `test_ids_are_unique` — no duplicate id values
4. `test_expected_source_docs_are_canonical` — doc_ids from manifest.json (not hard-coded)
5. `test_each_query_spans_at_least_two_docs` — >=2 distinct expected_source_docs per query
6. `test_at_least_two_graph_only_questions` — >=2 graph_only=true
7. `test_questions_extract_an_entity_or_trigger_replacement_fallback` — entity extraction or replacement keyword per query

Test runtime: 0.19s. All 7 pass. Zero external dependencies (no Neo4j, no LLM).

## Live Graph Spot-Check Results

Spot-checked all 7 candidate questions against the live Neo4j graph (populated by Phase 3 batch ingest: 212 nodes, 248 edges across 4 PDFs).

Cross-doc bridge verification:
- `thp9045a1023` neighbors include nodes from thp9045_wiring_module, t6_pro_install, t9_install_guide, t10_pro_user_guide
- `uwp-wallplate` is MENTIONED_IN t9_install_guide, t6_pro_install, t10_pro_user_guide
- `c-wire` is MENTIONED_IN t9_install_guide, t6_pro_install, t10_pro_user_guide
- `heat-pump` is MENTIONED_IN all 4 docs
- `rcht9610wf` is MENTIONED_IN t9_install_guide and t10_pro_user_guide

No candidate questions were dropped. All 7 confirmed viable with multi-doc paths in the live graph.

**Note on graph retriever case sensitivity:** `extract_candidate_entities` returns uppercase tokens (e.g., `THP9045A1023`) but `has_node` is case-sensitive against lowercase Neo4j node IDs. The query pipeline's retrieval returns empty context for these questions when using graph mode directly. This is a pre-existing limitation of the graph retriever not introduced by this plan. Plan 02's comparison runner will need to normalize entity lookups, or the current behavior correctly demonstrates graph-mode limits (which is part of the QUALITY-04 comparison story). Documented for Plan 02 executor awareness.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] mq03 question used prose "T9 thermostat" / "T10 Pro thermostat" — regex misses**

- **Found during:** Task 3 — `test_questions_extract_an_entity_or_trigger_replacement_fallback` would have failed
- **Issue:** The original phrasing "T9 thermostat and the T10 Pro thermostat" produces no tokens from `extract_candidate_entities` (no uppercase+hyphen or uppercase+digit patterns)
- **Fix:** Changed question to use canonical SKU codes `RCHT9610WF` and `THX321WFS3001W`
- **Files modified:** `data/eval/multi_doc_queries.json`
- **Commit:** a5fb517

## Confirmation: No src/ Files Modified

```
git diff --name-only HEAD~3 HEAD | grep '^src/'  # returns 0 files
```

Phase 4 deliberately reuses `src/pipeline` and `src/retrieval` as-is per REQUIREMENTS.md OOS section.

## TDD Gate Compliance

Task 3 followed TDD intent: tests were authored to guard the data files created in Tasks 1-2. The standard RED gate (tests failing before implementation) was not applicable here since the data artifacts precede the tests in task order. Tests went directly to GREEN (0.19s, 7 passed). No REFACTOR phase needed.

## Known Stubs

None — data files are fully populated with real content from live PDF extraction and live Neo4j graph verification.

## Threat Flags

None — no network endpoints, auth paths, file access patterns, or schema changes introduced. All artifacts are static JSON data files and a unit test.

## Self-Check: PASSED

- [x] `data/raw/doc_chunks_corpus.json` exists — 28 chunks, 4 doc_ids, 41,988 bytes
- [x] `data/eval/multi_doc_queries.json` exists — 7 queries, 3 graph_only=true
- [x] `tests/unit/test_multi_doc_queries.py` exists — 7 tests, all passing
- [x] Commits verified: 900171d (task1), a5fb517 (task2), 0fbf883 (task3)
- [x] No src/ files modified
- [x] Legacy `data/raw/doc_chunks.json` untouched
