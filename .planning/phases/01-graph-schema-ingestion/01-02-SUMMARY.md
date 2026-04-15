---
phase: 01-graph-schema-ingestion
plan: "02"
subsystem: graph-store
tags: [neo4j, graph, cypher, idempotency, unit-tests]
dependency_graph:
  requires: []
  provides: [Neo4jGraphStore, GraphStore]
  affects: [src/pipeline/ingest.py, src/retrieval/graph_retriever.py]
tech_stack:
  added: [neo4j==5.28.1 (driver), unittest.mock (test isolation)]
  patterns: [MERGE-keyed-on-node_id, IF-NOT-EXISTS-constraints, context-manager-store, monkeypatched-driver-tests]
key_files:
  created: [tests/__init__.py, tests/test_neo4j_store.py]
  modified: [src/graph/store.py]
decisions:
  - "kind/relation strings are interpolated into Cypher f-strings (validated Literal types) while all node_id values are always passed as parameters"
  - "Original GraphStore (networkx) preserved intact for offline unit tests"
  - "VALID_KINDS imported from schema.py with fallback inline set if schema.py has not yet been updated by plan 01-01"
metrics:
  duration: "~5 minutes"
  completed: "2026-04-15"
  tasks_completed: 2
  files_changed: 3
requirements: [GRAPH-07]
---

# Phase 01 Plan 02: Neo4j Graph Store Summary

Neo4jGraphStore replacing networkx GraphStore with MERGE-keyed writes, 5 IF NOT EXISTS uniqueness constraints, and 5 passing unit tests using monkeypatched driver.

## What Was Built

### Classes Implemented

**`Neo4jGraphStore`** (`src/graph/store.py`)

| Method | Signature | Notes |
|--------|-----------|-------|
| `__init__` | `(uri: str, user: str, password: str)` | Calls `verify_connectivity()`; raises `RuntimeError` with Docker hint if unreachable |
| `setup_constraints` | `() -> None` | Creates 5 `IF NOT EXISTS` uniqueness constraints on `node_id` per label |
| `upsert_node` | `(node_id: str, kind: str, **attributes) -> None` | `MERGE (n:{kind} {node_id: $node_id}) SET n += $props` |
| `upsert_edge` | `(source_id: str, target_id: str, relation: str, **attributes) -> None` | `MERGE (a)-[r:{relation}]->(b)` with parameterized src/tgt |
| `neighbors_multi_hop` | `(start_node: str, depth: int = 1) -> List[Tuple[str, str, str]]` | BFS via Cypher `[*1..$depth]` path query |
| `node_payload` | `(node_id: str) -> Dict` | Returns all node properties or `{}` |
| `has_node` | `(node_id: str) -> bool` | `count(n) > 0` check |
| `close` | `() -> None` | Closes driver |
| `__enter__` / `__exit__` | context manager | Calls `close()` on exit |

**`GraphStore`** (`src/graph/store.py`) — preserved unchanged (networkx-backed).

## Cypher Injection Mitigation

The threat model identified two trust boundaries:

1. **node_id/property values** — always passed as `$node_id`, `$src`, `$tgt`, `$props` parameters via the neo4j driver. Never interpolated into the Cypher string.

2. **kind/relation strings** — interpolated directly into the Cypher f-string (e.g., `MERGE (n:{kind} ...)`). These are validated against `VALID_KINDS` / `VALID_RELATIONS` enums defined in `schema.py` before reaching the store. The store trusts that callers (EntityNode/RelationEdge) enforce the closed-world constraint.

This approach satisfies T-02-01 and T-02-02 from the threat register.

## Test Results

```
tests/test_neo4j_store.py .....  5 passed in 0.37s
```

| Test | Coverage |
|------|----------|
| `test_upsert_node_calls_merge` | Verifies MERGE Cypher with `$node_id` parameter |
| `test_upsert_edge_calls_merge` | Verifies MERGE Cypher for edge upsert |
| `test_setup_constraints_creates_five` | Exactly 5 `session.run()` calls, all containing `IF NOT EXISTS` |
| `test_connectivity_error_raises_runtime_error` | `ServiceUnavailable` → `RuntimeError` with docker hint |
| `test_graphstore_neighbors` | Original `GraphStore.neighbors_multi_hop()` BFS with depth=2 |

No live Neo4j connection required — all driver calls are monkeypatched with `unittest.mock`.

## Deviations from Plan

**1. [Rule 3 - Blocking] neo4j driver not installed in active Python environment**

- **Found during:** Task 1 verification
- **Issue:** `ModuleNotFoundError: No module named 'neo4j'` — the package is pinned in `requirements.txt` but the active Python environment (system Python 3.13.1) had no virtualenv with requirements installed.
- **Fix:** Ran `pip install neo4j==5.28.1` to make the driver available for verification and test runs.
- **Impact:** No code change required; environment setup only.

**2. [Observation] VALID_KINDS not yet in schema.py**

- **Found during:** Task 1 implementation
- **Issue:** Plan 01-01 (schema.py update) had not yet been executed, so `from src.graph.schema import VALID_KINDS` would fail.
- **Fix:** The plan already specified a try/except fallback with an inline set — implemented as designed. No deviation needed.

## Known Stubs

None — `Neo4jGraphStore` is a complete implementation. All methods make real Cypher calls through the driver.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes beyond those specified in the plan's threat model.

## Self-Check

- [x] `src/graph/store.py` exists and contains `Neo4jGraphStore` and `GraphStore`
- [x] `tests/__init__.py` exists
- [x] `tests/test_neo4j_store.py` exists with 5 tests
- [x] Commit `6dc3805` exists (Task 1: feat — store.py)
- [x] Commit `7af7760` exists (Task 2: test — test_neo4j_store.py)

## Self-Check: PASSED
