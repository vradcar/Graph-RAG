---
phase: 02-query-pipeline
plan: 01
subsystem: retrieval-and-generation
tags: [graph-retriever, llm-generation, entity-resolution, cypher]
dependency_graph:
  requires: [src/llm/provider.py, src/graph/store.py]
  provides: [graph_retrieve, generate_answer, QueryAnswer, EntityResolution]
  affects: [src/pipeline/query.py]
tech_stack:
  added: [instructor, pydantic]
  patterns: [structured-llm-output, per-relation-cypher, entity-resolution]
key_files:
  created: []
  modified:
    - src/retrieval/graph_retriever.py
    - src/llm/generate.py
decisions:
  - Undirected Cypher patterns for relationship queries to catch both edge directions
  - 200-node cap on load_all_node_ids to prevent prompt bloat
  - Empty triples short-circuit returns not_found QueryAnswer without LLM call
metrics:
  duration: 67s
  completed: "2026-04-15"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 02 Plan 01: Graph Retriever and Answer Generator Summary

LLM-backed entity resolution with per-relation Cypher queries and instructor-structured answer generation.

## Task Summary

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rewrite graph_retriever.py | ab1b201 | src/retrieval/graph_retriever.py |
| 2 | Rewrite generate.py | 2403ddf | src/llm/generate.py |

## What Changed

### graph_retriever.py (full rewrite)
- Removed regex-based `extract_candidate_entities` and old `graph_retrieve`
- Added `EntityResolution` Pydantic model for structured LLM output
- Added `load_all_node_ids()` with 200-node safety cap
- Added `resolve_entities()` using instructor client
- Added `RELATION_QUERIES` dict with 4 undirected Cypher patterns (COMPATIBLE_WITH, REPLACES, SUPPORTS_WIRING, HAS_SPEC)
- Added `retrieve_graph_context()` combining per-relation queries + BFS multi-hop with deduplication
- Added `graph_retrieve()` entry point with `has_node()` validation and stderr logging for filtered IDs

### generate.py (full rewrite)
- Removed stub implementation
- Added `EvidenceTriple` and `QueryAnswer` Pydantic models
- Added `ANSWER_SYSTEM_PROMPT` for graph-grounded answers
- Added `generate_answer()` with empty-triples short circuit and instructor `response_model=QueryAnswer`
- Added `format_triples()` and `format_answer()` for human-readable output

## Deviations from Plan

None - plan executed exactly as written.

## Threat Model Compliance

- T-02-01 (Injection): Mitigated. All Cypher queries use parameterized `$node_id`. Resolved IDs validated via `store.has_node()`.
- T-02-02 (Info Disclosure): Accepted per plan.
- T-02-03 (Spoofing): Accepted per plan. LLM output filtered against known node set.

## Known Stubs

None.

## Self-Check: PASSED
