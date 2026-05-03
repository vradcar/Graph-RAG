---
phase: 01-schema-provenance-foundation
reviewed: 2026-05-02T15:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - pytest.ini
  - requirements.txt
  - src/graph/schema.py
  - src/graph/provenance.py
  - src/graph/neo4j_loader.py
  - tests/__init__.py
  - tests/conftest.py
  - tests/test_provenance.py
  - tests/test_schema.py
findings:
  critical: 4
  warning: 5
  info: 3
  total: 12
status: fixes_applied
---

# Phase 01: Code Review Report

**Reviewed:** 2026-05-02T15:00:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Reviewed the schema-provenance foundation layer: `schema.py`, `provenance.py`, `neo4j_loader.py`, the test suite, and supporting config. The core data model and Cypher MERGE patterns are structurally sound — injection is prevented, idempotency logic is correct, and the parallel-evidence-edge design is well-implemented.

Four blockers were found: `merge_node_with_provenance` and `merge_edge_with_provenance` do not guard against `None` IDs and will silently corrupt the graph or quietly drop data; the `MATCH (d:Document)` step inside `merge_node_with_provenance` fails silently when the Document node is absent (violating the stated audit invariant with no error); and `merge_document` crashes at runtime when `ingested_at` is an empty string due to `datetime("")` being rejected by Neo4j.

Five warnings cover the constraint coverage gap for `WiringConfig` and `Spec`, the misleading `--verify` CLI documentation, a vacuous assertion in `test_document_upsert`, the `except Exception` swallowing real bugs in `conftest.py`, and the `_clean_props` duplication that creates a silent divergence risk.

---

## Critical Issues

### CR-01: `merge_node_with_provenance` does not guard against `None` node_id — creates null-keyed nodes

**File:** `src/graph/provenance.py:101-136`

**Issue:** `node_id = node.get("node_id") or node.get("id")` returns `None` when both keys are absent or both are falsy. There is no guard; execution continues and `props["node_id"] = None` is set (line 111). The Cypher `MERGE (n:{safe_label} {node_id: $node_id})` then runs with `node_id=null`. In Neo4j, `MERGE` on a property with a `null` value will match or create a node where `node_id` is absent/null — which can match any other node that also lacks `node_id`. Repeated ingestion of different nodes without IDs will all MERGE into the same null-keyed node and silently overwrite each other's properties. `neo4j_loader.load_nodes` does guard (line 138-139) before calling this helper, but `merge_node_with_provenance` is a public API that can be called directly.

**Fix:**
```python
# provenance.py — add guard at line 101
node_id = node.get("node_id") or node.get("id")
if not node_id:
    raise ValueError(f"merge_node_with_provenance requires a non-empty node_id; got: {node!r}")
```

---

### CR-02: `merge_edge_with_provenance` silently drops the edge when either endpoint node does not exist

**File:** `src/graph/provenance.py:167-178`

**Issue:** The Cypher uses `MATCH (a {node_id: $source_id})` followed by `MATCH (b {node_id: $target_id})`. If either node is not found, both MATCHes produce an empty row set. The subsequent `MERGE` is never evaluated — the edge is not written, no exception is raised, and `tx.run()` returns without error. Back in `neo4j_loader.load_edges`, the `loaded` counter increments as if the edge was written (line 202: `loaded += 1` runs unconditionally). The caller has no signal that the edge was silently discarded.

This is the expected failure mode when `load_edges` is called before `load_nodes` completes, or when the source JSON references a node that was skipped for another reason.

**Fix:**
```python
# provenance.py — check result rowcount after the MERGE
result = tx.run(
    f"""
    MATCH (a {{node_id: $source_id}})
    MATCH (b {{node_id: $target_id}})
    MERGE (a)-[r:{safe_rel} {{source_doc: $doc_id}}]->(b)
    ON CREATE SET r += $props, r.created = timestamp()
    ON MATCH  SET r += $props, r.updated = timestamp()
    RETURN count(r) AS written
    """,
    source_id=source_id,
    target_id=target_id,
    props=props,
    doc_id=doc_id,
)
row = result.single()
if row is None or row["written"] == 0:
    raise ValueError(
        f"merge_edge_with_provenance: endpoint node not found "
        f"(source_id={source_id!r}, target_id={target_id!r})"
    )
```
Callers that want soft failure should catch `ValueError` and log/skip.

---

### CR-03: `merge_node_with_provenance` silently skips the `MENTIONED_IN` edge when the `:Document` node is absent

**File:** `src/graph/provenance.py:127-132`

