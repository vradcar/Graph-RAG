# Phase 1: Graph Schema & Ingestion — Validation Strategy

**Phase:** 01-graph-schema-ingestion
**Created:** 2026-04-15

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Quick run | `pytest tests/ -x -q` |
| Full suite | `pytest tests/ -v` |

## Requirements → Test Map

| Req ID | Behavior | Test Type | Test File | Automated Command |
|--------|----------|-----------|-----------|-------------------|
| GRAPH-01–06 | Node types and properties validated | unit | tests/test_schema.py | `pytest tests/test_schema.py -x` |
| GRAPH-07 | MERGE produces no duplicates | integration | tests/test_neo4j_store.py | `pytest tests/test_neo4j_store.py::test_idempotent_ingest -x` |
| INGEST-01 | pymupdf text extraction | unit | tests/test_pdf_parser.py | `pytest tests/test_pdf_parser.py -x` |
| INGEST-02 | pdfplumber table extraction | unit | tests/test_pdf_parser.py | `pytest tests/test_pdf_parser.py::test_table_not_fused -x` |
| INGEST-03 | Groq+instructor extraction | unit | tests/test_entity_extractor.py | `pytest tests/test_entity_extractor.py -x` |
| INGEST-04 | Closed-world enum enforcement | unit | tests/test_entity_extractor.py | `pytest tests/test_entity_extractor.py::test_closed_world_enum -x` |
| INGEST-05 | Normalize/deduplicate | unit | tests/test_entity_extractor.py | `pytest tests/test_entity_extractor.py -x` |
| INGEST-06 | Idempotent re-run | integration | tests/test_ingest_pipeline.py | `pytest tests/test_ingest_pipeline.py::test_double_run_idempotency -x` |

## Security Controls

| Threat | Mitigation | Verified By |
|--------|-----------|-------------|
| Cypher injection via entity labels | Parameterized Cypher ($node_id) | grep for f-string node_id in store.py |
| API key exposure | Load from .env via python-dotenv | grep for hardcoded keys |
