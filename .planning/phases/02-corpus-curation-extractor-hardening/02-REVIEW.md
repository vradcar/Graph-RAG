---
phase: 02-corpus-curation-extractor-hardening
reviewed: 2026-05-03T00:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - src/graph/extract.py
  - src/pipeline/ingest.py
  - src/ingest/entity_extractor.py
  - src/ingest/manifest.py
  - src/ingest/normalizer.py
  - src/ingest/pdf_parser.py
  - src/ingest/rejections.py
  - tests/conftest.py
  - tests/fixtures/t9_baseline.json
  - tests/integration/test_corpus_ingest.py
  - tests/integration/test_corpus_ingest_full.py
  - tests/integration/test_cross_doc_bridges.py
  - tests/integration/test_replacements_ingest.py
  - tests/integration/test_t9_non_regression.py
  - tests/regressions/test_extractor_rejects_invalid_kind.py
  - tests/regressions/test_parser_filters_translation_pages.py
  - tests/regressions/test_parser_strips_footnote_markers.py
  - tests/test_normalizer.py
  - tests/unit/test_manifest.py
  - tests/unit/test_normalizer_bridges.py
findings:
  critical: 3
  warning: 5
  info: 3
  total: 11
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-05-03T00:00:00Z
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

This phase introduced PDF parsing (`pdf_parser.py`), LLM-based entity extraction (`entity_extractor.py`), a corpus manifest (`manifest.py`), entity normalization (`normalizer.py`), rejection logging (`rejections.py`), and a `pages` kwarg filter threaded from manifest through the ingest pipeline to the extractor.

Three blockers were found. The most significant is a schema mismatch: `extract.py`'s Week 2 rich graph emits **9 edge types and 8 node types that do not exist in `schema.py`**, including the `REPLACED_BY` relation used throughout the retrieval layer — while `ingest_replacements()` writes `REPLACES` in the opposite direction for the same semantic concept, creating an inconsistent graph. The second blocker is a multi-separator normalization bug in `normalize_node_id` that silently produces double-dashed node IDs (e.g., `"o--b"`) when input contains a space adjacent to a slash, causing alias lookups to fail and cross-document bridge tests to silently miss edges. The third is a `ValueError` crash (unhelpful traceback) when the manifest `pages` list has anything other than exactly 2 elements, with no guard in either the pipeline or the extractor.

---

## Critical Issues

### CR-01: Rich-graph edge types and node types are not in `schema.py` — schema split is inconsistent

**File:** `src/graph/extract.py:159,180,189,199,256,286,315,340,360`

**Issue:** `extract_from_pdf` produces edges with types `NOT_COMPATIBLE_WITH`, `HAS_ELECTRICAL_SPEC`, `NEEDS_ADAPTER_IF_MISSING`, `COMPLEX_ON`, `REQUIRES`, `CONNECTS_TO`, `HAS_OPERATING_RANGE`, `MOUNTS_ON`, and `REPLACED_BY`. None of these appear in `schema.py`'s `ALLOWED_RELATIONS = Literal["COMPATIBLE_WITH", "REPLACES", "SUPPORTS_WIRING", "HAS_SPEC", "MENTIONED_IN"]`. Similarly, node types `Thermostat`, `Wallplate`, `Adapter`, `ZoningPanel`, `WiringTerminal`, `RoomSensor`, `OperatingRange`, and `ElectricalSpec` are not in `NODE_KIND`. `_validate()` in `extract.py` does not check edge types against the schema — it only checks for key presence and endpoint membership — so these invalid types pass validation silently.

`neo4j_loader.py` currently logs a warning for unknown kinds/relations but loads them anyway (lines 128-129, 172-173). The comment says "Phase 2 tightens this." This phase is Phase 2, so the intended tightening either never happened or the schema was intentionally expanded but `schema.py` was not updated. Either way, the schema definition and the data it describes are now split across two codebases with no single source of truth.

Additionally, `ingest_replacements()` writes `(new)-[:REPLACES]->(old)`, but `_build_thermostat_nodes()` writes `(old)-[:REPLACED_BY]->(new)` — opposite direction, different relation name — for the same semantic concept. The retrieval layer (`graph_retriever.py`) queries for `REPLACED_BY` only.

**Fix:**  
Option A (preferred): Extend `schema.py` to add all used relation types and node kinds:
```python
NODE_KIND = Literal[
    "Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec",
    "Document", "Thermostat", "Wallplate", "Adapter", "ZoningPanel",
    "WiringTerminal", "RoomSensor", "OperatingRange", "ElectricalSpec",
]
ALLOWED_RELATIONS = Literal[
    "COMPATIBLE_WITH", "REPLACES", "REPLACED_BY", "SUPPORTS_WIRING", "HAS_SPEC",
    "MENTIONED_IN", "NOT_COMPATIBLE_WITH", "HAS_ELECTRICAL_SPEC",
    "NEEDS_ADAPTER_IF_MISSING", "COMPLEX_ON", "REQUIRES", "CONNECTS_TO",
    "HAS_OPERATING_RANGE", "MOUNTS_ON",
]
```
Option B: Align `_build_thermostat_nodes` to emit `REPLACES` in the same direction as `ingest_replacements()`, then remove `REPLACED_BY` from the codebase and update `graph_retriever.py`.

