# ROADMAP — Milestone v2.0 T1-Sai

**Goal:** Harden the ingestion pipeline so it produces high-quality, knowledge-grounded extractions across multiple Honeywell HVAC PDFs, proving GraphRAG's multi-document answering advantage over flat RAG.

**Granularity:** coarse
**Phases:** 4
**Coverage:** 21/21 v2.0 REQ-IDs mapped

---

## Phases

- [x] **Phase 1: Schema & Provenance Foundation** - Additive schema for Document nodes, MENTIONED_IN, source_doc edge property, and per-document MERGE/dedup semantics
- [ ] **Phase 2: Corpus Curation & Extractor Hardening** - Onboard T6 Pro, THP9045, T10 Pro PDFs; harden parser/extractor/normalizer with no T9 regression
- [ ] **Phase 3: Batch Ingestion Tooling** - scripts/batch_ingest.py with dry-run, per-doc reports, structured failure log, and idempotent re-runs
- [ ] **Phase 4: Multi-Document Quality Verification** - Curated cross-doc query set with citations and graph-vs-vector comparison demonstrating graph-only wins

## Phase Details

### Phase 1: Schema & Provenance Foundation
**Goal**: The graph schema and Neo4j loader carry enough provenance for every extracted fact to be cited and deduplicated across documents.
**Depends on**: Nothing (first phase of milestone)
**Requirements**: SCHEMA-01, SCHEMA-02, SCHEMA-03, SCHEMA-04, SCHEMA-05
**Success Criteria** (what must be TRUE):
  1. src/graph/schema.py defines a :Document node kind with (doc_id, title, sku, source_url, ingested_at) and a MENTIONED_IN relation; existing entity kinds and business relations are unchanged (additive only).
  2. Loading the same fact from two different PDFs produces two parallel evidence-bearing edges in Neo4j, each carrying a distinct source_doc property.
  3. A node mentioned in N PDFs exists exactly once in Neo4j and has a source_docs[] array of length N populated via ON CREATE / ON MATCH semantics.
  4. Every edge written by neo4j_loader.py has a non-null source_doc property, verifiable via Cypher `MATCH ()-[r]->() WHERE r.source_doc IS NULL RETURN count(r)` returning 0.
**Plans**: 3 plans
- [x] 01-01-PLAN.md — Schema additions (Document, MENTIONED_IN) + failing test scaffolding
- [x] 01-02-PLAN.md — provenance.py helpers + neo4j_loader.py refactor + --doc-id CLI
- [x] 01-03-PLAN.md — T9 backfill re-ingest + audit verification (checkpoint)

### Phase 2: Corpus Curation & Extractor Hardening
**Goal**: A curated 3-PDF Honeywell corpus is checked in and ingests cleanly through hardened parser/extractor/normalizer code with zero T9 regression.
**Depends on**: Phase 1
**Requirements**: DISCOVER-01, DISCOVER-02, DISCOVER-03, INGEST-01, INGEST-02, INGEST-03, INGEST-04, INGEST-05
**Success Criteria** (what must be TRUE):
  1. The 3 target PDFs (T6 Pro, THP9045 C-Wire Adapter, T10 Pro) are present in data/raw/ with a manifest documenting title, SKU, source URL, and retrieval date for each.
  2. Each new PDF, when ingested, produces at least one entity that already exists in or directly connects to the T9 subgraph, verifiable via a cross-doc edge in Neo4j.
  3. pdf_parser.py, entity_extractor.py, and normalizer.py ingest all 3 PDFs end-to-end with no unhandled exceptions; the extractor enforces the closed-world entity/relation enum and rejects invalid LLM outputs with a logged reason.
  4. Re-running the original T9 ingest after hardening produces node/edge counts equal to (or strictly greater than) the v1.0 baseline, with no kinds removed or renamed.
  5. Every extractor failure observed during corpus ingestion has a corresponding fix in pdf_parser/entity_extractor/normalizer with a regression test that fails on the unfixed code.
**Plans**: TBD

### Phase 3: Batch Ingestion Tooling
**Goal**: A single batch command ingests the entire corpus repeatably with structured per-doc reporting and idempotent re-run safety.
**Depends on**: Phase 2
**Requirements**: BATCH-01, BATCH-02, BATCH-03, BATCH-04
**Success Criteria** (what must be TRUE):
  1. `python scripts/batch_ingest.py` ingests all PDFs in data/raw/ in one command; --dry-run writes per-doc JSON to data/processed/ without touching Neo4j.
  2. Each PDF run produces a structured per-doc report (entity count by kind, edge count by relation, extraction warnings, runtime, pass/fail) viewable on stdout and persisted to disk.
  3. Failures are written to reports/ingest_failures.log as structured entries (doc_id, stage, error class, snippet) suitable for debug-driven fixes.
  4. Running batch ingest twice in succession yields identical Neo4j graph state — verified by node/edge counts and no duplicate source_doc-keyed edges — via scoped delete by source_doc before re-MERGE.
**Plans**: TBD

### Phase 4: Multi-Document Quality Verification
**Goal**: A curated cross-document query set demonstrates that the graph surfaces multi-PDF knowledge with citations, and beats flat RAG on questions only a graph can answer.
**Depends on**: Phase 3
**Requirements**: QUALITY-01, QUALITY-02, QUALITY-03, QUALITY-04
**Success Criteria** (what must be TRUE):
  1. A curated query set of >=6 questions is checked in, where each question's correct answer requires traversing edges that span >=2 PDFs.
  2. Running each multi-doc query through the existing pipeline returns a knowledge-grounded answer whose graph context contains edges from >=2 distinct source_doc values.
  3. For every answer, the user can trace which PDF(s) supplied each supporting edge — surfaced via source_doc and/or MENTIONED_IN in the graph context output.
  4. Running the same query set in vector mode produces a comparison artifact in which graph mode wins or ties on every query, with at least 2 queries documented as graph-only wins (vector mode cannot answer).
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Schema & Provenance Foundation | 3/3 | Complete | 2026-05-02 |
| 2. Corpus Curation & Extractor Hardening | 0/0 | Not started | - |
| 3. Batch Ingestion Tooling | 0/0 | Not started | - |
| 4. Multi-Document Quality Verification | 0/0 | Not started | - |

---
*Last updated: 2026-05-02 — Phase 1 complete (3/3 plans done, all SCHEMA-* requirements verified)*
