# Honeywell GraphRAG

Graph-based Retrieval-Augmented Generation for Honeywell HVAC product documentation. The system extracts entities and relationships from product PDFs into Neo4j, then answers compatibility and wiring questions using graph, vector, or hybrid retrieval with Groq-backed generation.

## What this project does

GraphRAG is built for HVAC product support questions that require multi-hop reasoning, such as replacement chains and installation constraints. It combines:

- **Graph retrieval** from Neo4j for exact, explainable relationships (replacement, compatibility, wiring).
- **Vector retrieval** over document chunks for descriptive queries and fallback coverage.
- **Hybrid fusion** that merges graph evidence with vector snippets into a single answer context.

## Business use case

**Core question:** "What is the modern replacement for this discontinued part, and what does a homeowner need to install it?"

The answer must include replacement mapping plus downstream requirements (wiring terminals, adapters, compatible HVAC system types). This makes multi-hop graph traversal essential.

## Architecture overview

Data flow: PDF + JSON sources → ingest + normalization → graph items + document chunks → Neo4j + vector store → retrieval + fusion → LLM answer.

Key layers:

- **Ingestion:** Parses PDFs, normalizes entities, and writes graph-ready items.
- **Graph layer:** Neo4j stores typed nodes and edges (REPLACED_BY, COMPATIBLE_WITH, REQUIRES, NEEDS_ADAPTER_IF_MISSING).
- **Retrieval layer:** Graph traversal (BFS), vector search, or hybrid fusion.
- **LLM layer:** Generates grounded answers using a structured schema.
- **UI layer:** Streamlit app with depth slider, demo queries, evidence panels, and export.

### Architecture details

**Ingestion path**

1. PDF parsing extracts text and tables into normalized chunks.
2. Entity extraction converts product mentions into typed nodes.
3. Relationship extraction emits edges (replacement, compatibility, wiring).
4. Outputs are serialized to `data/processed/` for traceability and re-runs.

**Graph path (structured)**

- Entities become nodes in Neo4j (Thermostat, HVACSystemType, WiringTerminal, Adapter, Sensor).
- Edges encode constraints (REPLACED_BY, COMPATIBLE_WITH, REQUIRES, NEEDS_ADAPTER_IF_MISSING).
- Multi-hop traversal (BFS) retrieves dependency chains based on depth.

**Vector path (unstructured)**

- Document chunks are indexed in a simple vector store.
- Descriptive queries retrieve top-k chunks with source metadata.

**Fusion and answer generation**

- Graph evidence and vector snippets are merged into a ranked context.
- A structured schema enforces grounded answers and safe refusal.

## Setup

### 1) Create a virtual environment

```
python -m venv .venv
```

Activate it:

- Windows:
	```
	.\.venv\Scripts\activate
	```
- macOS/Linux:
	```
	source .venv/bin/activate
	```

### 2) Install dependencies

```
pip install -r requirements.txt
```

### 3) Configure environment variables

```
cp .env.example .env
```

Fill in:

- `LLM_PROVIDER` (default: `groq`)
- `GROQ_MODEL`
- `GROQ_API_KEY`
- `NEO4J_URI`
- `NEO4J_USER` (use this key for loader compatibility)
- `NEO4J_PASSWORD`

### 4) Start Neo4j

Use local Docker (recommended):

```
docker compose up -d
```

Or run directly:

```
docker run --name graphrag-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password -d neo4j:5
```

If already created:

```
docker start graphrag-neo4j
```

Neo4j Browser: http://localhost:7474

## How to run

### Ingest data

```
python -m src.pipeline.ingest --input data/raw/products_sample.json
```

For PDF-based ingest with replacements:

```
python -m src.pipeline.ingest --input data/raw/t9-thermostat.pdf --replacements data/raw/replacements.json --output data/processed/graph_items.json --verbose
```

Multi-PDF ingest (manifest-driven):

```
python scripts/batch_ingest.py --dry-run --manifest data/raw/manifest.json
```

Then run the same command without `--dry-run` to load into Neo4j.

### Load data into Neo4j (if using graph_items.json)

```
python -m src.graph.neo4j_loader --input data/processed/graph_items.json --verify
```

### Ask a question (CLI)

Graph mode:

```
python -m src.pipeline.query --question "What replaces TH1110D?" --depth 2 --mode graph
```

Hybrid mode:

```
python -m src.pipeline.query --question "What replaces TH1110D?" --depth 2 --mode hybrid
```

### Evaluate retrieval modes

```
python -m src.pipeline.evaluate --queries data/eval/queries.json --output data/eval/results.json
```

Optional exports:

```
python -m src.pipeline.evaluate --queries data/eval/queries.json --output data/eval/results.json --output-csv data/eval/results.csv --summary data/eval/summary.json
```

### Run the Streamlit app

```
python -m streamlit run app.py
```

### Run demo showcase

```
python -m scripts.demo_showcase --mode both --depth 2 --output reports/week3_demo_showcase.txt
```

## Common issues

- **ModuleNotFoundError**: Ensure `.venv` is active and rerun `pip install -r requirements.txt`.
- **Streamlit mismatch**: Use `python -m streamlit run app.py` from the venv.
- **Neo4j connection failure**: Confirm the container is running and `.env` matches `NEO4J_AUTH`.
- **Query returns not_found**: Use concrete entity IDs or run ingestion for the target PDFs.

## Key scripts

- `scripts/batch_ingest.py` — ingest all PDFs from `data/raw/manifest.json`
- `scripts/compare_graph_vs_vector.py` — multi-doc graph vs vector comparison
- `scripts/demo_showcase.py` — curated demo queries for graph vs vector
- `scripts/seed_aura.py` — seed Neo4j Aura (optional)

## Evaluation artifacts

- `data/eval/queries.json` — eval question set
- `data/eval/results.json` — evaluation output
- `data/eval/results.csv` — evaluation output (CSV)
- `data/eval/summary.json` — evaluation summary stats
- `notebooks/scoring_analysis.ipynb` — scoring + plotting
- `reports/retrieval_comparison.png` — evaluation plot

## Reports and documentation

- `reports/week4_report.tex` — final report (Week 4)
- `reports/week3_demo_showcase.txt` — demo output transcript
- `docs/schema.md` — schema and node/edge definitions
- `docs/architecture.md` — architecture notes
- `docs/deployment.md` — Docker deployment steps

## Project layout

```
.
├── app.py
├── config/
├── data/
│   ├── raw/
│   ├── processed/
│   └── eval/
├── docs/
├── notebooks/
├── reports/
├── scripts/
├── src/
└── tests/
```

### Project structure details

- `app.py` — Streamlit UI entry point (depth slider, demo queries, evidence panel).
- `config/` — runtime configuration (retrieval mode, traversal depth, backend selection).
- `data/raw/` — source PDFs, manifest, and seed JSON inputs.
- `data/processed/` — normalized graph items and parsed document chunks.
- `data/eval/` — evaluation queries and computed results.
- `docs/` — schema and architecture documentation for the final submission.
- `notebooks/` — analysis and plotting notebooks for evaluation results.
- `reports/` — final report and demo artifacts.
- `scripts/` — batch ingest, demo runs, and comparisons.
- `src/` — core pipeline code (graph, retrieval, LLM, ingestion, UI adapters).
- `tests/` — unit and integration tests for pipeline components.

## Notes

- Graph backend: Neo4j 5.x
- LLM provider: Groq (configurable in `config/settings.yaml`)
- Default retrieval mode can be set in `config/settings.yaml`
