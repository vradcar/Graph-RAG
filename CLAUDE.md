# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
cp .env.example .env            # then fill in API keys if needed
```

## Pipeline Commands

```bash
# 1. Ingest raw data into graph-ready JSON
python -m src.pipeline.ingest --input data/raw/products_sample.json

# 2. Query (modes: graph | vector | hybrid)
python -m src.pipeline.query --question "What replaces TH1110D?" --depth 2 --mode hybrid

# 3. Evaluate retrieval approaches
python -m src.pipeline.evaluate --queries data/eval/queries.json --output data/eval/results.json
```

## Architecture

The pipeline has four layers:

**Graph layer** (`src/graph/`)
- `schema.py` — `EntityNode` and `RelationEdge` dataclasses (the canonical data model)
- `extract.py` — converts raw JSON records into `{nodes, edges}` dicts
- `store.py` — `GraphStore` wraps a `networkx.MultiDiGraph`; `neighbors_multi_hop()` does BFS in both directions

**Retrieval layer** (`src/retrieval/`)
- `graph_retriever.py` — keyword-matches the question to a node, then calls `GraphStore.neighbors_multi_hop()`
- `vector_store.py` — `SimpleVectorStore`: bag-of-words token overlap (placeholder; replace with real embeddings)
- `hybrid_retriever.py` — merges graph and vector hits

**LLM layer** (`src/llm/generate.py`)
- `generate_answer()` is a stub — replace with actual LLM API call (OpenAI, Claude, etc.)

**Pipeline layer** (`src/pipeline/`)
- `ingest.py` — CLI entry point: raw JSON → `data/processed/graph_items.json`
- `query.py` — CLI entry point: loads graph + vector store, runs retrieval, calls `generate_answer()`
- `evaluate.py` — runs query across all entries in an eval set and writes results

**Configuration** (`config/settings.yaml`)  
Controls graph backend (`networkx` or `neo4j`), default traversal depth, retrieval mode, and eval paths. Loaded via `src/common/config.py`.

## Key Extension Points

- **LLM integration**: `src/llm/generate.py` — replace the stub with an actual API call
- **Entity extraction**: `src/graph/extract.py` — `product_records_to_graph_items()` is domain-specific; adapt for new ontologies
- **Vector search**: `src/retrieval/vector_store.py` — swap `SimpleVectorStore` with embeddings (e.g., OpenAI, sentence-transformers)
- **Graph backend**: set `graph.backend: neo4j` in `config/settings.yaml` and implement a Neo4j adapter using the credentials in `.env`

## Data Flow

```
data/raw/*.json
    → ingest.py → extract.py
    → data/processed/graph_items.json
    → query.py → GraphStore + SimpleVectorStore
    → generate_answer() → stdout
```

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Honeywell GraphRAG**

A Graph-based Retrieval-Augmented Generation (GraphRAG) prototype for Honeywell's HVAC product data. It extracts entities and relationships from product documentation into a Neo4j knowledge graph, then answers natural language queries by traversing the graph and generating structured answers via an LLM (Groq).

**Core Value:** Deliver relationship-aware answers about product compatibility, replacements, and specifications that a standard RAG system would miss — by modeling products as interconnected graph nodes rather than flat document chunks.

### Constraints

- **Graph backend**: Neo4j (not networkx)
- **LLM provider**: Groq — model name must be a single configurable placeholder in the codebase for easy experimentation
- **Data**: Single PDF only (T9 thermostat installation guide)
- **Scope**: Demo/prototype quality, not production-grade
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### PDF Parsing
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pymupdf` (fitz) | 1.24.x | Extract text from T9 thermostat PDF | Fastest pure-Python PDF library; preserves layout structure better than pdfplumber for technical docs; handles multi-column and diagram-adjacent text. Active development. |
| `pdfplumber` | 0.11.x | Fallback / table extraction | Better table detection than pymupdf. Use alongside pymupdf only if wiring tables in the PDF need structured extraction. |
### Entity Extraction
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Groq API (`groq` Python SDK) | 0.9.x | LLM-based entity + relationship extraction | Zero-shot or few-shot prompting to extract (Product, Accessory, WiringConfig, HVACSystemType, Spec) entities and typed edges from PDF text chunks. Fastest inference path given the Groq constraint. |
| `instructor` | 1.4.x | Structured output from LLM calls | Wraps Groq chat completions with Pydantic model enforcement — guarantees the LLM returns a valid JSON schema matching your node/edge types rather than freeform text. Significantly reduces extraction parsing bugs. |
| `pydantic` | 2.7.x | Schema validation for extracted entities | Canonical dataclass replacement; `instructor` depends on it; validates node/edge payloads before writing to Neo4j. |
### Graph Storage & Construction
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `neo4j` (official Python driver) | 5.28.1 | Neo4j database connectivity | Already pinned in `requirements.txt`. Stable. Supports both sync and async session patterns. Use sync for this prototype scope. |
| Neo4j Community Edition | 5.x (latest) | Graph database | Constraint: already decided. Run via Docker (`neo4j:5` image). Community edition is sufficient — no RBAC or clustering needed for a demo. |
### Query Processing
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Groq API (`groq` SDK) | 0.9.x | NL → Cypher translation + answer generation | Single LLM provider for both extraction and query phases keeps the dependency surface small. Use a configurable model name (e.g., `llama-3.1-70b-versatile` or `mixtral-8x7b-32768`) stored in `config/settings.yaml`. |
| `neo4j` driver | 5.28.1 | Execute Cypher queries, return graph context | Direct driver usage; no ORM needed at prototype scale. |
### Web UI
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `streamlit` | 1.35.x | Query interface and answer display | Fastest path from Python to interactive web demo; no frontend code required; built-in `st.json()` and `st.write()` for displaying graph context. Gradio is also acceptable but Streamlit has better layout control for multi-panel demos. |
- Text input for natural language question
- Answer display panel
- Expandable "Graph context" section showing the raw triples used
- Link to Neo4j Browser (`http://localhost:7474`) for full visualization
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-dotenv` | 1.0.1 | Load `.env` for Neo4j URI, Groq API key | Always — already in `requirements.txt` |
| `pyyaml` | 6.0.2 | Load `config/settings.yaml` | Already in codebase |
| `networkx` | 3.4.2 | Keep for unit tests / offline graph ops | Keep in dev dependencies; useful for testing graph logic without Neo4j running |
| `pytest` | 8.x | Unit and integration tests | Test extraction logic and query flow in isolation |
| `python-docx` / `tabula-py` | — | NOT needed | Out of scope; PDF is the only source format |
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| PDF parsing | `pymupdf` | `pypdf`, `pdfplumber` | pypdf has weaker layout handling; pdfplumber is a useful complement for tables but not primary |
| Entity extraction | Groq + `instructor` | spaCy NER, LangChain | spaCy lacks domain knowledge; LangChain adds unnecessary weight |
| Graph DB | Neo4j 5.x | networkx (existing) | networkx is in-memory, no persistence, no visualization, no Cypher — not suitable as final backend |
| Query gen | BFS traversal | NL-to-Cypher via LLM | NL-to-Cypher is less reliable for small schemas; BFS is deterministic |
| UI | Streamlit | Gradio, FastAPI+React | Gradio less flexible for multi-panel; FastAPI+React is out of scope complexity |
| LLM provider | Groq | OpenAI, Anthropic | Constraint: Groq required |
## Installation
# Core additions to existing requirements.txt
# Existing (already pinned)
# neo4j==5.28.1
# networkx==3.4.2
# python-dotenv==1.0.1
# pyyaml==6.0.2
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
## Sources
- Existing `requirements.txt` — confirms neo4j==5.28.1, networkx==3.4.2, python-dotenv==1.0.1
- Existing `src/graph/store.py` — confirms BFS traversal pattern to preserve
- `.planning/PROJECT.md` — confirms constraints (Neo4j, Groq, single PDF, Streamlit/Gradio)
- Training data (through August 2025) — pymupdf, instructor, Streamlit community consensus
- NOTE: Groq model names and exact library patch versions should be verified at `https://console.groq.com/docs/models` and `https://pypi.org` before first install
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
