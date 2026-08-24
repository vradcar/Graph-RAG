# Honeywell GraphRAG

Graph-based Retrieval-Augmented Generation for Honeywell HVAC product documentation. The system extracts entities and relationships from product PDFs into Neo4j, then answers compatibility and wiring questions using graph, vector, or hybrid retrieval with Groq-backed generation.

## What this project does

GraphRAG is built for HVAC product support questions that require multi-hop reasoning across product documentation. It combines:

- **Graph retrieval** from Neo4j for exact, explainable relationships (compatibility, wiring requirements, adapters).
- **Vector retrieval** — semantic search (sentence-transformer embeddings) over node/document text, used as a fallback when graph traversal finds nothing.
- **Hybrid fusion** that merges graph evidence with vector snippets into a single ranked context.
- **Grounded generation** — the LLM answers using only retrieved graph evidence and explicitly returns a "not found" response with a rephrasing suggestion when nothing relevant is retrieved, rather than guessing.

## Business use case

**Core question:** "Is this accessory compatible with my thermostat, and what does installing it require?"

The answer needs to combine compatibility facts with downstream requirements (wiring terminals, C-wire adapters, supported HVAC system types) — often by crossing multiple source documents (e.g. a wiring-module PDF plus a thermostat install guide). This is what makes graph traversal valuable over flat document search: `scripts/compare_graph_vs_vector.py` demonstrates several such cross-document questions where graph retrieval succeeds and plain vector search cannot bridge the two documents.

The schema also defines `REPLACES`/`REPLACED_BY` edges for discontinued-product replacement chains, and `src/llm/generate.py` has a dedicated answer path for that question shape — but the currently-ingested PDF corpus (T9, T6 Pro, T10 Pro, THP9045 wiring module) is installation/compatibility documentation and doesn't contain any replacement-chain facts. That capability is only exercised against the older synthetic dataset (`data/raw/products_sample.json` + `data/raw/replacements.json`) described under [Legacy ingest path](#legacy-single-json-ingest-path) below.

## Architecture overview

Data flow: PDFs → LLM-based entity/relationship extraction → per-doc corpus JSON → Neo4j (+ vector index built from graph text at query time) → retrieval → LLM answer.

Key layers:

- **Ingestion (`src/ingest/`, `scripts/batch_ingest.py`):** Parses PDFs (pymupdf/pdfplumber), extracts typed entities and edges via Groq, normalizes, and caches the result per-document as `data/processed/_<doc_id>_corpus.json`.
- **Graph layer (`src/graph/`):** Neo4j stores typed nodes and edges (`COMPATIBLE_WITH`, `REQUIRES`, `NEEDS_ADAPTER_IF_MISSING`, `SUPPORTS_WIRING`, `HAS_SPEC`, `MOUNTS_ON`, etc.) with per-edge `source_doc` provenance.
- **Retrieval layer (`src/retrieval/`):** A staged pipeline — regex/keyword fast path, then LLM-guided entity resolution + BFS graph traversal, then semantic vector fallback — see `src/pipeline/query.py:run_query_structured` for the exact stage order.
- **LLM layer (`src/llm/generate.py`):** Generates a structured, evidence-grounded answer (Groq, via `instructor`), with a deterministic non-LLM fallback template when no API key is configured.
- **UI layer (`app.py`):** Streamlit app with a depth slider, demo queries, an evidence panel, and export.

### Retrieval pipeline detail

`run_query_structured` (`src/pipeline/query.py`) tries each stage in order and stops at the first one that finds evidence:

1. **Fast path** — regex/keyword match directly against the graph, no LLM call.
2. **LLM query understanding** — Groq extracts entities + intent from the question, resolves them against known graph node IDs, then BFS-traverses from each (`GraphStore.neighbors_multi_hop`, depth configurable via `--depth`).
3. **Vector fallback** — semantic search (sentence-transformer embeddings, cosine similarity) over all node text pulled from Neo4j, then 1-hop graph expansion from the matched nodes.
4. **Answer generation** — Groq produces a structured answer constrained to the retrieved evidence; if nothing was retrieved by any stage, it returns `not_found=True` with a suggestion for how to rephrase the question.

There's no separate "mode" flag for graph vs. vector vs. hybrid at query time — the CLI runs this same staged pipeline regardless, and vector search only engages if graph retrieval comes up empty. (`scripts/demo_showcase.py` and `scripts/compare_graph_vs_vector.py`, used for comparing retrieval strategies, do accept an explicit `--mode`/mode selection — see [Compare retrieval strategies](#compare-retrieval-strategies).)

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

The first vector search will download the `all-MiniLM-L6-v2` embedding model (~80MB) from Hugging Face and cache it locally — no API key needed for this part.

### 3) Configure environment variables

