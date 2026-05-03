---
phase: 01-graph-schema-ingestion
plan: "04"
subsystem: entity-extraction
tags: [groq, instructor, pydantic, normalizer, entity-extractor, unit-tests]
dependency_graph:
  requires:
    - plan 01 (NODE_KIND, ALLOWED_RELATIONS from src.graph.schema)
  provides:
    - src/ingest/entity_extractor.py exports build_client, extract_from_page, ExtractionResult, ExtractedNode, ExtractedEdge
    - src/ingest/normalizer.py exports normalize_node_id, normalize_label, deduplicate_nodes, normalize_and_deduplicate, ALIAS_MAP
  affects:
    - plan 05 (ingest CLI: from src.ingest.entity_extractor import build_client, extract_from_page)
tech_stack:
  added:
    - groq==1.1.2
    - instructor==1.15.1
    - pydantic==2.12.5
    - pytest==9.0.2
  patterns:
    - Closed-world enum enforcement via Pydantic Literal type annotation (NODE_KIND, ALLOWED_RELATIONS)
    - instructor.from_groq with mode=TOOLS for structured output with automatic retry on schema violation
    - Lazy import of format_page_for_llm inside extract_from_page() body (avoids circular import)
    - ALIAS_MAP dict for canonical label normalization before Neo4j MERGE
key_files:
  created:
    - src/ingest/__init__.py
    - src/ingest/entity_extractor.py
    - src/ingest/normalizer.py
    - src/ingest/pdf_parser.py (stub — full impl from plan 03)
    - tests/__init__.py
    - tests/test_entity_extractor.py
    - tests/test_normalizer.py
  modified:
    - src/graph/schema.py (added NODE_KIND, ALLOWED_RELATIONS, VALID_KINDS, VALID_RELATIONS)
    - requirements.txt (added groq, instructor, pydantic, pytest, PyMuPDF, pdfplumber)
decisions:
  - "Lazy import of format_page_for_llm inside extract_from_page() allows wave 2 plans (03 and 04) to run in parallel without circular import issues"
  - "pdf_parser.py stub created in this worktree so test_extract_from_page_calls_groq_with_correct_roles can run without plan 03 being merged first"
  - "schema.py updated in this worktree to include NODE_KIND/ALLOWED_RELATIONS since wave 1 (plan 01) runs in a separate worktree and cannot be imported from there"
  - "Test parametrize expectation for normalize_label('  heat pump  ') corrected to 'HEAT-PUMP' — HEAT PUMP is in ALIAS_MAP, the original test comment was wrong"
metrics:
  duration: "~3 minutes"
  completed: "2026-04-15"
  tasks_completed: 2
  files_changed: 9
requirements: [INGEST-03, INGEST-04, INGEST-05]
---

# Phase 01 Plan 04: Entity Extractor and Normalizer Summary

Groq+instructor entity extractor with Pydantic closed-world enum enforcement and a canonical normalizer/deduplicator — both consumed by the ingest CLI in plan 05.

## What Was Built

### Pydantic Models (`src/ingest/entity_extractor.py`)

| Model | Field | Type | Notes |
|-------|-------|------|-------|
| `ExtractedNode` | `node_id` | `str` | Stable unique identifier; product model numbers or lowercase-hyphenated slugs |
| `ExtractedNode` | `label` | `str` | Human-readable name |
| `ExtractedNode` | `kind` | `NODE_KIND` | Literal["Product","Accessory","WiringConfig","HVACSystemType","Spec"] — Pydantic rejects any other value |
| `ExtractedNode` | `properties` | `dict` | Optional extra attributes |
| `ExtractedEdge` | `source_id` | `str` | node_id of source |
| `ExtractedEdge` | `target_id` | `str` | node_id of target |
| `ExtractedEdge` | `relation` | `ALLOWED_RELATIONS` | Literal["COMPATIBLE_WITH","REPLACES","SUPPORTS_WIRING","HAS_SPEC"] — Pydantic rejects any other value |
| `ExtractionResult` | `nodes` | `List[ExtractedNode]` | Extracted node list |
| `ExtractionResult` | `edges` | `List[ExtractedEdge]` | Extracted edge list |

### Functions (`src/ingest/entity_extractor.py`)

| Function | Signature | Notes |
|----------|-----------|-------|
| `build_client` | `() -> instructor.Instructor` | Reads GROQ_API_KEY via os.getenv(); raises ValueError if missing |
| `extract_from_page` | `(client, model: str, page: dict) -> ExtractionResult` | Returns ExtractionResult; short-circuits on blank page without calling LLM |

### EXTRACTION_SYSTEM_PROMPT (summarized)

Instructs the LLM to:
- Extract exactly 5 node kinds: Product, Accessory, WiringConfig, HVACSystemType, Spec
- Use exactly 4 relationship types: COMPATIBLE_WITH, REPLACES, SUPPORTS_WIRING, HAS_SPEC
- Use product model numbers (e.g., RCHT9510WF) as node_id for Product nodes
- Use lowercase-hyphenated slugs for all other node_ids
- Only extract explicitly stated relationships (no inference)
- Return empty lists if no entities found on the page