Also, add edge-type validation to `_validate()`:
```python
from src.graph.schema import VALID_RELATIONS
for e in graph["edges"]:
    if e.get("type") not in VALID_RELATIONS:
        errs.append(f"Edge type {e.get('type')!r} not in VALID_RELATIONS: {e}")
```

---

### CR-02: `normalize_node_id` fails to collapse multi-separator sequences — cross-doc bridge aliases silently break

**File:** `src/ingest/normalizer.py:115-123`

**Issue:** The normalization chain applies a single `replace("--", "-")` pass after replacing spaces, slashes, and underscores with dashes. A single pass only collapses one pair. Three or more consecutive dashes are left with a residual double-dash.

Concretely, `"O / B"` (space-slash-space) produces `"o--b"` (not `"o-b"`), so `NODE_ID_ALIASES.get("o--b", "o--b")` returns the raw unhyphenated value rather than `"terminal-o-b"`. Any LLM output that inserts whitespace around a slash — or any input with adjacent separators such as underscores and spaces — will silently produce a malformed node_id that fails alias resolution, causing cross-document bridge detection to miss edges.

```python
# Reproducer:
normalize_node_id("O / B")   # returns "o--b", not "terminal-o-b"
normalize_node_id("a___b")   # returns "a--b", not "a-b"
```

The existing test suite only covers `"O/B"` (no spaces), which passes. The broken case is untested.

**Fix:** Replace the single-pass `replace("--", "-")` with a regex collapse:
```python
import re

def normalize_node_id(raw: str) -> str:
    normalized = raw.strip().lower()
    normalized = re.sub(r"[ /_.]+", "-", normalized)   # collapse any run of separators
    normalized = normalized.strip("-")
    return NODE_ID_ALIASES.get(normalized, normalized)
```

---

### CR-03: Unguarded tuple unpack crashes with `ValueError` when manifest `pages` has other than exactly 2 elements

**File:** `src/graph/extract.py:519` and `src/ingest/pdf_parser.py:62`

**Issue:** Both `extract_from_pdf` and `extract_page_content` unpack `pages` with `start, end = pages`. If the manifest ever contains a `pages` list with 1 or 3+ elements (data entry error or future multi-range support), the unpack raises `ValueError: too many values to unpack (expected 2)` with no indication of which document or manifest key caused the problem.

`src/pipeline/ingest.py:93` similarly does `tuple(doc["pages"])` without validating the length before passing it to `extract_from_pdf`.

**Fix:** Validate before unpacking. In both call sites:
```python
if pages is not None:
    if len(pages) != 2:
        raise ValueError(
            f"pages must be a 2-element (start, end) tuple; got {pages!r}"
        )
    start, end = pages
```

---

## Warnings

### WR-01: `zoning_panel` node is hardcoded inside the page-3 extractor but claims `source_page=7`

**File:** `src/graph/extract.py:194-201`

**Issue:** The `zoning_panel` node and its `COMPLEX_ON` edge are created inside `_extract_compatibility_and_power`, which is the page-3 extractor. Both the node and the edge carry `source_page=7`. When a `pages=(3, 3)` filter is active, the page-3 extractor runs, the `zoning_panel` node is created with `source_page=7`, but no page-7 extractor has run. The `source_page` field is therefore inaccurate provenance data.

**Fix:** Either move the `zoning_panel` node to a dedicated page-7 extractor entry in `page_specific_extractors`, or set `source_page=3` to match where the node is actually extracted.

---

### WR-02: `normalize_label` returns the original case when a label is not in `ALIAS_MAP`, creating inconsistent label casing in the graph

**File:** `src/ingest/normalizer.py:134-135`

**Issue:** `normalize_label` converts the raw label to uppercase to do a case-insensitive lookup in `ALIAS_MAP`, but falls back to `raw.strip()` (original case) when the label is not found. This means two LLM outputs for the same concept — `"Heat Pump System"` and `"heat pump system"` — both pass through unchanged with different casings even though neither is in `ALIAS_MAP`. Labels that happen to be in `ALIAS_MAP` get canonical uppercase treatment; all others keep whatever case the LLM returned. This is inconsistent and will create label fragmentation in Neo4j.

**Fix:** Either return `normalized` (uppercased) when not in the alias map, or consistently return `raw.strip()` and apply a separate title-case normalization step:
```python
def normalize_label(raw: str) -> str:
    upper = raw.strip().upper().replace("  ", " ")
    return ALIAS_MAP.get(upper, raw.strip())
    # OR for full normalization: ALIAS_MAP.get(upper, upper)
```
Pick one policy and apply it uniformly.

---

### WR-03: `test_t9_non_regression.py` reads the fixture file at module level — crashes pytest collection if the fixture is absent

**File:** `tests/integration/test_t9_non_regression.py:10`

