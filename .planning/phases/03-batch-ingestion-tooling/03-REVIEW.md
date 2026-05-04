---
phase: 03-batch-ingestion-tooling
reviewed: 2026-05-03T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - scripts/batch_ingest.py
  - src/graph/provenance.py
  - src/ingest/batch.py
  - src/ingest/batch_report.py
  - src/ingest/failure_log.py
  - tests/integration/test_batch_ingest_dry_run.py
  - tests/integration/test_batch_ingest_neo4j.py
  - tests/unit/test_scoped_delete.py
  - tests/unit/test_batch_report.py
  - tests/unit/test_failure_log.py
findings:
  critical: 4
  warning: 5
  info: 3
  total: 12
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-05-03T00:00:00Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Phase 03 delivers batch ingestion orchestration (dry-run and full-mode), per-doc JSON reports, a JSONL failure log, and scoped-delete provenance helpers. The overall structure is solid, but several correctness and security defects were found that must be addressed before full-mode (Plan 03-03) goes live against a shared Neo4j instance. The four critical findings are: two Cypher injection vectors in `provenance.py`, a silent data-loss bug in `scoped_delete_doc` (wrong aggregation pattern), and a broken `_to_iso_z` path that silently emits wrong timestamps. Five warnings cover duplicate imports, empty-report exit-code confusion, a monkey-patched global that is not thread-safe, an argparse monkey-patch that suppresses all parse errors globally, and a missing `ingested_at` guard in the Cypher template.

---

## Critical Issues

### CR-01: Cypher injection via unsanitised `safe_label` in `merge_node_with_provenance`

**File:** `src/graph/provenance.py:103-136`

**Issue:** `safe_label` is built by stripping non-alphanumeric characters from `node.get("kind")`, but the comment at line 101 says "the caller validates" and treats local sanitisation as "defence-in-depth". If the caller omits or bypasses validation (e.g. during tests, future callers, or a schema change), a `kind` value like `Product}) DETACH DELETE (n` would survive the alphanumeric filter as `ProductDETACHDELETEn` — harmless — but a value whose alphanumeric remnant happens to be a valid Neo4j label and whose surrounding brackets/braces appear in adjacent literal text could produce unexpected node structures. More concretely: the f-string on line 136 embeds `safe_label` directly into a Cypher statement:

```python
f"""
MERGE (n:{safe_label} {{node_id: $node_id}})
```

If `safe_label` resolves to the empty string (input is entirely non-alphanumeric), the fallback `or "Entity"` saves it, but if it resolves to a multi-word label after stripping — e.g. `ProductORSpec` — this becomes valid but semantically wrong Cypher. The deeper issue is that **f-string Cypher interpolation for structural tokens (labels, relationship types) is never safe** when input originates outside the codebase. The same pattern appears for `safe_rel` in `merge_edge_with_provenance` line 195. Both should be validated against a strict whitelist allowlist before interpolation, not sanitised character-by-character.

**Fix:**
```python
VALID_LABELS = frozenset({"Product", "Accessory", "WiringConfig",
                           "HVACSystemType", "Spec", "Entity"})
VALID_RELATIONS = frozenset({"COMPATIBLE_WITH", "REPLACES", "HAS_SPEC",
                              "REQUIRES", "RELATED_TO"})

# In merge_node_with_provenance:
if label not in VALID_LABELS:
    raise ValueError(f"Unknown node label {label!r}; allowed: {VALID_LABELS}")
safe_label = label  # already validated — no f-string sanitisation needed

# In merge_edge_with_provenance:
if relation not in VALID_RELATIONS:
    raise ValueError(f"Unknown relation {relation!r}; allowed: {VALID_RELATIONS}")
safe_rel = relation
```

---

### CR-02: `scoped_delete_doc` — wrong Cypher pattern causes all count queries to return 0

**File:** `src/graph/provenance.py:246-285`

**Issue:** Steps 1, 2, 3, and 5 all use the pattern:

```cypher
MATCH ()-[r {source_doc: $doc_id}]->()
WITH r, count(r) AS c
DELETE r
RETURN c
```

`WITH r, count(r) AS c` is a **grouping aggregation over each individual `r`**, so `count(r)` is always `1` for every row — the `WITH` clause does not aggregate across all matched rows. The intent is to return the total number of deleted items, but this pattern returns one row per deleted item each containing `c=1`, and then `.single()` reads only the first row. For step 4 (orphan delete) the same pattern appears at line 265. The caller receives `out["edges"] = 1` even when 500 edges were deleted, silently producing misleading reports.

The correct pattern uses `count(*)` before the mutation, or collects counts with `RETURN count(r) AS c` directly after deletion using `WITH count(r) AS c DELETE r` order doesn't work either — the fix is:

