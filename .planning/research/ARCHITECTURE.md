# Architecture Patterns

**Domain:** GraphRAG on product documentation (Honeywell T9 thermostat PDF)
**Researched:** 2026-04-15
**Confidence:** HIGH — derived from existing skeleton codebase + established GraphRAG pipeline conventions

---

## Recommended Architecture

The system is a linear ingestion + query-time pipeline. Two distinct runtime paths:

1. **Ingestion path** (run once or on data change): PDF → entities+relations → Neo4j
2. **Query path** (per user request): NL question → entity detection → Cypher traversal → context assembly → Groq → answer

```
INGESTION PATH
==============
data/raw/t9-thermostat.pdf
        |
        v
 [1] PDF Parser (pdfplumber / PyMuPDF)
        | raw text per page
        v
 [2] LLM Entity Extractor (Groq)
        | structured JSON: nodes + edges
        v
 [3] Graph Schema Validator (schema.py)
        | validated EntityNode / RelationEdge objects
        v
 [4] Neo4j Writer (store.py - Neo4j adapter)
        | MERGE statements via neo4j-driver
        v
  Neo4j database

QUERY PATH
==========
User (Streamlit/Gradio UI)
        |
        v
 [5] Query Understanding (query.py)
        | entity candidates extracted from question text
        v
 [6] Cypher Traversal (graph_retriever.py - Neo4j adapter)
        | multi-hop neighbor subgraph
        v
 [7] Context Assembler (generate.py preamble)
        | formatted triples + node properties
        v
 [8] LLM Generator (Groq API)
        | natural language answer
        v
 [9] Web UI (Streamlit/Gradio)
        | displayed to user + optional graph visualization
```

---

## Component Boundaries

### Ingestion Components

| Component | Module | Responsibility | Input | Output |
|-----------|--------|---------------|-------|--------|
| PDF Parser | `src/ingest/pdf_parser.py` (new) | Extract raw text from T9 PDF, page by page | PDF file path | List of `{page, text}` dicts |
| LLM Entity Extractor | `src/ingest/entity_extractor.py` (new) | Prompt Groq to identify products, accessories, wiring configs, HVAC system types, and relations | Page text | `{nodes: [...], edges: [...]}` JSON |
| Graph Schema Validator | `src/graph/schema.py` (exists) | Validate and type-cast raw dicts into `EntityNode` / `RelationEdge` dataclasses | Raw dicts | Typed dataclass instances |
| Neo4j Writer | `src/graph/store.py` (replace networkx with neo4j-driver) | MERGE nodes and edges into Neo4j; enforce uniqueness on `node_id` | EntityNode / RelationEdge | Neo4j graph mutations |

### Query Components

| Component | Module | Responsibility | Input | Output |
|-----------|--------|---------------|-------|--------|
| Query Understander | `src/retrieval/graph_retriever.py` (extend) | Extract entity mentions from natural language question | Question string | List of candidate node IDs |
| Cypher Traversal | `src/retrieval/graph_retriever.py` (replace BFS with Cypher) | Run parameterized multi-hop Cypher query; return subgraph triples | Node IDs + depth | List of `(source, relation, target)` tuples with properties |
| Context Assembler | `src/llm/generate.py` (extend preamble logic) | Format graph triples into an LLM-consumable prompt section | Triples list | Formatted string block |
| LLM Generator | `src/llm/generate.py` (replace stub) | Call Groq chat completion with system prompt + context + question | Prompt string | Answer string |
| Web UI | `app.py` (new) | Accept user question, invoke query path, display answer + graph viz | HTTP request | Rendered UI |

### Cross-Cutting

| Component | Module | Responsibility |
|-----------|--------|---------------|
| Config loader | `src/common/config.py` (exists) | Load `config/settings.yaml`; expose Neo4j URI/credentials, Groq model name, traversal depth |
| Graph schema definition | `src/graph/schema.py` (exists) | Canonical node kinds: `Product`, `Accessory`, `WiringConfig`, `HvacSystemType`; canonical edge types: `COMPATIBLE_WITH`, `REPLACES`, `REQUIRES`, `HAS_SPEC` |

---

## Data Flow

### Ingestion (detailed)

```
PDF bytes
  --> pdfplumber/PyMuPDF --> List[{page_num, text}]
  --> chunk by page (or logical section boundaries)
  --> for each chunk:
        Groq prompt (structured output / JSON mode)
        --> {nodes: [{node_id, label, kind, properties}],
             edges: [{source_id, target_id, relation, properties}]}
  --> validate with schema.py dataclasses
  --> neo4j-driver: MERGE (n:Product {node_id: $id}) SET n += $props
                    MERGE (a)-[:COMPATIBLE_WITH]->(b)
  --> idempotent: re-running ingestion does not duplicate data
```

Key invariant: **node_id is the stable identifier** (e.g., `RCHT9510WF` for the T9). All MERGE operations key on `node_id`.

### Query (detailed)

```
"What wiring config does the T9 use for a heat pump?"
  --> regex + simple NER: candidate entities = ["T9", "RCHT9510WF"]
  --> for each entity found in Neo4j:
        MATCH path = (n {node_id: $id})-[*1..2]-(m)
        RETURN n, relationships(path), m
  --> triples assembled: [("RCHT9510WF", "COMPATIBLE_WITH", "WiringConfig_Y"), ...]
  --> system prompt + triples + question --> Groq chat API
  --> answer: "The T9 supports Y wiring configurations for heat pumps..."
  --> UI renders answer text + optional Neo4j Browser iframe or py2neo subgraph viz
```