**Issue:** `BASELINE = json.loads(Path("tests/fixtures/t9_baseline.json").read_text())` executes at import time. If the fixture file is missing (e.g., in a fresh clone before fixture generation), pytest fails to collect the entire module rather than skipping the test. This produces a confusing `FileNotFoundError` in the collection phase rather than a skip.

**Fix:** Move the load inside the test function or use a lazy fallback:
```python
BASELINE_PATH = Path("tests/fixtures/t9_baseline.json")

@pytest.mark.integration
def test_t9_baseline_no_regression(neo4j_driver, clean_db):
    if not BASELINE_PATH.exists():
        pytest.skip(f"{BASELINE_PATH} missing")
    BASELINE = json.loads(BASELINE_PATH.read_text())
    ...
```

---

### WR-04: `test_cross_doc_bridges.py` does not use `clean_db` — can produce false-positive bridge detections from stale data

**File:** `tests/integration/test_cross_doc_bridges.py:19`

**Issue:** `test_each_new_doc_bridges_to_t9` depends on `corpus_ingested` (which ingests new docs) and `neo4j_driver`, but does NOT include `clean_db`. If a prior test run left data in Neo4j — including T9 nodes and their `source_docs` arrays — the bridge check `MATCH (n) WHERE $d1 IN n.source_docs AND $d2 IN n.source_docs` will find those leftover nodes and report a bridge even when the current ingest produced none. The test can report a false pass.

**Fix:** Add `clean_db` to the test signature so the database is wiped before the corpus ingest:
```python
@pytest.mark.integration
@pytest.mark.parametrize("new_doc_id", NEW_DOC_IDS)
def test_each_new_doc_bridges_to_t9(neo4j_driver, clean_db, corpus_ingested, new_doc_id):
    ...
```
Note: `corpus_ingested` must be re-ordered after `clean_db` in the fixture resolution order.

---

### WR-05: `ingest_replacements` silently skips valid cross-document replacement edges when endpoints are not in the local `thermostats[]` array

**File:** `src/graph/extract.py:442-448`

**Issue:** Lines 442-448 check `if old_id not in therms_by_id or new_id not in therms_by_id` and skip the edge with a warning. This rejects any replacement edge whose endpoint comes from a different document's product catalog — a scenario that becomes common once multiple PDFs are ingested. The check was likely intended to prevent dangling edges, but Neo4j's MERGE will safely create the target node if it doesn't exist (via `merge_node_with_provenance`), making the guard unnecessarily restrictive.

**Fix:** Remove the cross-reference check, or replace it with a node pre-creation step for missing endpoints:
```python
for rep in replacements:
    old_id = rep.get("from")
    new_id = rep.get("to")
    if not old_id or not new_id:
        skipped += 1
        continue
    # Removed: therms_by_id membership check — Neo4j MERGE handles missing nodes
    edge = { ... }
    session.execute_write(...)
    edge_count += 1
```

---

## Info

### IN-01: Redundant `start, end = pages` assignment inside the per-extractor loop

**File:** `src/graph/extract.py:544-545`

**Issue:** `start` and `end` are already unpacked at line 519 (inside `if pages is not None`). The inner loop re-unpacks them at line 545 on every iteration. This is dead code — the values never change between the two unpacks.

**Fix:** Remove the inner assignment:
```python
for target_page, fn in page_specific_extractors:
    if pages is not None and (target_page < start or target_page > end):
        log.info("Skipping extractor for page %d (outside filter %d-%d)",
                 target_page, start, end)
        continue
    n, e = fn()
```

---

### IN-02: `print()` used for status output in `normalizer.py` — inconsistent with logging pattern used everywhere else

**File:** `src/ingest/normalizer.py:178`

**Issue:** `normalize_and_deduplicate` uses `print(f"  Excluded {excluded_count} incompatible system nodes")` while every other module in this phase uses `logging.getLogger(__name__)`. This output appears on stdout regardless of log level settings, bypasses the logging infrastructure, and cannot be suppressed during testing.

**Fix:**
```python
import logging
log = logging.getLogger(__name__)
...
if excluded_count:
    log.info("Excluded %d incompatible system nodes", excluded_count)
```

---

### IN-03: `test_parser_filters_translation_pages.py` uses module-level `pytest.mark.skipif` with a `Path.exists()` call — skip condition evaluated at collection time against potentially wrong cwd

**File:** `tests/regressions/test_parser_filters_translation_pages.py:10`

**Issue:** `@pytest.mark.skipif(not PDF.exists(), reason="...")` evaluates `PDF.exists()` when the module is imported (collection time), not when the test runs. If pytest is invoked from a directory other than the project root, the relative `Path("data/raw/thp9045-wiring-module.pdf")` will not resolve correctly and the skip condition will always be `True`, silently skipping both tests forever.

**Fix:** Use a check inside the test body:
```python
def test_pages_filter_returns_only_english_range():
    if not PDF.exists():
        pytest.skip(f"THP9045 PDF not present: {PDF}")
    ...
```

---

_Reviewed: 2026-05-03T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
