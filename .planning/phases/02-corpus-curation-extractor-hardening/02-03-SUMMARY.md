---
plan: 02-03
phase: 02-corpus-curation-extractor-hardening
status: complete
key-files:
  created:
    - src/ingest/rejections.py
    - tests/regressions/test_extractor_rejects_invalid_kind.py
    - reports/.gitkeep
  modified:
    - src/ingest/entity_extractor.py
---

# Plan 02-03: Entity Extractor Rejection Handling

## What Was Built

- **`src/ingest/rejections.py`**: `log_rejection()` JSON-line writer to `reports/extraction_rejections.log`; exports `REJECTION_LOG_PATH`
- **`src/ingest/entity_extractor.py`**: `extract_from_page` wrapped in `ValidationError` handler — catches post-retry failures, logs via `log_rejection`, and returns empty `ExtractionResult` instead of crashing; `doc_id` param added; multi-SKU page prompt rule and image-only wiring diagram rule added to `EXTRACTION_SYSTEM_PROMPT`
- **`tests/regressions/test_extractor_rejects_invalid_kind.py`**: Regression test verifying that a `ValidationError` (simulated via pydantic probe) causes `log_rejection` to fire and an empty result to be returned
- **`reports/.gitkeep`**: Directory scaffolding so the log directory exists in the repo

## Self-Check: PASSED

All must_haves delivered:
- Invalid kind after retries → logged + empty result (not crashed) ✓
- System prompt instructs LLM on multi-SKU pages ✓
- Rejections written to `reports/extraction_rejections.log` ✓
- Regression test in `tests/regressions/` ✓

## Commits

- `62abc34` feat(02-03): add rejection logger module + reports/ directory
- `c8b0221` feat(02-03): wrap extract_from_page in ValidationError handler + multi-SKU prompt rules
- `fc5e992` test(02-03): regression test for invalid-kind extraction rejection