**Fix:** Separate count from delete, or use the recommended Neo4j delete-and-count idiom:
```cypher
MATCH ()-[r {source_doc: $doc_id}]->()
WITH collect(r) AS rels
UNWIND rels AS r
DELETE r
RETURN size(rels) AS c
```
Or more simply:
```cypher
MATCH ()-[r {source_doc: $doc_id}]->()
WITH count(r) AS c
MATCH ()-[r2 {source_doc: $doc_id}]->()
DELETE r2
RETURN c
```
Apply the same fix to the `ment_q`, `prune_q`, `orph_q`, and `doc_q` steps.

---

### CR-03: `_to_iso_z` silently produces wrong timestamps for non-UTC aware datetimes with non-zero offsets

**File:** `src/ingest/batch_report.py:65-76`

**Issue:** The string branch (line 68) assumes that any string already ending in `"Z"` is correct UTC:

```python
if isinstance(value, str):
    return value if value.endswith("Z") else value + "Z"
```

If a caller passes an ISO string that ends in `"+05:30"` (or any non-UTC offset), this branch appends nothing and the stored timestamp is wrong UTC-labelled time. More importantly, if a string like `"2026-05-03T19:14:02"` (no tz) is passed, the code blindly appends `Z` producing `"2026-05-03T19:14:02Z"`, claiming UTC without any conversion. The function is called in `build_doc_report` for `started_at`/`finished_at`, which currently always receives `datetime` objects — but the string branch is a latent correctness bug for any future caller that passes an ISO string with offset or no offset.

**Fix:**
```python
def _to_iso_z(value: Any) -> str:
    if isinstance(value, str):
        # Parse and normalise rather than blindly append
        value = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Fall through to datetime branch
    if isinstance(value, _dt.datetime):
        if value.tzinfo is None:
            raise ValueError(f"Naive datetime passed to _to_iso_z: {value!r}")
        return value.astimezone(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    raise TypeError(f"Unsupported timestamp type: {type(value)!r}")
```

---

### CR-04: `_extract_to_graph_items` monkey-patches `argparse.ArgumentParser.parse_args` globally — any concurrent call in the same process uses the stub

**File:** `src/ingest/batch.py:110-120`

**Issue:** The function replaces `argparse.ArgumentParser.parse_args` on the **class** (not an instance), which affects every `ArgumentParser` in the process while the patch is active:

```python
_ap.ArgumentParser.parse_args = _stub_parse
try:
    _ingest_main()
finally:
    _ap.ArgumentParser.parse_args = _orig_parse
```

In a multi-threaded environment (e.g. a future async batch runner, or any test runner that parallelises with `pytest-xdist`), a second thread entering `argparse` parsing during this window will get `_stub_parse` instead of the real `parse_args`, causing it to silently receive the wrong `Namespace` (`ns` from a different doc) or to crash. Even single-threaded, if `_ingest_main()` itself spawns a subprocess or thread that calls `argparse`, the patch corrupts that call. This is a fragile design that could cause data-loss (wrong arguments silently passed to an ingestion run).

**Fix:** Use `unittest.mock.patch` as a context manager to confine the patch scope, or better, refactor `src.pipeline.ingest` to expose a `run(args)` function that accepts a pre-built `Namespace` directly, eliminating the need for any monkey-patching:
```python
# Preferred: expose a programmatic entry point in src/pipeline/ingest.py
from src.pipeline.ingest import run as _ingest_run
graph_items = _ingest_run(ns)
```

---

## Warnings

### WR-01: Duplicate `from neo4j import GraphDatabase` inside `run_batch`

**File:** `src/ingest/batch.py:316` and `345`

**Issue:** `GraphDatabase` is imported twice inside the same function body — once at line 316 (before the `if args.dry_run` branch) and again at line 345 (inside the `else` branch). The first import at line 316 is unreachable in the dry-run path and redundant in the full-mode path. This is harmless but indicates the function was assembled incrementally without cleanup.

**Fix:** Keep only the import at line 345 (inside the `else` block where it is actually used), and remove line 316:
```python
# Remove line 316:
# from neo4j import GraphDatabase   <-- delete this
```

---

### WR-02: `exit_code` returns 1 when `reports` is empty (e.g. empty manifest)

**File:** `scripts/batch_ingest.py:246`

**Issue:**
```python
exit_code = 0 if all(r.get("status") == "ok" for r in reports) else 1
```

When `reports` is an empty list, `all(...)` returns `True` (vacuous truth), so exit code is `0`. This is the opposite of the semantically correct behaviour for an empty manifest — the operator likely ran the wrong manifest or filtered to a non-existent doc. There is also no warning printed when zero docs are processed. This could silently succeed in CI while ingesting nothing.

**Fix:**
```python
if not reports:
    print("warning: no documents processed (manifest empty or all filtered out)", file=sys.stderr)
    return 2  # or another distinct code
exit_code = 0 if all(r.get("status") == "ok" for r in reports) else 1
```

---

### WR-03: `merge_document` passes `ingested_at=None` to `datetime($ingested_at)` — Neo4j raises a type error at runtime

**File:** `src/graph/provenance.py:66`

**Issue:**
```python
ingested_at=doc.get("ingested_at") or None,
```

