---
phase: 01-schema-provenance-foundation
fixed_at: 2026-05-02T16:00:00Z
review_path: .planning/phases/01-schema-provenance-foundation/01-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-05-02T16:00:00Z
**Source review:** .planning/phases/01-schema-provenance-foundation/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (CR-01 through CR-04, WR-01 through WR-05)
- Fixed: 9
- Skipped: 0

## Fixed Issues

### CR-04: `merge_document` crashes with datetime("") when ingested_at absent

**Files modified:** `src/graph/provenance.py`
**Commit:** 917020b
**Applied fix:** Changed `doc.get("ingested_at", "")` to `doc.get("ingested_at") or None` so both absent-key and empty-string cases resolve to None, which Cypher handles safely as `datetime(null)` without raising a parse error.

---

### CR-01: `merge_node_with_provenance` — no guard for None node_id

**Files modified:** `src/graph/provenance.py`
**Commit:** 03e723f
**Applied fix:** Added `if not node_id: raise ValueError(...)` immediately after extracting `node_id`, before any props are set or Cypher is executed. This prevents null-keyed node collisions in Neo4j MERGE.

---

### CR-03: `merge_node_with_provenance` — silent skip of MENTIONED_IN edge when Document absent

**Files modified:** `src/graph/provenance.py`
**Commit:** 33cad59
**Applied fix:** Added `RETURN count(m) AS mi_count` to the end of the node MERGE query and called `result.single()`. Raises `ValueError` if `mi_count == 0`, enforcing that `merge_document` must be committed before ingesting nodes.

---

### CR-02: `merge_edge_with_provenance` — silent data loss when endpoint nodes missing

**Files modified:** `src/graph/provenance.py`
**Commit:** 1b9b640
**Applied fix:** Added `RETURN count(r) AS written` to the edge MERGE query and called `result.single()`. Raises `ValueError` if `written == 0`, making missing-endpoint failures visible to callers instead of silently dropping the edge.

---

### WR-01: WiringConfig and Spec missing from create_constraints

**Files modified:** `src/graph/neo4j_loader.py`
**Commit:** 42784d0
**Applied fix:** Added `"WiringConfig"` and `"Spec"` to the labels list; removed `"Document"` which was creating a dead `constraint_document_node_id` constraint (Document identity uses `doc_id`, covered by the separate `constraint_document_doc_id` constraint already present).

---

### WR-02: --verify documented as standalone but requires input file

**Files modified:** `src/graph/neo4j_loader.py`
**Commit:** 037c0f9
**Applied fix:** Restructured `main()` to wrap the file-load block in `if not args.verify or input_path.exists():`. When `--verify` is passed without a data file, the load steps are skipped entirely and `verify(driver)` runs standalone. When `--verify` is combined with a present data file, both load and verify execute as before.

---

### WR-03: test_document_upsert vacuous assertion

**Files modified:** `tests/test_provenance.py`
**Commit:** 5b13f25
**Applied fix:** Added `assert first_ingested is not None, "first_ingested must be set on CREATE"` after reading the first-write result, and `assert node2.get("last_reingested") is not None, "last_reingested must be set on MATCH"` after the second upsert. These prevent the ON CREATE and ON MATCH Cypher branches from silently failing.

---

### WR-04: conftest.py bare except Exception swallows programming bugs

**Files modified:** `tests/conftest.py`
**Commit:** 816ae37
**Applied fix:** Moved the `from neo4j import GraphDatabase` import outside the try block (it was already there effectively), added `from neo4j.exceptions import ServiceUnavailable, AuthError`, and replaced `except Exception` with `except (ServiceUnavailable, AuthError, OSError)`. All other exceptions now propagate as test errors rather than silent skips. Also removed the redundant `allow_module_level=False` parameter from this call.

---

### WR-05: _clean_props duplicated in provenance.py and neo4j_loader.py

**Files modified:** `src/graph/utils.py` (new file), `src/graph/provenance.py`, `src/graph/neo4j_loader.py`
**Commit:** 6875e79
**Applied fix:** Created `src/graph/utils.py` with a single `clean_props` function containing the shared implementation. Both `provenance.py` and `neo4j_loader.py` now import `from src.graph.utils import clean_props as _clean_props`, with the local duplicate definitions removed. The `json` import was also removed from `provenance.py` (it was only needed by the local `_clean_props`).

---

_Fixed: 2026-05-02T16:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
