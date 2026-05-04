---
status: partial
phase: 03-batch-ingestion-tooling
source: [03-VERIFICATION.md]
started: 2026-05-03T00:00:00Z
updated: 2026-05-03T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. CLI invocation path
expected: `PYTHONPATH=. python scripts/batch_ingest.py --dry-run` writes reports/batch/<doc_id>_report.json for each manifest doc, prints aligned summary table, exits 0
result: [pending]

### 2. BATCH-04 idempotency via live Neo4j
expected: `pytest tests/integration/test_batch_ingest_neo4j.py -m integration` passes all 8 tests against Neo4j 5.x; running `python scripts/batch_ingest.py` twice produces identical node/edge counts
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
