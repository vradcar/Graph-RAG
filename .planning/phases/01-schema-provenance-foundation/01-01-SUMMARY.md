---
phase: 01-schema-provenance-foundation
plan: "01"
subsystem: schema
tags: [neo4j, schema, provenance, testing, tdd]
dependency_graph:
  requires: []
  provides: [Document-dataclass, MENTIONED_IN-relation, test-contract-SCHEMA-01-05]
  affects: [src/graph/schema.py, tests/]
tech_stack:
  added: [pytest>=8.0]
  patterns: [TDD-RED-baseline, additive-schema-extension, skip-if-unreachable-fixtures]
key_files:
  created:
    - tests/test_schema.py
    - tests/test_provenance.py
    - tests/conftest.py
    - pytest.ini
    - tests/__init__.py
  modified:
    - src/graph/schema.py
    - requirements.txt
decisions:
  - "D-01: doc_id is a manifest slug string, not a content hash"
  - "D-05: Tests use live local Neo4j with pytest.mark.integration; skip if unreachable"
  - "Additive-only schema changes preserve T9 ingestion non-regression"
metrics:
  duration: "~5 minutes"
  completed: "2026-05-03"
  tasks_completed: 3
  files_modified: 7
requirements: [SCHEMA-01, SCHEMA-02]
---

# Phase 01 Plan 01: Schema + Provenance Test Contract Summary

Added Document dataclass and MENTIONED_IN relation additively to schema.py, installed pytest infrastructure, and committed a failing integration test suite (RED baseline) encoding SCHEMA-01..05 and idempotency expectations for Plan 02 to turn GREEN.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add Document dataclass + MENTIONED_IN to schema.py | 6c03170 | src/graph/schema.py |
| 2 | Install pytest + create test scaffolding | 8ccc4bf | requirements.txt, pytest.ini, tests/__init__.py, tests/conftest.py |
| 3 | Write failing test suites encoding SCHEMA-01..05 + idempotency | f17b314 | tests/test_schema.py, tests/test_provenance.py |

## Schema Additions (exact lines)

`src/graph/schema.py` — additive changes:
```python
# NODE_KIND extended:
NODE_KIND = Literal["Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec", "Document"]

# ALLOWED_RELATIONS extended:
ALLOWED_RELATIONS = Literal[
    "COMPATIBLE_WITH", "REPLACES", "SUPPORTS_WIRING", "HAS_SPEC", "MENTIONED_IN"
]

# New Document dataclass appended:
@dataclass
class Document:
    doc_id: str           # canonical manifest slug, e.g. "t9_install_guide"
    title: str
    sku: Optional[str] = None
    source_url: Optional[str] = None
    ingested_at: Optional[str] = None  # ISO-8601; DB stores as datetime()
```

## Helper-Function Signatures Plan 02 Must Implement

From `tests/test_provenance.py` imports:
```python
from src.graph.provenance import (
    merge_document,            # (tx, doc_dict) -> None
    merge_node_with_provenance, # (tx, node_dict, doc_id: str) -> None
    merge_edge_with_provenance, # (tx, edge_dict, doc_id: str) -> None
)
```

All three functions are called as `session.execute_write(lambda tx: func(tx, ...))`.

## Test Counter

- **5 GREEN unit tests** in `tests/test_schema.py` (pass without Neo4j)
- **8 RED integration tests** in `tests/test_provenance.py` (ImportError on `src.graph.provenance` until Plan 02)

## Deviations from Plan

None — plan executed exactly as written. All artifacts were present from prior commits on the worktree branch.

## Self-Check

- [x] `src/graph/schema.py` contains `class Document` — FOUND
- [x] `tests/conftest.py` contains `pytest.skip` — FOUND
- [x] `tests/test_schema.py` — FOUND (5 tests pass)
- [x] `tests/test_provenance.py` — FOUND (8 tests, RED on ImportError)
- [x] `pytest.ini` registers integration marker — FOUND
- [x] `requirements.txt` contains `pytest>=8.0` — FOUND
- [x] Commits exist: 6c03170, 8ccc4bf, f17b314 — FOUND

## Self-Check: PASSED
