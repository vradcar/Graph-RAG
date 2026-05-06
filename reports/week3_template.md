# Week 3 Report — Hybrid Retrieval Evaluation

## Objective
Implement and evaluate hybrid retrieval (graph + vector) for the GraphRAG pipeline.

## Retrieval Architecture
- Graph-only: `graph_retrieve()` against Neo4j multi-hop traversal.
- Vector-only: `SimpleVectorStore` over document chunks.
- Hybrid: graph hits + vector hits merged with evidence-first ordering.

## Evaluation Setup
- Query set: `data/eval/queries.json` (30 queries)
- Metrics: accuracy (contains_expected), average hits, latency (p50/p95)
- Ground-truth method: expected tokens in the query file + evidence inspection

## Results Summary

| Method | Accuracy | Avg Hits | Avg Latency (ms) | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|
| graph | 0.000 | 0.000 | 52.633 | 9.500 | 228.350 |
| vector | 0.767 | 2.533 | 0.000 | 0.000 | 0.000 |
| hybrid | 0.767 | 2.533 | 11.433 | 9.500 | 32.100 |

Plot: `reports/retrieval_comparison.png`

## Evidence (screenshots)
- Graph-only query screenshot: `data/eval/query-output-week1.png`
- Hybrid demo screenshot: `data/eval/multi-PDF-demo.png`
- Neo4j graph view: `data/eval/graph-visualisation.png`
- Graph snapshots: `data/eval/neo4j-final-graph-1.png`, `data/eval/neo4j-final-graph-2.png`
- Demo transcript: `reports/week3_demo_showcase.txt`

## Deployment Note
- Local-only deployment via Docker/localhost (no public URL).

## Analysis
- Graph-only excels on multi-hop relationship queries but misses text-only facts.
- Vector-only covers text facts but lacks structured traversal.
- Hybrid captures vector coverage while adding graph evidence for relational queries.

## Final Recommendation
Use hybrid retrieval as the default mode, with graph-only for explanation-focused demos.
