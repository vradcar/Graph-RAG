---
phase: 02-corpus-curation-extractor-hardening
plan: "02"
subsystem: ingest/pdf_parser
tags: [parser, regression-tests, corpus-hardening, pages-filter, footnote-stripping]
dependency_graph:
  requires: [02-01]
  provides: [pdf_parser.extract_page_content with pages filter and footnote stripping]
  affects: [src/ingest/pdf_parser.py, tests/regressions/]
tech_stack:
  added: []
  patterns: [regex footnote stripping at parse boundary, per-doc page range filter]
key_files:
  created:
    - tests/regressions/test_parser_strips_footnote_markers.py
    - tests/regressions/test_parser_filters_translation_pages.py
    - tests/fixtures/regressions/t6_footnote_sample.txt
  modified:
    - src/ingest/pdf_parser.py
decisions:
  - "Footnote stripping at parse boundary (not normalizer) — prevents label and node_id slug pollution downstream"
  - "pages filter as optional kwarg with None default — backward compatible; existing callers unaffected"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-03"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 02 Plan 02: PDF Parser Hardening — Pages Filter + Footnote Stripping Summary

## One-liner

Added `pages=(start, end)` range filter and `[N]` footnote-marker stripping to `extract_page_content` with two regression tests covering THP9045 page isolation and T6 Pro marker cleanup.

## What Was Built

### Task 1: pages filter + footnote-marker stripping (commit `8c8c0a2`)

**`src/ingest/pdf_parser.py`** was modified to:

- Add `import re` and module-level constant `_FOOTNOTE_MARKER_RE = re.compile(r"\[\d{1,2}\]")` — strips inline footnote markers like `[1]`.`[11]` from T6 Pro prose.
- Add `_strip_footnote_markers(text: str) -> str` private helper — removes 1-2 digit bracketed markers while preserving surrounding whitespace.
- Change `extract_page_content` signature to accept optional `pages: tuple[int, int] | None = None` kwarg (1-indexed inclusive range; `None` = all pages, existing behavior unchanged).
- Apply page range filter inside the loop before appending — `continue` if `page_num < start or page_num > end`.
- Apply `_strip_footnote_markers()` to prose at extraction time — before storing in the returned page dict.
- `format_page_for_llm` untouched — consumes clean prose without modification.

### Task 2: regression tests + fixture (commit `b54ea73`)

- **`tests/fixtures/regressions/t6_footnote_sample.txt`** — 5-line verbatim snippet with `[1]`, `[2]`, `[3]`, `[4]`, `[11]` markers demonstrating the T6 Pro footnote pollution.
- **`tests/regressions/test_parser_strips_footnote_markers.py`** — two assertions: no `[\d+]` pattern remains after strip; surrounding text ("Power input", "24VAC") is preserved.
- **`tests/regressions/test_parser_filters_translation_pages.py`** — two assertions: `pages=(1,4)` on THP9045 returns exactly 4 pages numbered `[1,2,3,4]`; default (no `pages`) returns all 12 pages.

## Verification Results

All success criteria met:

| Check | Result |
|-------|--------|
| `extract_page_content('thp9045-wiring-module.pdf', pages=(1,4))` returns 4 pages | PASS |
| Footnote markers stripped from prose at parse time | PASS |
| `pytest tests/regressions/ -x` (4 tests) | 4 PASSED |
| `pytest tests/test_pdf_parser.py -x` (8 existing tests) | 8 PASSED |
| Total suite (tests/regressions/ + tests/test_pdf_parser.py) | 12 PASSED |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. Both fixes are fully wired: the regex runs on every page's prose; the pages filter slices the iteration loop deterministically.

## Threat Flags

None. This plan modifies only the local PDF parsing layer (no network endpoints, no auth paths, no schema changes, no file writes).

## Self-Check: PASSED

Files exist:
- `src/ingest/pdf_parser.py` — FOUND
- `tests/regressions/test_parser_strips_footnote_markers.py` — FOUND
- `tests/regressions/test_parser_filters_translation_pages.py` — FOUND
- `tests/fixtures/regressions/t6_footnote_sample.txt` — FOUND

Commits exist:
- `8c8c0a2` (Task 1) — FOUND
- `b54ea73` (Task 2) — FOUND