**Issue:** After the `MERGE (n:...)` block, the query continues with:
```cypher
WITH n
MATCH (d:Document {doc_id: $doc_id})
MERGE (n)-[m:MENTIONED_IN]->(d)
```
If `merge_document` was not called first (or its transaction was not committed), `MATCH` returns zero rows. `WITH n` then passes nothing to the `MERGE`, which is silently skipped. The function returns without error, but the `MENTIONED_IN` edge is never created. This directly violates the stated audit invariant:
```
MATCH ()-[r]->() WHERE type(r) <> 'MENTIONED_IN' AND r.source_doc IS NULL RETURN count(r)
```
The design note in the module docstring acknowledges this ordering requirement but relies entirely on caller discipline — there is no enforcement and no failure signal when the precondition is violated.

**Fix:** Add a `RETURN count(m)` at the end of the query and raise if the count is 0:
```python
result = tx.run(
    f"""
    ...
    WITH n
    MATCH (d:Document {{doc_id: $doc_id}})
    MERGE (n)-[m:MENTIONED_IN]->(d)
    ON CREATE SET m.first_mentioned = timestamp()
    RETURN count(m) AS mi_count
    """,
    ...
)
row = result.single()
if row is None or row["mi_count"] == 0:
    raise ValueError(
        f"merge_node_with_provenance: :Document {{doc_id: {doc_id!r}}} not found. "
        "Call merge_document in a committed transaction before ingesting nodes."
    )
```

---

### CR-04: `merge_document` crashes with a Neo4j runtime error when `ingested_at` is an empty string

**File:** `src/graph/provenance.py:80`

**Issue:** `ingested_at=doc.get("ingested_at", "")` falls back to `""` when the key is absent. Neo4j's `datetime("")` raises `Text cannot be parsed to a DateTime` — a runtime exception propagated through `execute_write`. The key-present-but-`None` case is safer: `doc.get("ingested_at", "")` returns `None` when the key exists with value `None` (because the default is never used), and `datetime(null)` evaluates to `null` in Cypher without error. But any caller that omits the key entirely — including direct callers of the public helper — will trigger the crash.

The `neo4j_loader.main()` always sets `ingested_at` via `datetime.now(timezone.utc).isoformat()`, so the CLI path is safe. The integration tests in `conftest.py` also populate the field. The risk is any programmatic caller (e.g., a future extraction pipeline) that builds a doc dict without `ingested_at`.

**Fix:**
```python
# provenance.py line 80
ingested_at=doc.get("ingested_at") or None,
```
`or None` converts both absent-key (`""` default) and explicit `None` to `None`, which Cypher handles safely.

---

## Warnings

### WR-01: `WiringConfig` and `Spec` are missing from `create_constraints` — MERGE race-safety not guaranteed

**File:** `src/graph/neo4j_loader.py:76-93`

**Issue:** `VALID_KINDS` in `schema.py` includes `WiringConfig` and `Spec`. The hard-coded `labels` list in `create_constraints` does not include either. Without a `REQUIRE n.node_id IS UNIQUE` constraint, Neo4j does not create an index on `node_id` for those labels, and the MERGE is not atomic under concurrent writes — parallel transactions can each see no existing node and both create one. The MERGE dedup guarantee breaks.

Additionally, `"Document"` appears in the `labels` list (line 79), which creates a `constraint_document_node_id` constraint. `merge_document` never sets `node_id` on Document nodes — it uses `doc_id` as the identity key. The `constraint_document_node_id` constraint is therefore applied to a property that is never set, making it dead weight. The separate `constraint_document_doc_id` constraint added on line 89-91 is the correct one.

**Fix:**
```python
# neo4j_loader.py — replace labels list
labels = [
    "Thermostat", "HVACSystemType", "WiringTerminal", "RoomSensor",
    "Adapter", "ElectricalSpec", "OperatingRange", "ZoningPanel",
    "Wallplate", "Product", "Accessory", "WiringConfig", "Spec",
    # "Document" removed — Document uniqueness is on doc_id, not node_id (see below)
]
```

---

### WR-02: `--verify` is documented as usable standalone but always requires the input file to exist

**File:** `src/graph/neo4j_loader.py:24, 285-290`

**Issue:** The module docstring shows:
```
# Quick verification: print node/edge counts after load
python -m src.graph.neo4j_loader --doc-id t9_install_guide --verify
```
This implies `--verify` can be run without loading data. However, `main()` unconditionally checks `if not input_path.exists(): raise SystemExit(...)` before branching on `--verify`. Running the documented command without the default `data/processed/graph_items.json` present raises `SystemExit: Input not found`. The user intent (inspect a live database) is defeated.

**Fix:** Move the file existence check inside the non-verify branch:
```python
if not args.verify or ...:  # only check file if we're going to load
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")
```
Or more cleanly: skip the load steps when `--verify` is passed without `--input`:
```python
if args.verify and not Path(args.input).exists() and args.input == "data/processed/graph_items.json":
    # verify-only mode: skip file load
    ...
```

