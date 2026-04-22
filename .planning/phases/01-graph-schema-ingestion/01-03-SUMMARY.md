---
phase: 01-graph-schema-ingestion
plan: "03"
subsystem: pdf-ingestion
tags: [pdf, parsing, pymupdf, pdfplumber, extraction, dual-extraction]
dependency_graph:
  requires:
    - plan 01 (requirements.txt pins PyMuPDF==1.27.2.2 and pdfplumber==0.11.9)
  provides:
    - src/ingest/pdf_parser.py exports extract_page_content() and format_page_for_llm()
    - src/ingest/__init__.py as package marker
  affects:
    - plan 04 (entity_extractor.py imports extract_page_content from src.ingest.pdf_parser)
    - plan 05 (ingest CLI calls extract_page_content on t9-thermostat.pdf)
tech_stack:
  added: []
  patterns:
    - Dual-extraction: fitz (prose) + pdfplumber (tables) — never mix concerns
    - extract_tables() over extract_text() to preserve cell-by-cell table structure
    - Pipe-delimited row formatting for LLM consumption via format_page_for_llm()
key_files:
  created:
    - src/ingest/__init__.py
    - src/ingest/pdf_parser.py
    - tests/test_pdf_parser.py
  modified: []
decisions:
  - "Used fitz.get_text('text') for prose (preserves layout) and pdfplumber.extract_tables() for tables (cell-by-cell, not fused)"
  - "format_page_for_llm() outputs pipe-delimited rows so LLM sees column structure clearly"
  - "Raised FileNotFoundError early (before opening PDF) to give clear error messages"
metrics:
  duration_minutes: 15
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 0
  completed_date: "2026-04-15"
---

# Phase 01 Plan 03: PDF Parser Summary

**One-liner:** Dual-extraction PDF parser using fitz (prose) + pdfplumber (tables) with pipe-delimited LLM formatting — 17 pages, 19 tables extracted from T9 thermostat PDF.

## What Was Built

Created the `src.ingest` package with a PDF parser module that implements a dual-extraction strategy for the T9 thermostat installation guide.

- **`extract_page_content(pdf_path)`** — Opens the PDF with both libraries simultaneously. Uses `fitz.page.get_text("text")` for prose text (preserves layout) and `pdfplumber.page.extract_tables()` for tables (cell-by-cell structure, not fused column text). Returns a list of `{page_num, prose, tables}` dicts.
- **`format_page_for_llm(page)`** — Converts a page dict into a single string for the entity extraction LLM prompt. Prose appears as a text block; tables appear as pipe-delimited rows preserving column structure.

## PDF Extraction Results (T9 Thermostat PDF)

| Metric | Value |
|--------|-------|
| Total pages | 17 |
| Pages with tables | 11 (pages 2-8, 11, 12, 14, 15) |
| Prose-only pages | 6 (pages 1, 9, 10, 13, 16, 17) |
| Total tables | 19 |

## Sample format_page_for_llm Output (Page 2 — first table page)

```
=== Page 2 — Text ===
Read before installing.
Included in your box:
Tools you will need:
You may need:
...

=== Page 2 — Table 1 ===
 |  |

=== Page 2 — Table 2 ===
 |
```

(Page 2 tables contain image-based content with minimal text; wiring/compatibility tables on pages 3-8 contain richer structured data.)

## Tests

8 tests in `tests/test_pdf_parser.py` — all pass against the real T9 PDF without requiring Neo4j or Groq:

| Test | What It Validates |
|------|-------------------|
| `test_extract_page_content_returns_pages` | Real PDF yields >= 1 pages |
| `test_page_dict_has_required_keys` | page_num, prose, tables keys present |
| `test_page_num_is_one_indexed` | First page is page_num == 1 |
| `test_prose_is_string` | prose is always str |
| `test_tables_is_list` | tables is always list |
| `test_tables_are_nested_lists_not_strings` | Tables are nested lists (cell-by-cell), not fused strings |
| `test_missing_pdf_raises_file_not_found` | FileNotFoundError on non-existent path |
| `test_format_page_for_llm_returns_string` | format_page_for_llm() produces non-empty str |

## Deviations from Plan

None — plan executed exactly as written. Libraries were not installed in a virtual environment; pip3 install to the global Python 3.13.1 environment was needed (Rule 3 auto-fix: missing dependencies).

## Known Stubs

None — extract_page_content() returns real data from the real PDF. format_page_for_llm() wires directly to the page dict with no placeholders.

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| `90a5c78` | feat | Create PDF parser module with dual-extraction strategy |
| `8515bcd` | test | Add tests for PDF parser covering structure, tables, and error handling |

## Self-Check: PASSED

- `src/ingest/__init__.py` — exists
- `src/ingest/pdf_parser.py` — exists, exports extract_page_content and format_page_for_llm
- `tests/test_pdf_parser.py` — exists, 8 tests all pass
- `90a5c78` commit — verified in git log
- `8515bcd` commit — verified in git log