When `doc["ingested_at"]` is absent or falsy, the parameter is `None`. The Cypher template unconditionally calls `datetime($ingested_at)` on line 54:
```cypher
d.ingested_at = datetime($ingested_at),
```
Neo4j will raise a `TypeError` when `$ingested_at` is `null` because `datetime(null)` is not valid in Neo4j 5.x. This path is hit every time a manifest entry lacks an `ingested_at` field — which is normal since manifest entries do not include this field; `batch.py` supplies it from `datetime.now()`. However, the provenance function is public and directly callable; any caller that omits `ingested_at` will crash the transaction.

**Fix:** Guard in the Cypher with `CASE WHEN $ingested_at IS NOT NULL THEN datetime($ingested_at) ELSE null END`:
```cypher
d.ingested_at = CASE WHEN $ingested_at IS NOT NULL
                     THEN datetime($ingested_at)
                     ELSE null END,
```

---

### WR-04: `capture_warnings` does not restore logger `propagate` or `level` — can permanently elevate a logger's effective level

**File:** `src/ingest/batch_report.py:164`

**Issue:** The `_Sink` handler is added at `WARNING` level to each named logger. If a target logger currently has no level set (defaults to `NOTSET`, inheriting from root), adding a handler with `WARNING` level does not change the logger's own level. However, if in future the handler is created at `DEBUG` level and the logger has `propagate=True`, all debug messages would start flowing to the sink. More concretely: the current code adds a handler to the logger object but never sets `lg.level` — so if the root logger is set to `DEBUG` (e.g. `--verbose` mode), the `_Sink` will capture `DEBUG` and `INFO` records too because `logging.Handler.emit` is called when `record.levelno >= handler.level`. The filter `if record.levelno >= logging.WARNING` inside `emit` corrects for this, but it is a double-filter relying on internal correctness rather than properly setting the handler level.

The real risk: if an exception occurs during `yield` and the `finally` block's `removeHandler` call itself throws (e.g., due to a broken logger state), all subsequent uses of those loggers will have a dangling `_Sink` capturing records indefinitely.

**Fix:**
```python
sink = _Sink(level=logging.WARNING)
# Also set on the logger so the logging framework filters early:
for lg in targets:
    lg.addHandler(sink)
    # Store and restore original level if we need to set one:
    # (current code is acceptable; add explicit setLevel to the handler only)
```
At minimum, document the dependency on `emit`'s internal guard and add a test that verifies `DEBUG`-level records are not captured even when root is at `DEBUG`.

---

### WR-05: `ingest_one_doc`'s `scoped_delete` parameter is silently ignored — dead parameter in public API

**File:** `src/ingest/batch.py:149`

**Issue:** The `scoped_delete` parameter is documented in the docstring as "kept for API compatibility but is never used inside this function". This means any caller that passes `scoped_delete=True` to `ingest_one_doc` will silently skip the scoped delete, resulting in data duplication on re-ingest. The docstring acknowledges this but the public API signature with a default value of `False` invites misuse. `_run_one_doc` correctly handles scoped delete itself, but the exported `ingest_one_doc` signature is misleading.

**Fix:** Remove the `scoped_delete` parameter from the `ingest_one_doc` signature entirely, or raise `NotImplementedError` if it is passed as `True`:
```python
def ingest_one_doc(
    doc: dict,
    *,
    dry_run: bool,
    inferencer: str | None,
    force: bool,
    output_dir: Path,
    driver: Any = None,
    # scoped_delete removed — handled by _run_one_doc
) -> tuple[dict, str, list[dict], str | None]:
```

---

## Info

### IN-01: `print_summary` truncates `doc_id` strings longer than 32 characters without warning

**File:** `scripts/batch_ingest.py:201`

**Issue:** `doc_id.ljust(COL_DOC)` silently overflows the column for doc_ids longer than 32 characters, misaligning the entire summary table. No truncation or warning is applied.

**Fix:**
```python
doc_id_disp = doc_id[:COL_DOC] if len(doc_id) > COL_DOC else doc_id
```

---

### IN-02: Commented-out / unused `create_constraints` import at top of `run_batch` is duplicated

**File:** `src/ingest/batch.py:24` and `317`

**Issue:** `create_constraints` is imported at the module top-level (line 24) and again inside the `run_batch` function body (line 317). The top-level import is sufficient; the local re-import at line 317 is redundant dead code.

**Fix:** Remove the `from src.graph.neo4j_loader import create_constraints` at line 317.

---

### IN-03: `test_dry_run_does_not_touch_neo4j` hardcodes expected report count as `4`

**File:** `tests/integration/test_batch_ingest_dry_run.py:102`

**Issue:** The assertion `assert len(reports) == 4` hardcodes the manifest document count. When a fifth document is added to `data/raw/manifest.json`, this test will fail for the wrong reason. The adjacent test `test_dry_run_walks_all_manifest_docs` correctly derives the expected count dynamically from `load_manifest`.

**Fix:**
```python
all_docs = load_manifest("data/raw/manifest.json")
assert len(reports) == len(all_docs)
```

---

_Reviewed: 2026-05-03T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