---

## Suggested Build Order

Build order follows data dependency: you cannot query what you haven't stored.

### Phase 1 — Foundation (graph schema + Neo4j connection)
**Why first:** Everything else depends on a working Neo4j store.
- Implement Neo4j adapter in `src/graph/store.py` (replace networkx)
- Validate schema: `EntityNode` kinds, `RelationEdge` types
- Write smoke test: connect, MERGE one node, read it back
- Deliverable: `GraphStore` backed by Neo4j, passing unit tests

### Phase 2 — Ingestion pipeline (PDF → Neo4j)
**Why second:** Query path needs data in the graph.
- PDF parser: extract text from `data/raw/t9-thermostat.pdf`
- LLM entity extractor: prompt Groq, parse JSON response, validate schema
- Wire into `src/pipeline/ingest.py`
- Deliverable: `python -m src.pipeline.ingest --input data/raw/t9-thermostat.pdf` populates Neo4j with T9 product graph

### Phase 3 — Query pipeline (Cypher traversal + Groq answer)
**Why third:** Core value of the system; requires Phase 1+2.
- Replace regex BFS in `graph_retriever.py` with parameterized Cypher
- Replace stub in `generate.py` with Groq chat completion call
- Wire into `src/pipeline/query.py`
- Deliverable: `python -m src.pipeline.query --question "..." --mode graph` returns a real answer

### Phase 4 — Web UI + graph visualization
**Why last:** Cosmetic layer on top of working pipeline.
- `app.py`: Streamlit or Gradio interface wrapping `query.py` logic
- Neo4j graph viz: embed Neo4j Browser, use `pyvis`, or `streamlit-agraph`
- Deliverable: browser-accessible demo at `localhost:8501`

---

## Component Communication Map

```
app.py
  --> src/pipeline/query.py
        --> src/retrieval/graph_retriever.py --> src/graph/store.py --> Neo4j
        --> src/llm/generate.py --> Groq API

src/pipeline/ingest.py
  --> src/ingest/pdf_parser.py   (new)
  --> src/ingest/entity_extractor.py  (new) --> Groq API
  --> src/graph/store.py --> Neo4j
```

The UI (app.py) and the CLI (pipeline/query.py) share the same retrieval + generation code — they are alternative entry points, not separate systems.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Storing chunks as nodes
**What it is:** Creating `Chunk` or `DocumentSection` nodes in the graph alongside product nodes.
**Why bad:** The project is explicitly product-centric. Mixed-type graphs pollute traversals and make Cypher queries more complex. The retrieval context should be graph triples about products, not document text.
**Instead:** Extract only product-centric entities (Product, Accessory, WiringConfig, HvacSystemType) during ingestion. Raw text lives only in the LLM prompt during extraction; it is not stored.

### Anti-Pattern 2: Dynamic Cypher string construction from user input
**What it is:** Building Cypher strings by concatenating the user's question or extracted entity names.
**Why bad:** Cypher injection risk; also unpredictable query shape.
**Instead:** Extract entity IDs from the question, then run a parameterized Cypher query (`{node_id: $id}`) — no string interpolation of user-controlled values.

### Anti-Pattern 3: Rebuilding the in-memory networkx graph on every query
**What it is:** The current `query.py` loads `graph_items.json` and rebuilds a networkx graph at startup for every invocation.
**Why bad:** O(N) startup cost per query; not needed when Neo4j is the store.
**Instead:** The Neo4j adapter connects to a persistent database — no graph reconstruction at query time. Connection pooling via the neo4j-driver handles reuse.

### Anti-Pattern 4: Hardcoding the Groq model name
**What it is:** Embedding `"llama3-70b-8192"` (or any model name) as a string literal in `generate.py`.
**Why bad:** The project requires easy model swapping for experimentation.
**Instead:** Single config key `llm.model` in `config/settings.yaml`, read via `src/common/config.py`. No other file references the model string.

---

## Scalability Notes

This is a prototype with a single PDF. The architecture choices that matter for this scope:

| Concern | At prototype scale (1 PDF, ~100 nodes) | If extended (10+ PDFs, 10K+ nodes) |
|---------|----------------------------------------|-------------------------------------|
| Ingestion | Single Groq call per page chunk, sequential | Batch + async Groq calls; parallel page processing |
| Graph storage | Neo4j local (Docker) | Neo4j AuraDB or self-hosted cluster |
| Query latency | Single Cypher hop + 1 Groq call (~2-4s) | Add full-text index on `node_id`; cache frequent queries |
| Entity extraction accuracy | Manual prompt engineering | Few-shot examples from domain; evaluate extraction F1 |

---

## Sources

- Existing skeleton codebase: `src/graph/`, `src/retrieval/`, `src/pipeline/`, `src/llm/` (HIGH confidence — direct code reading)
- Project definition: `.planning/PROJECT.md` (HIGH confidence — authoritative project context)
- GraphRAG pipeline conventions: Microsoft GraphRAG, Neo4j GraphRAG Python package architecture patterns (MEDIUM confidence — training data, architecture is stable and well-established)