---

### WR-03: `test_document_upsert` assertion on `first_ingested` passes vacuously if the property is absent

**File:** `tests/test_provenance.py:32-40`

**Issue:** The test reads `first_ingested = node.get("first_ingested")` from the first write result, then asserts `node2.get("first_ingested") == first_ingested` after the second write. If `first_ingested` is `None` on both reads (e.g., due to a property name typo in the Cypher or a silent Cypher failure), both sides equal `None` and the assertion passes — incorrectly signalling correctness. The test's stated purpose ("preserved on re-ingest") requires proving the value is non-null in the first place.

The test also never asserts that `last_reingested` is set after the second upsert, leaving the `ON MATCH` branch entirely unverified.

**Fix:**
```python
first_ingested = node.get("first_ingested")
assert first_ingested is not None, "first_ingested must be set on CREATE"
# ... second upsert ...
node2 = result2["d"]
assert node2.get("first_ingested") == first_ingested, "first_ingested must be preserved on re-ingest"
assert node2.get("last_reingested") is not None, "last_reingested must be set on MATCH"
```

---

### WR-04: `conftest.py` swallows all exceptions — programming bugs in the fixture masked as skips

**File:** `tests/conftest.py:21-22`

**Issue:** The bare `except Exception: pytest.skip(...)` on line 21 catches `ImportError`, `AttributeError`, `TypeError`, and any other programming error in the fixture body, converting them into silent test skips. If the `neo4j` package API changes, a bug is introduced in the fixture code, or an unexpected import fails, the entire integration test suite silently disappears from the results rather than failing loudly.

**Fix:** Catch only the expected connectivity exceptions:
```python
from neo4j.exceptions import ServiceUnavailable, AuthError

try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    yield driver
    driver.close()
except (ServiceUnavailable, AuthError, OSError):
    pytest.skip("Neo4j not reachable")
# All other exceptions propagate as test errors
```

---

### WR-05: `_clean_props` is duplicated verbatim in `provenance.py` and `neo4j_loader.py`

**File:** `src/graph/neo4j_loader.py:96-112` and `src/graph/provenance.py:38-50`

**Issue:** The two implementations are identical today. `neo4j_loader.load_nodes` calls its own `_clean_props` to produce `extra_props`, then packages the result as `node_dict["properties"]`, which `merge_node_with_provenance` passes through its own `_clean_props` a second time. Any future change to property serialization rules (e.g., adding `datetime` support, handling `bytes`, changing how empty lists are treated) must be applied in both files. A divergence between the two copies would produce different serialization behavior depending on which call path is used, causing silent data inconsistency.

**Fix:** Extract to a single location, e.g. `src/graph/utils.py`, and import from both modules:
```python
# src/graph/utils.py
from typing import Any, Dict
import json

def clean_props(d: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten dict to Neo4j-safe scalar / primitive-list values."""
    ...
```
Then in both files: `from src.graph.utils import clean_props as _clean_props`.

---

## Info

### IN-01: `import sys` in `neo4j_loader.py` is unused

**File:** `src/graph/neo4j_loader.py:36`

**Issue:** `sys` is imported on line 36 but never referenced anywhere in the module. `SystemExit` is raised directly (not via `sys.exit`), which does not require importing `sys`.

**Fix:** Remove `import sys` from line 36.

---

### IN-02: `allow_module_level=False` in fixture-level `pytest.skip` calls is redundant noise

**File:** `tests/conftest.py:13, 22`

**Issue:** `allow_module_level=False` is the default value of that parameter and has no effect when `pytest.skip()` is called inside a fixture function. The parameter only matters when called at module import time (outside any function). Its presence implies a copy-paste from a module-level context and may mislead future readers into thinking it has operational significance.

**Fix:**
```python
pytest.skip("NEO4J_PASSWORD not set")
pytest.skip("Neo4j not reachable")
```

---

### IN-03: `pymupdf` (`fitz`) is not in `requirements.txt` but is the primary PDF library per `CLAUDE.md`

**File:** `requirements.txt`

**Issue:** `CLAUDE.md` specifies `pymupdf` (imported as `fitz`) as the primary PDF parsing library. It is absent from `requirements.txt`. `pdfplumber` is present but is designated as a fallback/complement for table extraction. Any code that `import fitz` will raise `ModuleNotFoundError` in a clean environment.

**Fix:**
```
pymupdf>=1.24.0
```
Add to `requirements.txt`. Verify the exact version at https://pypi.org/project/pymupdf before pinning.

---

_Reviewed: 2026-05-02T15:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
