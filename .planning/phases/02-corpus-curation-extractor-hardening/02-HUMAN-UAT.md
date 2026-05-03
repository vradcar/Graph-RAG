---
status: partial
phase: 02-corpus-curation-extractor-hardening
source: [02-VERIFICATION.md]
started: 2026-05-03T18:00:00Z
updated: 2026-05-03T18:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. SC-2: Cross-doc bridge assertions (corpus_ingested + bridge counts)
expected: All 3 new PDFs (T6, THP9045, T10) ingest into Neo4j; each bridges to t9_install_guide via shared node or adjacent edge
result: [pending]

### 2. SC-4/INGEST-05: T9 non-regression gate
expected: node_count >= 8, edge_count >= 13, no baseline kinds removed after re-ingest
result: [pending]

### 3. INGEST-04: REPLACES edges written by ingest_replacements
expected: Cypher MATCH ()-[r:REPLACES]->() RETURN count(r) >= 1 after replacements ingest
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
