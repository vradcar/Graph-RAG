---
phase: 02-query-pipeline
plan: 02
subsystem: query-pipeline
tags: [query, evaluate, neo4j, cli]
dependency_graph:
  requires: [02-01]
  provides: [query-cli, eval-pipeline]
  affects: [src/pipeline/query.py, src/pipeline/evaluate.py, data/eval/queries.json]
tech_stack:
  added: []
  patterns: [neo4j-context-manager, instructor-client, structured-output]
key_files:
  created: []
  modified:
    - src/pipeline/query.py
    - src/pipeline/evaluate.py
    - data/eval/queries.json
decisions:
  - run_query_structured exposed separately for evaluate.py reuse
metrics:
  duration: 58s
  completed: "2026-04-15"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 02 Plan 02: Query CLI and Evaluation Pipeline Summary

Rewrote query.py and evaluate.py to use Neo4j-backed graph retrieval with LLM entity resolution and structured answer generation; updated demo queries to D-10 T9-focused set.

## Task Results

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rewrite query.py | df64e28 | src/pipeline/query.py |
| 2 | Rewrite evaluate.py + demo queries | 20a8fd5 | src/pipeline/evaluate.py, data/eval/queries.json |

## Changes Made

### Task 1: query.py rewrite
- Removed all networkx GraphStore, SimpleVectorStore, hybrid_retrieve, load_graph_items, build_graph, load_sample_docs references
- Wired Neo4jGraphStore, graph_retrieve, load_all_node_ids, generate_answer, format_answer
- Added `run_query()` (returns formatted string) and `run_query_structured()` (returns QueryAnswer)
- CLI: --question (required) + --depth (default 2), removed --mode and --top-k
- Model comes from settings.yaml only, no hardcoded strings

### Task 2: evaluate.py rewrite + queries.json
- Removed all old imports (build_graph, load_graph_items, SimpleVectorStore, hybrid_retrieve)
- Wired Neo4jGraphStore context manager, graph_retrieve, generate_answer
- Each query result includes: question, depth, answer (prose), evidence, not_found, latency_sec, expected
- Updated queries.json to 3 D-10 queries: accessories, wiring configs, specifications
- Defaults from settings.yaml evaluation section

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED
