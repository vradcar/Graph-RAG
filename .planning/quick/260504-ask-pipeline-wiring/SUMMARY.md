---
slug: ask-pipeline-wiring
date: 2026-05-04
status: complete
---

# Summary: Wire Full Pipeline to Ask Tab

## What changed

`src/pipeline/query.py:run_query_structured` is now a 4-stage orchestrator. The Streamlit "Ask" tab and "Multi-Doc Queries" tab both call it unchanged, so they inherit the upgrade with no UI edits.

## Stages (executed in order, short-circuit when triples found)

1. **Fast path** — `graph_retrieve()` (regex + replacement-keyword Cypher). Unchanged. Curated demo queries still hit this and pay no extra latency.
2. **LLM query understanding** — `understand_query()` calls Groq via `instructor` to extract entities, intent, and search terms. Resolved against actual graph node IDs via `resolve_entities_against_graph()` (exact + case-insensitive + substring match). Each resolved entity drives `neighbors_multi_hop()`.
3. **Vector fallback** — `_vector_fallback()` builds a bag-of-words `SimpleVectorStore` from all Neo4j nodes (one-time per process), augments the query with LLM-suggested search terms, and pulls 1-hop neighbors of each top-K hit.
4. **Generation** — existing `generate_answer()`.

## Files changed

- `src/retrieval/query_understanding.py` — NEW (Pydantic schema + Groq call)
- `src/retrieval/graph_retriever.py` — added `resolve_entities_against_graph`
- `src/graph/store.py` — added `Neo4jGraphStore.list_node_ids()` (cached)
- `src/pipeline/query.py` — 4-stage orchestrator + lazy vector store from Neo4j

## Verification

- Module compile-check clean.
- Helper logic exercised via mocks (exact, case-insensitive, and substring entity resolution all verified).
- Live Neo4j currently empty in this environment, so end-to-end answer prose was not exercised; orchestration runs cleanly through all 4 stages and returns the deterministic "not found" path when no triples are produced.

## Trade-offs / known limits

- Vector store is bag-of-words (`SimpleVectorStore`) — bounded by token overlap. Future work: real embeddings.
- LLM-understanding stage adds ~500ms–1s only on the slow path.
- `list_node_ids()` caches per-process; ingestions during a running Streamlit session won't be picked up until restart.
