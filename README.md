# Project 6 — GraphRAG (POC Template)

Starter template for a 3-week GraphRAG proof of concept focused on relationship-heavy enterprise questions (product compatibility, supply chain, and compliance).

## What this template gives you
- A minimal end-to-end GraphRAG flow: ingest → graph retrieval → answer generation
- Multi-hop traversal with configurable depth
- Retrieval modes for comparison:
	- `graph` (structured)
	- `vector` (unstructured)
	- `hybrid` (graph + vector)
- Evaluation script to compare approaches across the same query set
- Week-by-week report templates for course deliverables

## Repository layout
```
.
├── config/
│   └── settings.yaml
├── data/
│   ├── raw/
│   ├── processed/
│   └── eval/
├── notebooks/
├── reports/
├── src/
│   ├── common/
│   ├── graph/
│   ├── llm/
│   ├── pipeline/
│   └── retrieval/
├── .env.example
├── requirements.txt
└── README.md
```

## Quick setup (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Update `.env` only if you plan to connect a real LLM provider and/or Neo4j.

## Run the baseline pipeline

### 1) Build graph-ready data from sample input
```bash
python -m src.pipeline.ingest --input data/raw/products_sample.json
```

### 2) Ask a question (graph-only)
```bash
python -m src.pipeline.query --question "What is the modern replacement for TH1110D?" --depth 2 --mode graph
```

### 3) Ask the same question (vector-only)
```bash
python -m src.pipeline.query --question "What is the modern replacement for TH1110D?" --mode vector
```

### 4) Ask the same question (hybrid)
```bash
python -m src.pipeline.query --question "What is the modern replacement for TH1110D?" --depth 2 --mode hybrid
```

### 5) Run retrieval comparison on eval set
```bash
python -m src.pipeline.evaluate --queries data/eval/queries.json --output data/eval/results.json
```

## How this maps to your 3-week plan

### Week 1 — Foundation
- Use `ingest.py` and `query.py` to demonstrate end-to-end GraphRAG.
- Capture graph screenshot and sample Q&A output.
- Fill `reports/week1_template.md`.

### Week 2 — Multi-hop reasoning
- Extend `data/raw/*` with your chosen business domain.
- Use `--depth` to compare single-hop vs multi-hop outputs.
- Document traversal evidence and quality differences.
- Fill `reports/week2_template.md`.

### Week 3 — Hybrid retrieval + evaluation
- Improve document chunks and entity coverage.
- Compare graph-only vs vector-only vs hybrid using `evaluate.py`.
- Summarize relevance, latency, and retrieved evidence.
- Fill `reports/week3_template.md`.

## Where to customize next
- Replace placeholder answer generation in `src/llm/generate.py` with your real LLM API call.
- Upgrade entity extraction in `src/graph/extract.py` for your domain ontology.
- Swap local graph backend with Neo4j adapter if required.
- Add richer scoring metrics (exact match, judge model, human rating) in evaluation.

## Notes
- Current graph backend is `networkx` for fast local prototyping.
- Neo4j dependencies/config are included for future extension.
- This template is intentionally simple so your team can iterate quickly.
