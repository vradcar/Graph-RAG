# REQUIREMENTS — Milestone v2.0 T1-Sai

**Goal:** Harden the ingestion pipeline so it produces high-quality, knowledge-grounded extractions across multiple Honeywell HVAC PDFs, proving GraphRAG's multi-document answering advantage over flat RAG.

**Source of truth for scope:** This file. Phases are derived from these requirements; do not implement work that is not traceable to a REQ-ID here.

---

## v2.0 Requirements

### Discovery & Corpus (DISCOVER)

- [ ] **DISCOVER-01**: Curate a 3-PDF Honeywell HVAC corpus (T6 Pro, THP9045 C-Wire Adapter, T10 Pro) chosen for entity overlap with the existing T9 graph
- [ ] **DISCOVER-02**: Each PDF in the corpus is checked into `data/raw/` with a documented source URL (manifest file with title, SKU, URL, retrieval date)
- [ ] **DISCOVER-03**: Each PDF is verified to contain at least one entity that exists in or directly connects to the T9 subgraph (else it adds no multi-doc value)

### Schema & Provenance (SCHEMA)

- [ ] **SCHEMA-01**: Add `:Document` node kind to `src/graph/schema.py` with properties (doc_id, title, sku, source_url, ingested_at)
- [ ] **SCHEMA-02**: Add `MENTIONED_IN` relation type to schema (entity → document) so citations are queryable
- [ ] **SCHEMA-03**: All extracted edges carry a `source_doc` property identifying the PDF they were extracted from
- [ ] **SCHEMA-04**: Edge MERGE semantics in `neo4j_loader.py` keyed on (source, target, relation, source_doc) so the same fact from two PDFs yields two parallel evidence-bearing edges
- [ ] **SCHEMA-05**: Nodes deduplicate across documents (one `:Product {sku: "T6 Pro"}` regardless of how many PDFs mention it) and accumulate a `source_docs[]` list via ON CREATE / ON MATCH

### Ingestion Hardening (INGEST)

- [ ] **INGEST-01**: `pdf_parser.py` handles all 3 new PDFs end-to-end without unhandled exceptions; layout/table failures log structured warnings rather than crashing
- [ ] **INGEST-02**: `entity_extractor.py` extracts only schema-valid entity kinds and relations across the new PDFs (closed-world enum enforced; invalid LLM outputs rejected with logged reason)
- [ ] **INGEST-03**: `normalizer.py` performs deterministic cross-document entity resolution: SKU regex (`(RCHT|TH[XP]?|RTH|HZ|THM|THP)\d{3,4}…`) + ALIAS registry resolves common Honeywell product/accessory naming variants to canonical IDs
- [ ] **INGEST-04**: Bug-fix loop: any extractor failure observed during corpus ingestion is filed as a fix in pdf_parser/entity_extractor/normalizer with a regression test guarding against it
- [ ] **INGEST-05**: T9 baseline does not regress — re-running the original T9 ingest after hardening produces the same node/edge counts as v1.0 (or strictly more, never fewer or different kinds)

### Batch Tooling (BATCH)

- [ ] **BATCH-01**: `scripts/batch_ingest.py` ingests all PDFs in `data/raw/` in one command, with `--dry-run` mode that writes per-doc JSON to `data/processed/` without touching Neo4j
- [ ] **BATCH-02**: Per-PDF report includes: entity count by kind, edge count by relation, extraction warnings, runtime, and pass/fail status
- [ ] **BATCH-03**: Failure log written to `reports/ingest_failures.log` with structured entries (doc_id, stage, error class, snippet) for debug-driven fixes
- [ ] **BATCH-04**: Re-run safety: re-running batch ingest twice produces identical graph state (no duplicates, no orphan edges) — scoped delete by `source_doc` before re-MERGE

### Quality Verification (QUALITY)

- [ ] **QUALITY-01**: Curated multi-document query set (≥6 questions) where the correct answer requires traversing edges that span at least 2 PDFs (e.g. "What thermostats does the THP9045 support?")
- [ ] **QUALITY-02**: Each multi-doc query returns a knowledge-grounded answer where the graph context surfaces edges from ≥2 distinct `source_doc` values
- [ ] **QUALITY-03**: Citation surface — for any answer, the user can trace which PDF(s) the supporting edges came from (via `source_doc` and/or `MENTIONED_IN`)
- [ ] **QUALITY-04**: A flat-RAG-style baseline (vector mode in existing pipeline) is run against the same multi-doc query set; graph mode wins or ties on the curated set, and at least 2 queries are demonstrable graph-only wins

---

## Future Requirements

Deferred to later milestones:

- Eval framework with precision@k, latency p50/p95, LLM-judge scoring (T2 track)
- Streamlit UX polish, mode toggle, loading states (T3 track)
- Dockerfile + docker-compose + public deployment (T4 track)
- Report, deck, demo video (T5 track)
- 8+ PDF corpus including smoke/CO detectors and equipment interface modules
- Honeywell internal hosting / dataset access outreach (T4 stretch)

---

## Out of Scope

Explicitly excluded from v2.0 T1-Sai:

- **Eval scoring infrastructure** — T2 owns this; T1 only ships the curated query set, not the harness
- **UI changes** — T3 owns Streamlit polish; T1 must not break the existing app but does not improve it
- **Deployment / packaging** — T4 owns Docker/Aura; T1 stays local-Neo4j
- **Schema redesign** — only additive changes (`:Document`, `MENTIONED_IN`, `source_doc` property). Existing kinds and relations are not renamed or restructured
- **Vector store changes** — `SimpleVectorStore` unchanged; vector mode used as-is for the QUALITY-04 baseline comparison
- **Fuzzy product-name merging** — fuzzy matching restricted to WiringConfig and Spec only; Products require deterministic SKU/alias resolution
- **Non-Honeywell PDFs** — corpus is Honeywell HVAC only

---

## v1.0 Requirements (Validated — Reference Only)

The original v1.0 milestone shipped graph schema, ingestion, query pipeline, and Streamlit UI for the T9 thermostat. Those requirements (GRAPH-*, INGEST-*, QUERY-*, UI-*) are validated and live; v2.0 builds on top of them. See `.planning/archive/v1.0-milestone/` for the executed plans.

---

## Traceability

Every v2.0 REQ-ID maps to exactly one phase.

| REQ-ID | Phase |
|--------|-------|
| DISCOVER-01 | Phase 2 |
| DISCOVER-02 | Phase 2 |
| DISCOVER-03 | Phase 2 |
| SCHEMA-01 | Phase 1 |
| SCHEMA-02 | Phase 1 |
| SCHEMA-03 | Phase 1 |
| SCHEMA-04 | Phase 1 |
| SCHEMA-05 | Phase 1 |
| INGEST-01 | Phase 2 |
| INGEST-02 | Phase 2 |
| INGEST-03 | Phase 2 |
| INGEST-04 | Phase 2 |
| INGEST-05 | Phase 2 |
| BATCH-01 | Phase 3 |
| BATCH-02 | Phase 3 |
| BATCH-03 | Phase 3 |
| BATCH-04 | Phase 3 |
| QUALITY-01 | Phase 4 |
| QUALITY-02 | Phase 4 |
| QUALITY-03 | Phase 4 |
| QUALITY-04 | Phase 4 |

---
*Last updated: 2026-05-02 — milestone v2.0 T1-Sai traceability filled by roadmapper*