### Normalizer (`src/ingest/normalizer.py`)

| Function | Behavior |
|----------|----------|
| `normalize_node_id(raw)` | lowercase + hyphenated: "RCHT9510WF" → "rcht9510wf", "2 Wire Heat Only" → "2-wire-heat-only" |
| `normalize_label(raw)` | Apply ALIAS_MAP (uppercase key lookup), return canonical alias or stripped original |
| `normalize_node(node)` | Returns node dict copy with normalized node_id and label |
| `deduplicate_nodes(nodes)` | Remove duplicates by node_id, first-seen wins |
| `normalize_and_deduplicate(nodes)` | Convenience: normalize all then deduplicate |

### ALIAS_MAP entries

| Input (uppercased) | Canonical Output |
|--------------------|-----------------|
| `"24 VAC"` | `"24VAC"` |
| `"24 V AC"` | `"24VAC"` |
| `"24VAC AC"` | `"24VAC"` |
| `"HEAT PUMP"` | `"HEAT-PUMP"` |
| `"HEAT ONLY"` | `"HEAT-ONLY"` |
| `"COOL ONLY"` | `"COOL-ONLY"` |

## Test Results

```
tests/test_entity_extractor.py ......    6 tests
tests/test_normalizer.py .............   13 tests
19 passed in 0.27s
```

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_entity_extractor.py` | 6 | Closed-world enum rejection (kind + relation), valid ExtractionResult construction, ValueError on missing API key, blank-page short-circuit, LLM message role structure |
| `test_normalizer.py` | 13 | normalize_node_id (6 parametrized cases), normalize_label (4 parametrized cases), deduplicate_nodes, deduplicate empty list, normalize_and_deduplicate pipeline |

No live Groq API key required — all client calls mocked with MagicMock.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Incorrect test parametrize expectation for normalize_label**

- **Found during:** Task 2 test run
- **Issue:** The plan's test template had `("  heat pump  ", "heat pump")` with comment "stripped but not in map", but `HEAT PUMP` IS in ALIAS_MAP → canonical form is `"HEAT-PUMP"`, not `"heat pump"`
- **Fix:** Updated parametrize expected value to `"HEAT-PUMP"` to match actual behavior
- **Files modified:** `tests/test_normalizer.py`
- **Commit:** 9671ec7

### Infrastructure Additions (not deviations, required for wave 2 parallel execution)

**2. [Rule 3 - Blocking] schema.py lacked NODE_KIND/ALLOWED_RELATIONS in this worktree**

- **Found during:** Task 1 setup
- **Issue:** Wave 1 plan (01-01) ran in a separate worktree (agent-ad0a54d3); this worktree's schema.py was the original skeleton without the Literal types
- **Fix:** Applied wave 1's schema.py changes (NODE_KIND, ALLOWED_RELATIONS, VALID_KINDS, VALID_RELATIONS) to this worktree; updated requirements.txt with all new dependencies
- **Files modified:** `src/graph/schema.py`, `requirements.txt`

**3. [Rule 3 - Blocking] pdf_parser.py not yet merged from concurrent plan 03**

- **Found during:** Task 1 implementation (format_page_for_llm import inside extract_from_page)
- **Issue:** Plan 03 runs in wave 2 concurrently and creates `src/ingest/pdf_parser.py` with `format_page_for_llm`; tests that call `extract_from_page` with non-blank content would fail with ImportError
- **Fix:** Created `src/ingest/pdf_parser.py` stub with a working `format_page_for_llm` implementation; plan 03's full version will replace this on merge. The stub is functionally correct (prose + table text joining)
- **Files modified:** `src/ingest/pdf_parser.py` (created)

## Known Stubs

- `src/ingest/pdf_parser.py` — `extract_page_content()` raises `NotImplementedError`; `format_page_for_llm()` is fully functional. Plan 03 provides the complete implementation; this stub will be replaced on merge.

## Threat Flags

None — no new network endpoints or auth paths beyond those in the plan's threat model. GROQ_API_KEY is only read via `os.getenv()`, never hardcoded or logged.

## Self-Check

Checking created files exist:

- [x] `src/graph/schema.py` — updated with NODE_KIND, ALLOWED_RELATIONS
- [x] `src/ingest/__init__.py` — package marker
- [x] `src/ingest/entity_extractor.py` — ExtractedNode, ExtractedEdge, ExtractionResult, build_client, extract_from_page
- [x] `src/ingest/normalizer.py` — normalize_node_id, normalize_label, deduplicate_nodes, normalize_and_deduplicate, ALIAS_MAP
- [x] `src/ingest/pdf_parser.py` — format_page_for_llm stub
- [x] `tests/__init__.py` — package marker
- [x] `tests/test_entity_extractor.py` — 6 tests
- [x] `tests/test_normalizer.py` — 13 tests
- [x] Commit `ab6848b` — feat(01-04): entity_extractor.py and normalizer.py
- [x] Commit `9671ec7` — test(01-04): unit tests

## Self-Check: PASSED