**Only if you don't already have a `.env`** — this command overwrites one if it exists, replacing working credentials with placeholders:

```
cp .env.example .env
```

If you already have a `.env`, edit it by hand instead and skip the copy.

Fill in:

- `LLM_PROVIDER` (default: `groq`)
- `GROQ_MODEL`
- `GROQ_API_KEY`
- `NEO4J_URI`
- `NEO4J_USER` — **use exactly this key name.** `NEO4J_USERNAME` is not read anywhere in the codebase; if that's the only one set, every script silently falls back to a hardcoded default of `neo4j`.
- `NEO4J_PASSWORD`

> **Aura gotcha:** if you're using Neo4j Aura, the username is **not** `neo4j` by default on newer instances — it's the instance ID shown in your connection details (e.g. `3b68cef5`), and the credentials file Aura downloads on instance creation (`Neo4j-<id>-Created-<date>.txt`) has the exact values. Don't check that file into git.

### 4) Get a Neo4j instance running

**Option A — Neo4j Aura (recommended):** local Docker volumes don't travel with the repo and their credentials are easy to lose track of between machines/teammates. Aura's free tier gives you a small, persistent, remotely-reachable instance instead:

1. Create a free instance at [console.neo4j.io](https://console.neo4j.io).
2. Copy the connection URI, username, and password into `.env` (see the gotcha above).
3. Seed it from the committed corpus (no LLM calls, safe to re-run — see below).

**Option B — local Docker:**

```
docker compose up -d neo4j
```

Neo4j Browser: http://localhost:7474 (default local dev credentials: `neo4j` / `devpassword`, per `docker-compose.yml` — only applies the first time the `neo4j_data` volume is created).

### 5) Load data into Neo4j

If you already have `data/processed/_<doc_id>_corpus.json` files (they're committed for the current 4-doc corpus), just seed:

```
python scripts/seed_aura.py
```

Works against Aura or local Docker — it just reads `NEO4J_URI`/`NEO4J_USER`/`NEO4J_PASSWORD` from `.env`. It's idempotent (MERGE writes), so re-running it is safe. Useful flags:

```
python scripts/seed_aura.py --verify              # print node/edge counts, no write
python scripts/seed_aura.py --doc-id t9_install_guide   # seed a single document
python scripts/seed_aura.py --reset                # wipe first, then seed fresh
```

## How to run

### Ask a question (CLI)

```
python -m src.pipeline.query --question "What is the T9 thermostat compatible with?" --depth 1
```

```
python -m src.pipeline.query --question "Does the Honeywell Home thermostat need a C-wire adapter?" --depth 2 --provider groq
```

If nothing relevant is found in the graph, you'll get a `not_found` response with a suggested rephrasing rather than a hallucinated answer.

### Run the Streamlit app

```
python -m streamlit run app.py
```

### Re-run ingestion from source PDFs

Only needed if you're changing the source documents or the extraction prompt/schema — the corpus JSONs are already committed and step 5 above (`seed_aura.py`) is normally enough.

```
python scripts/batch_ingest.py --dry-run          # extract + cache corpus JSON only, no Neo4j write
python scripts/batch_ingest.py                    # extract (from cache if present) and load into Neo4j
python scripts/batch_ingest.py --doc-id t9_install_guide --force   # re-extract one doc, bypassing cache
```

Reads `data/raw/manifest.json` (4 docs: T9, T6 Pro, T10 Pro, THP9045 wiring module) and the PDFs in `data/raw/`. Requires `GROQ_API_KEY` (or `OPENROUTER_API_KEY`/`GEMINI_API_KEY` via `--inferencer`) for any doc not already cached.

### Legacy single-JSON ingest path

An older, separate demo dataset (TH1110D / T6-PRO / SMK-100) with explicit replacement-chain (`REPLACES`/`REPLACED_BY`) edges, kept for exercising that code path:

```
python -m src.pipeline.ingest --input data/raw/products_sample.json
python -m src.graph.neo4j_loader --doc-id legacy_products --input data/processed/graph_items.json --verify
```

This writes into the same graph as the PDF corpus (additively) rather than replacing it — the two datasets don't share entities.

### Compare retrieval strategies

Two separate, non-interchangeable eval pipelines exist — pick the one that matches what you're testing:

**Multi-doc graph vs. vector comparison** (matches the current 4-PDF corpus — use this one):

```
python -m scripts.compare_graph_vs_vector
```

Runs `data/eval/multi_doc_queries.json` (cross-document compatibility/wiring questions, several intentionally requiring graph traversal that vector search can't bridge) against the live graph plus a vector store built from `data/raw/doc_chunks_corpus.json`. Writes `data/eval/multi_doc_results.json` and a human-readable `data/eval/multi_doc_comparison.md`. Add `--with-llm` to also generate prose answers (requires an API key).

**Legacy single-metric eval** (matches the older synthetic dataset — `data/eval/queries.json`'s `TH1110D`/`T6-PRO` questions won't resolve against the current PDF corpus):

```
python -m src.pipeline.evaluate --queries data/eval/queries.json --output data/eval/results.json --output-csv data/eval/results.csv --summary data/eval/summary.json
```

### Run demo showcase

```
python -m scripts.demo_showcase --mode both --depth 2 --output reports/week3_demo_showcase.txt
```

`--mode` accepts `graph`, `vector`, `hybrid`, or `both`; use `--query N` to run a single one of the 8 curated demo questions.

## Run the tests

```
python -m pytest tests/ -q -m "not integration"
```

148 passed, 3 skipped, 0 failed as of the last full run. Everything external (Neo4j, LLM calls) is mocked in the non-integration suite, so this needs no live services or API keys. A handful of tests are marked `@pytest.mark.integration` and require a running Neo4j plus a real API key — run those separately with `-m integration` when you actually want to exercise the live stack:

```
python -m pytest tests/ -q -m integration
```

## Common issues

- **ModuleNotFoundError: No module named 'src'**: run scripts as modules from the repo root (`python -m ...`), or set `PYTHONPATH=.` first — `scripts/seed_aura.py` and a few others import `src.*` at the top level.
- **`neo4j.exceptions.AuthError: Unauthorized`**: almost always one of — (a) `.env` has `NEO4J_USERNAME` instead of `NEO4J_USER` (the code doesn't read the former, see Setup step 3); (b) on Aura, the username isn't `neo4j` — check the downloaded credentials file; (c) a local Docker volume from a previous run has different baked-in credentials than what's currently in `.env` (Neo4j only applies `NEO4J_AUTH` the first time a volume is created) — either recover the original password or wipe the volume and reseed.
- **`ModuleNotFoundError: No module named 'sentence_transformers'` or `'fitz'`**: rerun `pip install -r requirements.txt` inside the active `.venv` — both `sentence-transformers` (vector search) and `pymupdf` (PDF parsing, imported as `fitz`) are declared dependencies.
- **UnicodeEncodeError on Windows** printing `→`/`…` to the console: set `PYTHONIOENCODING=utf-8` before running.
- **Streamlit mismatch**: use `python -m streamlit run app.py` from the venv, not a bare `streamlit run`.
- **Query returns `not_found`**: either the graph doesn't have relevant data, or the question doesn't match a real node/relation — try one of the suggested rephrasings in the response, or check actual node IDs in Neo4j Browser / Aura console.

## Key scripts

- `scripts/batch_ingest.py` — extract + load all PDFs from `data/raw/manifest.json` (the current corpus)
- `scripts/seed_aura.py` — load the already-extracted corpus JSON into any Neo4j instance (Aura or local); no LLM calls, safe to re-run
- `scripts/compare_graph_vs_vector.py` — multi-doc graph vs. vector comparison against the current corpus
- `scripts/demo_showcase.py` — curated demo queries across graph/vector/hybrid modes

## Evaluation artifacts

Current corpus (multi-doc):
- `data/eval/multi_doc_queries.json` — eval question set
- `data/eval/multi_doc_results.json` — evaluation output
- `data/eval/multi_doc_comparison.md` — human-readable comparison report

Legacy synthetic dataset:
- `data/eval/queries.json` — eval question set
- `data/eval/results.json` / `results.csv` / `summary.json` — evaluation output
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
- `config/` — runtime configuration (retrieval depth default, backend selection, LLM provider/model).
- `data/raw/` — source PDFs, manifest, legacy JSON inputs.
- `data/processed/` — cached per-document extraction output (`_<doc_id>_corpus.json`).
- `data/eval/` — evaluation queries and computed results (current + legacy sets).
- `docs/` — schema and architecture documentation.
- `notebooks/` — analysis and plotting notebooks for evaluation results.
- `reports/` — final report and demo artifacts.
- `scripts/` — batch ingest, Aura seeding, demo runs, retrieval comparisons.
- `src/` — core pipeline code (graph, retrieval, LLM, ingestion, config).
- `tests/` — unit and integration tests for pipeline components.

## Notes

- Graph backend: Neo4j 5.x (Aura or self-hosted — no networkx fallback in the current query path).
- LLM provider: Groq, model name configurable via `GROQ_MODEL` env var or `config/settings.yaml`'s `llm.model`.
- Vector search: sentence-transformer embeddings (`all-MiniLM-L6-v2`), local/CPU, no separate API key.
- Default retrieval depth and other pipeline defaults live in `config/settings.yaml`; `NEO4J_URI`/`NEO4J_USER` env vars always take precedence over that file's values.
