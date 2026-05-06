# Honeywell GraphRAG

Graph-based Retrieval-Augmented Generation for Honeywell HVAC product documentation. The system extracts entities and relationships from product PDFs into Neo4j, then answers compatibility and wiring questions using graph, vector, or hybrid retrieval with Groq-backed generation.

## Status (T1–T5)

| Track | Status | Notes |
|---|---|---|
| T1 — Ingestion + multi-doc verification | Done | Multi-PDF ingest, provenance, and graph vs vector comparison complete. |
| T2 — Evaluation expansion | Partial | Needs expanded query set + richer metrics (precision@k, p50/p95 latency, CSV). |
| T3 — Demo UX + showcase | Partial | Demo scripts exist; docs and showcase outputs still need polishing. |
| T4 — Deployment | Partial | Docker Compose + deployment guide exist; no public hosted URL. |
| T5 — Report + artifacts | In progress | Week 3 report + screenshots + slide/video references pending. |

## Quickstart

See [HOW_TO_USE.md](HOW_TO_USE.md) for local setup, ingestion, evaluation, and UI steps.

## Deployment

Docker-based deployment instructions are in [docs/deployment.md](docs/deployment.md).
Current submission uses local Docker/localhost only (no public URL).

## Key scripts

- `scripts/batch_ingest.py` — ingest all PDFs from `data/raw/manifest.json`
- `scripts/compare_graph_vs_vector.py` — multi-doc graph vs vector comparison
- `scripts/demo_showcase.py` — curated demo queries for graph vs vector
- `scripts/seed_aura.py` — seed Neo4j Aura (optional)

## Evaluation artifacts

- `data/eval/queries.json` — eval question set
- `data/eval/results.json` — evaluation output
- `notebooks/scoring_analysis.ipynb` — scoring + plotting
- `reports/retrieval_comparison.png` — evaluation plot

## Documentation

- [docs/schema.md](docs/schema.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/deployment.md](docs/deployment.md)

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

## Notes

- Graph backend: Neo4j 5.x
- LLM provider: Groq (configurable in `config/settings.yaml`)
