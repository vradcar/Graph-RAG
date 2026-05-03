# Honeywell GraphRAG

## Current Milestone: v2.0 T1-Sai

**Goal:** Harden the ingestion pipeline so it produces high-quality, knowledge-grounded extractions across multiple Honeywell HVAC PDFs (not just T9), proving GraphRAG's multi-document answering advantage over flat RAG.

**Target features:**
- Discover and onboard 3–5 additional Honeywell HVAC PDFs (other thermostats, smoke detectors, controllers) that compose well with the existing T9 schema
- Batch ingestion harness (`scripts/batch_ingest.py`) with per-PDF entity/edge counts and structured failure logs
- Extractor hardening across `src/ingest/pdf_parser.py`, `entity_extractor.py`, `normalizer.py` driven by failures observed on the new corpus
- Graph quality safeguards: no T9 regression, deduplication across documents, cross-document edges where the data supports them (e.g. shared accessories, replacement chains)
- Multi-document query verification: a curated set of cross-document questions that demonstrate knowledge-grounded answers only a graph (not flat RAG) can produce

**Out of scope (other tracks T2–T5):** evaluation framework, demo UX polish, deployment/Docker, report/deck/video.

**Integration mindset (cross-cutting — applied while writing code, not as a separate phase):** Other tracks (T2 eval, T3 demo/UI, T4 deployment, T5 report) depend on T1's pipeline. Code in this milestone should be written so downstream tracks can integrate without rework — favor importable Python APIs over shell-only entry points, return structured data (entities, edges, source_doc) from query results, keep ingest deterministic and idempotent, and avoid breaking existing CLI signatures. This is a how-we-write-code principle, not a checklist.

## What This Is

A Graph-based Retrieval-Augmented Generation (GraphRAG) prototype for Honeywell's HVAC product data. It extracts entities and relationships from product documentation into a Neo4j knowledge graph, then answers natural language queries by traversing the graph and generating structured answers via an LLM (Groq).

## Core Value

Deliver relationship-aware answers about product compatibility, replacements, and specifications that a standard RAG system would miss — by modeling products as interconnected graph nodes rather than flat document chunks.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Extract entities (products, accessories, wiring configs, HVAC system types, specs) from the T9 thermostat PDF
- [ ] Build a product-centric knowledge graph in Neo4j with typed relationships (compatible_with, replaces, requires, has_spec, etc.)
- [ ] Natural language query interface that converts questions to graph traversals
- [ ] LLM-generated structured answers using graph context (Groq)
- [ ] Simple web UI (Streamlit/Gradio) for querying
- [ ] Neo4j graph visualization showing nodes and edges
- [ ] Sample query demonstrating end-to-end pipeline with output

### Out of Scope

- Multi-document ingestion / web scraping — single PDF source only
- Production hardening (auth, rate limiting, error recovery)
- Document-centric graph nodes (sections, chunks) — product-centric only
- Embedding-based vector search — graph traversal is the retrieval mechanism
- Fine-tuning or training models

## Context

- **Data source**: T9 Smart Thermostat Installation Guide (RCHT9510WF) at `data/raw/t9-thermostat.pdf`
- **Domain**: Honeywell Building Automation & HVAC Controls — thermostats, compatibility, wiring configurations, product specifications
- **Existing codebase**: Skeleton GraphRAG pipeline with networkx-based graph store, placeholder vector store, and stub LLM generation. This project replaces the networkx backend with Neo4j and implements the full pipeline end-to-end.
- **Compatibility relationships**: Thermostat ↔ wiring config ↔ voltage ↔ HVAC system type. Products have successor/replacement chains.

## Constraints

- **Graph backend**: Neo4j (not networkx)
- **LLM provider**: Groq — model name must be a single configurable placeholder in the codebase for easy experimentation
- **Data**: Single PDF only (T9 thermostat installation guide)
- **Scope**: Demo/prototype quality, not production-grade

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Neo4j over networkx | Real graph database with visualization, Cypher queries, scalability | — Pending |
| Groq as LLM provider | Fast inference, simple API | — Pending |
| Product-centric schema | Cleaner graph, focused on compatibility/replacement relationships | — Pending |
| Single PDF source | Scoped prototype, proves the architecture | — Pending |
| Web UI (Streamlit/Gradio) | Quick demo interface for queries | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-02 — milestone v2.0 T1-Sai started*
