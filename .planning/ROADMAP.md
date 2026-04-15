# ROADMAP — Honeywell GraphRAG

## Phases

- [ ] **Phase 1: Graph Schema & Ingestion** - Extract T9 thermostat data from PDF and populate a typed Neo4j knowledge graph
- [ ] **Phase 2: Query Pipeline** - Answer natural language questions via multi-hop Cypher traversal and Groq LLM
- [ ] **Phase 3: Web UI** - Streamlit interface for querying and Neo4j graph visualization

## Phase Details

### Phase 1: Graph Schema & Ingestion
**Goal**: The T9 thermostat PDF is fully parsed and all product entities, relationships, and specs are stored in Neo4j with no duplicates
**Depends on**: Nothing (first phase)
**Requirements**: GRAPH-01, GRAPH-02, GRAPH-03, GRAPH-04, GRAPH-05, GRAPH-06, GRAPH-07, INGEST-01, INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06
**Success Criteria** (what must be TRUE):
  1. Running the ingest command against the T9 PDF populates Neo4j with Product, Accessory, WiringConfig, HVACSystemType, and Spec nodes
  2. Neo4j Browser shows typed edges (COMPATIBLE_WITH, REPLACES, SUPPORTS_WIRING, HAS_SPEC) connecting nodes as expected
  3. Re-running ingest twice produces the same node and edge counts — no duplicates
  4. Extracted relationships use only the closed-world enum of allowed types (no invented relationship names)
  5. Neo4j Browser at localhost:7474 shows the populated graph — nodes and edges are visually browsable
**Plans**: 5 plans

Plans:
- [ ] 01-01-PLAN.md — Schema enum constants + settings.yaml Neo4j/LLM config + requirements.txt
- [ ] 01-02-PLAN.md — Neo4jGraphStore with MERGE writes, uniqueness constraints, unit tests
- [ ] 01-03-PLAN.md — PDF parser (pymupdf prose + pdfplumber tables) + parser tests
- [ ] 01-04-PLAN.md — Entity extractor (Groq+instructor+Pydantic enum) + normalizer + tests
- [ ] 01-05-PLAN.md — Ingest CLI wiring all components + idempotency integration test

### Phase 2: Query Pipeline
**Goal**: A developer can ask natural language questions about T9 compatibility and replacements and receive correct, graph-grounded answers from Groq
**Depends on**: Phase 1
**Requirements**: QUERY-01, QUERY-02, QUERY-03, QUERY-04, QUERY-05, QUERY-06
**Success Criteria** (what must be TRUE):
  1. Running the query command with a natural language question returns an LLM-generated answer (not an error or placeholder)
  2. At least 3 canned demo queries (e.g. "What wiring configs does the T9 support?", "What does the T9 replace?", "What specs does the T9 have?") produce verified correct answers
  3. Answers reference graph-traversal results (multi-hop, depth 2+), not hallucinated content
  4. Groq model name is changed in settings.yaml alone — no code edits required
**Plans**: TBD

### Phase 3: Web UI
**Goal**: A user can query the knowledge graph through a web browser and see answers alongside a link to the Neo4j graph visualization
**Depends on**: Phase 2
**Requirements**: UI-01, UI-02, UI-03
**Success Criteria** (what must be TRUE):
  1. Opening the Streamlit app in a browser presents a query input field
  2. Submitting a question displays the LLM-generated answer on the page
  3. The UI provides a working link or embed to Neo4j Browser showing the live graph
**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Graph Schema & Ingestion | 0/5 | Not started | - |
| 2. Query Pipeline | 0/? | Not started | - |
| 3. Web UI | 0/? | Not started | - |
