# Technology Stack

**Project:** Honeywell GraphRAG — T9 Thermostat PDF to Neo4j Knowledge Graph
**Researched:** 2026-04-15
**Scope:** Demo/prototype; single PDF source; no production hardening required

---

## Recommended Stack

### PDF Parsing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pymupdf` (fitz) | 1.24.x | Extract text from T9 thermostat PDF | Fastest pure-Python PDF library; preserves layout structure better than pdfplumber for technical docs; handles multi-column and diagram-adjacent text. Active development. |
| `pdfplumber` | 0.11.x | Fallback / table extraction | Better table detection than pymupdf. Use alongside pymupdf only if wiring tables in the PDF need structured extraction. |

**Do NOT use:** `PyPDF2` — unmaintained, superseded by `pypdf`. `pypdf` is acceptable but pymupdf gives better text fidelity for technical installation guides.

**Confidence:** MEDIUM — based on community consensus as of mid-2025; no live docs verification available in this session.

---

### Entity Extraction

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Groq API (`groq` Python SDK) | 0.9.x | LLM-based entity + relationship extraction | Zero-shot or few-shot prompting to extract (Product, Accessory, WiringConfig, HVACSystemType, Spec) entities and typed edges from PDF text chunks. Fastest inference path given the Groq constraint. |
| `instructor` | 1.4.x | Structured output from LLM calls | Wraps Groq chat completions with Pydantic model enforcement — guarantees the LLM returns a valid JSON schema matching your node/edge types rather than freeform text. Significantly reduces extraction parsing bugs. |
| `pydantic` | 2.7.x | Schema validation for extracted entities | Canonical dataclass replacement; `instructor` depends on it; validates node/edge payloads before writing to Neo4j. |

**Do NOT use:** spaCy NER alone — its off-the-shelf models have no knowledge of HVAC domain terminology. Fine-tuning spaCy is out of scope. LLM extraction is the right call here.

**Do NOT use:** LangChain's entity extraction chains — heavy dependency tree, adds complexity without benefit for a focused prototype. Direct `groq` SDK + `instructor` is simpler and more debuggable.

**Confidence:** MEDIUM-HIGH — `instructor` + Pydantic v2 + Groq SDK is a well-established 2024-2025 pattern for structured LLM extraction.

---

### Graph Storage & Construction

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `neo4j` (official Python driver) | 5.28.1 | Neo4j database connectivity | Already pinned in `requirements.txt`. Stable. Supports both sync and async session patterns. Use sync for this prototype scope. |
| Neo4j Community Edition | 5.x (latest) | Graph database | Constraint: already decided. Run via Docker (`neo4j:5` image). Community edition is sufficient — no RBAC or clustering needed for a demo. |

**Neo4j setup:** Docker is the fastest path for local dev:
```bash
docker run -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5
```
Browser UI at `http://localhost:7474` provides built-in graph visualization — satisfies the "Neo4j graph visualization" requirement without additional tooling.

**Schema approach:** Use Cypher `MERGE` (not `CREATE`) for all node/edge writes to make ingestion idempotent. Define uniqueness constraints on `Product.id` and other primary entity types before first ingest run.

**Confidence:** HIGH — official driver version verified against `requirements.txt`; Neo4j 5.x Docker pattern is standard.

---

### Query Processing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Groq API (`groq` SDK) | 0.9.x | NL → Cypher translation + answer generation | Single LLM provider for both extraction and query phases keeps the dependency surface small. Use a configurable model name (e.g., `llama-3.1-70b-versatile` or `mixtral-8x7b-32768`) stored in `config/settings.yaml`. |
| `neo4j` driver | 5.28.1 | Execute Cypher queries, return graph context | Direct driver usage; no ORM needed at prototype scale. |

**Query flow:**
1. User submits natural language question
2. LLM (Groq) generates a Cypher query OR the pipeline uses keyword → node matching + BFS traversal (existing pattern from `graph_retriever.py`)
3. Neo4j executes; returns subgraph
4. LLM (Groq) generates a natural language answer from graph context

**NL-to-Cypher vs BFS:** For a single-document prototype with a small, well-defined schema, BFS traversal from a matched node is more reliable than asking the LLM to generate Cypher. Reserve NL-to-Cypher for a stretch goal. The existing `graph_retriever.py` + `GraphStore.neighbors_multi_hop()` pattern is the right starting point — just port it to Neo4j driver calls.

