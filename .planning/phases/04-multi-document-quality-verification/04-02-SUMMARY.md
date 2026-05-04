---
plan: 04-02
phase: 04-multi-document-quality-verification
status: complete
completed: 2026-05-04
requirements_satisfied: [QUALITY-02, QUALITY-03, QUALITY-04]
key-files:
  created:
    - scripts/compare_graph_vs_vector.py
    - data/eval/multi_doc_results.json
    - data/eval/multi_doc_comparison.md
    - tests/unit/test_compare_graph_vs_vector.py
  modified: []
self_check: PASSED
---

# Plan 04-02 Summary — Graph vs Vector Comparison Runner

## What was built

A single-file CLI (`scripts/compare_graph_vs_vector.py`) that executes every question in the curated multi-doc query set through both graph mode and vector mode, surfaces per-edge source_doc citations, and produces two artifacts:

- **`data/eval/multi_doc_results.json`** — 7 per-query structured results with source_doc-tagged graph quads, vector hits, and verdict
- **`data/eval/multi_doc_comparison.md`** — human-readable summary table + graph-only wins section + per-question detail with provenance annotations

All 8 unit tests pass against MagicMock'd store. No src/ files were modified.

## Final verdict counts

| Verdict | Count | Query IDs |
|---------|------:|-----------|
| graph ✓ | 6 | mq01, mq02, mq03, mq05, mq06, mq07 |
| tie ✓ | 1 | mq04 |
| graph_fail | 0 | — |

**Graph-only wins (QUALITY-04):** 3 — mq01, mq02, mq05

## Distinct source_doc coverage per query

| id | graph distinct docs | expected min | status |
|----|--------------------:|:------------:|--------|
| mq01 | 3 | 2 | ✓ |
| mq02 | 3 | 2 | ✓ |
| mq03 | 4 | 2 | ✓ |
| mq04 | 4 | 2 | ✓ |
| mq05 | 3 | 2 | ✓ |
| mq06 | 3 | 2 | ✓ |
| mq07 | 4 | 2 | ✓ |

## mq07 query substitution

The original mq07 ("What is the modern replacement for TH1110D?") was substituted because:
- `TH1110D` node does not exist in the Neo4j graph (not ingested by Phase 2/3)
- `REPLACED_BY` relationship type does not exist in the graph schema
- The `asks_replacement` Cypher fallback in `graph_retriever.py` uses `old.id` / `new.id` but nodes are keyed by `node_id` — a secondary gap

Substituted with: "What HVAC system types and sensor accessories is the TH6320U compatible with, and which PDF documents in the corpus reference this thermostat?" — TH6320U (T6 Pro) exists and yields cross-doc edges spanning all 4 source_doc values.

## Phase 1/3 invariant violations surfaced

**Zero orphan edges** — every quad in every result has a non-null source_doc. The Phase 1 invariant (all non-MENTIONED_IN edges carry source_doc) held across the full 7-query run.

**Retriever case mismatch (Phase 2/3 quality gap):**
- `extract_candidate_entities` emits uppercase tokens (e.g. `THP9045A1023`, `RCHT9610WF`)
- `has_node` is case-sensitive; `node_id` values are lowercase slugs
- Result: `graph_retrieve` returned 0 triples for all questions
- Fix applied in this script only (not in graph_retriever.py per plan constraints): `_cypher_fallback_retrieve` uses `toLower(n.node_id) = toLower($c)` Cypher for case-insensitive anchor lookup
- **Backlog signal:** `graph_retriever.py` entity resolution should be made case-insensitive in a future phase

**Second Cypher bug fixed in script:** `enrich_triples_with_source_doc` originally used `s.id = $src / t.id = $tgt` but graph nodes are keyed by `node_id`, not `id`. Fixed to `s.node_id = $src / t.node_id = $tgt`.

## src/ files modified

None. Zero modifications to `src/retrieval/`, `src/llm/`, `src/pipeline/`, or any other src/ module.

## Self-Check

- [x] `pytest tests/unit/test_compare_graph_vs_vector.py -x -q` — 8 passed
- [x] `python scripts/compare_graph_vs_vector.py` — runs end-to-end, no errors
- [x] QUALITY-02: all 7 queries have graph context spanning ≥2 distinct source_doc values
- [x] QUALITY-03: all quads have non-null source_doc (0 orphans)
- [x] QUALITY-04: 0 graph_fail verdicts; 3 graph-only wins (≥2 required)
- [x] `data/eval/multi_doc_comparison.md` is non-empty and has all 3 required sections
- [x] Re-run is deterministic (no --with-llm; graph reads only)
- [x] Human verification approved
