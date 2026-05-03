# Requirements — Honeywell GraphRAG

## v1 Requirements

### Graph Schema & Storage (GRAPH)

- [ ] **GRAPH-01**: System stores Product nodes with properties: model number, name, description, status (active/discontinued)
- [ ] **GRAPH-02**: System stores Accessory nodes linked to compatible Products via COMPATIBLE_WITH edges
- [ ] **GRAPH-03**: System stores WiringConfig nodes representing wiring configurations (e.g., 2-wire, 4-wire) linked to Products via SUPPORTS_WIRING edges
- [ ] **GRAPH-04**: System stores HVACSystemType nodes (heat pump, conventional, etc.) linked to Products via COMPATIBLE_WITH edges
- [ ] **GRAPH-05**: System stores Spec nodes (voltage, dimensions, etc.) linked to Products via HAS_SPEC edges
- [ ] **GRAPH-06**: Products linked to successors/predecessors via REPLACES edges
- [ ] **GRAPH-07**: All Neo4j writes use MERGE with uniqueness constraints to prevent duplicates

### PDF Ingestion (INGEST)

- [ ] **INGEST-01**: System extracts text from T9 thermostat PDF using pymupdf
- [ ] **INGEST-02**: System extracts tables from T9 thermostat PDF using pdfplumber
- [ ] **INGEST-03**: System uses Groq LLM with structured output (instructor + Pydantic) to extract entities and relationships from parsed PDF content
- [ ] **INGEST-04**: Extraction prompt enforces a closed-world enum of allowed relationship types (no LLM-invented synonyms)
- [ ] **INGEST-05**: Extracted entities are normalized/deduplicated before writing to Neo4j
- [ ] **INGEST-06**: Ingestion is idempotent — re-running does not create duplicate nodes or edges

### Query Pipeline (QUERY)

- [ ] **QUERY-01**: User can ask natural language questions about product compatibility, replacements, and specs
- [ ] **QUERY-02**: System detects relevant entities from the question and maps them to graph nodes
- [ ] **QUERY-03**: System performs multi-hop Cypher traversal (depth 2+) to gather graph context
- [ ] **QUERY-04**: System generates structured answers via Groq LLM using graph context
- [ ] **QUERY-05**: At least 3 canned demo queries produce verified correct answers
- [ ] **QUERY-06**: Groq model name is a single configurable key in settings.yaml

### Web UI (UI)

- [ ] **UI-01**: User can type natural language queries in a Streamlit web interface
- [ ] **UI-02**: System displays LLM-generated answers in the UI
- [ ] **UI-03**: UI provides a link/embed to Neo4j Browser for graph visualization

## v2 Requirements (Deferred)

- Wiring terminal extraction as structured entities (R/C/W/Y/G)
- Wiring compatibility table parsing
- NL-to-Cypher generation
- Evidence panel showing graph triples alongside answers
- Multi-document ingestion
- Embedding-based vector search

## Out of Scope

- Production hardening (auth, rate limiting, error recovery) — prototype scope
- Docker containerization — local development only
- REST API — Streamlit is the interface
- CI/CD pipeline — manual testing
- Fine-tuning or training models — using off-the-shelf Groq models
- Document-centric graph nodes (sections, chunks) — product-centric only

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| GRAPH-01 | Phase 1 | Pending |
| GRAPH-02 | Phase 1 | Pending |
| GRAPH-03 | Phase 1 | Pending |
| GRAPH-04 | Phase 1 | Pending |
| GRAPH-05 | Phase 1 | Pending |
| GRAPH-06 | Phase 1 | Pending |
| GRAPH-07 | Phase 1 | Pending |
| INGEST-01 | Phase 1 | Pending |
| INGEST-02 | Phase 1 | Pending |
| INGEST-03 | Phase 1 | Pending |
| INGEST-04 | Phase 1 | Pending |
| INGEST-05 | Phase 1 | Pending |
| INGEST-06 | Phase 1 | Pending |
| QUERY-01 | Phase 2 | Pending |
| QUERY-02 | Phase 2 | Pending |
| QUERY-03 | Phase 2 | Pending |
| QUERY-04 | Phase 2 | Pending |
| QUERY-05 | Phase 2 | Pending |
| QUERY-06 | Phase 2 | Pending |
| UI-01 | Phase 3 | Pending |
| UI-02 | Phase 3 | Pending |
| UI-03 | Phase 3 | Pending |

---
*Last updated: 2026-04-15 after roadmap creation*