**Groq model name:** Make it a single `settings.yaml` key (`llm.model`). Suggested default: `llama-3.1-70b-versatile` (strong instruction following, good for structured tasks). Fallback: `mixtral-8x7b-32768`.

**Confidence:** MEDIUM — Groq model availability changes frequently; verify current model list at `https://console.groq.com/docs/models` before committing a default.

---

### Web UI

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `streamlit` | 1.35.x | Query interface and answer display | Fastest path from Python to interactive web demo; no frontend code required; built-in `st.json()` and `st.write()` for displaying graph context. Gradio is also acceptable but Streamlit has better layout control for multi-panel demos. |

**UI components to implement:**
- Text input for natural language question
- Answer display panel
- Expandable "Graph context" section showing the raw triples used
- Link to Neo4j Browser (`http://localhost:7474`) for full visualization

**Do NOT use:** Gradio — fine for ML model demos but its component model makes multi-panel layouts (answer + graph context + metadata) more awkward than Streamlit. Streamlit's session state also integrates more cleanly with long-running Neo4j connections.

**Confidence:** MEDIUM-HIGH — Streamlit 1.35 is current as of mid-2025.

---

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-dotenv` | 1.0.1 | Load `.env` for Neo4j URI, Groq API key | Always — already in `requirements.txt` |
| `pyyaml` | 6.0.2 | Load `config/settings.yaml` | Already in codebase |
| `networkx` | 3.4.2 | Keep for unit tests / offline graph ops | Keep in dev dependencies; useful for testing graph logic without Neo4j running |
| `pytest` | 8.x | Unit and integration tests | Test extraction logic and query flow in isolation |
| `python-docx` / `tabula-py` | — | NOT needed | Out of scope; PDF is the only source format |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| PDF parsing | `pymupdf` | `pypdf`, `pdfplumber` | pypdf has weaker layout handling; pdfplumber is a useful complement for tables but not primary |
| Entity extraction | Groq + `instructor` | spaCy NER, LangChain | spaCy lacks domain knowledge; LangChain adds unnecessary weight |
| Graph DB | Neo4j 5.x | networkx (existing) | networkx is in-memory, no persistence, no visualization, no Cypher — not suitable as final backend |
| Query gen | BFS traversal | NL-to-Cypher via LLM | NL-to-Cypher is less reliable for small schemas; BFS is deterministic |
| UI | Streamlit | Gradio, FastAPI+React | Gradio less flexible for multi-panel; FastAPI+React is out of scope complexity |
| LLM provider | Groq | OpenAI, Anthropic | Constraint: Groq required |

---

## Installation

```bash
# Core additions to existing requirements.txt
pip install pymupdf==1.24.11
pip install groq==0.9.0
pip install instructor==1.4.3
pip install pydantic==2.7.4
pip install streamlit==1.35.0
pip install pdfplumber==0.11.4   # optional, for table-heavy pages
pip install pytest==8.2.2

# Existing (already pinned)
# neo4j==5.28.1
# networkx==3.4.2
# python-dotenv==1.0.1
# pyyaml==6.0.2
```

---

## Confidence Summary

| Layer | Confidence | Notes |
|-------|------------|-------|
| Neo4j driver (5.28.1) | HIGH | Verified in requirements.txt |
| Neo4j 5.x Docker setup | HIGH | Standard, well-documented pattern |
| Groq SDK (0.9.x) | MEDIUM | Version approximate; verify at pypi.org/project/groq |
| pymupdf for PDF parsing | MEDIUM | Strong community consensus; no live docs check |
| instructor + Pydantic v2 | MEDIUM-HIGH | Established 2024-2025 pattern |
| Streamlit (1.35.x) | MEDIUM | Version approximate; verify at pypi.org/project/streamlit |
| BFS over NL-to-Cypher | HIGH | Fits the constrained schema and prototype scope |

---

## Sources

- Existing `requirements.txt` — confirms neo4j==5.28.1, networkx==3.4.2, python-dotenv==1.0.1
- Existing `src/graph/store.py` — confirms BFS traversal pattern to preserve
- `.planning/PROJECT.md` — confirms constraints (Neo4j, Groq, single PDF, Streamlit/Gradio)
- Training data (through August 2025) — pymupdf, instructor, Streamlit community consensus
- NOTE: Groq model names and exact library patch versions should be verified at `https://console.groq.com/docs/models` and `https://pypi.org` before first install
