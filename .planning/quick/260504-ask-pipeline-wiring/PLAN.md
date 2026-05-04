---
slug: ask-pipeline-wiring
date: 2026-05-04
status: in-progress
---

# Wire Full Pipeline to Ask Tab

## Goal

When an entirely new and unseen query comes through the "Ask" tab (no SKU mention, no replacement keyword), run it through the full pipeline:

1. Graph retrieval (existing regex/keyword fast path)
2. **LLM query understanding** (NEW) — extract entities + intent when fast path is empty
3. **Vector fallback** (NEW wiring) — when graph still yields nothing
4. LLM answer generation (existing)

## Non-Goals

- Replacing `SimpleVectorStore` with real embeddings.
- Re-architecting `hybrid_retriever.py`.
- Changing the Multi-Doc Queries tab (it already calls `run_query_structured` and inherits the upgrade).
- Adding new tests (CLI smoke test is the verification path for this quick task).

## Design

### Augment, don't replace

Keep the existing regex+keyword path as the fast path. Curated demo queries (`What replaces TH1110D?`) skip LLM understanding entirely. Only queries that miss both regex *and* the replacement-keyword fallback go to the slow path.

### New module: `src/retrieval/query_understanding.py`

```python
class QueryUnderstanding(BaseModel):
    entities: list[str]      # candidate node IDs the LLM extracted
    intent: Literal["replacement", "compatibility", "spec", "general"]
    search_terms: list[str]  # keywords for vector fallback

def understand_query(client, model, question) -> QueryUnderstanding: ...
```

- Single Groq call via `instructor`.
- Prompt seeded with the actual relation types in the graph (`REPLACED_BY`, `COMPATIBLE_WITH`, `REQUIRES`, etc.).
- Returns an empty stub on LLM failure so the pipeline degrades to vector fallback.

### Modify `src/retrieval/graph_retriever.py`

Add `resolve_entities_against_graph(store, candidates) -> list[str]`:
- Case-insensitive substring match against node IDs.
- Uses a new `Neo4jGraphStore.list_node_ids()` helper (one Cypher call, cached on the store instance for the life of the process).

### Modify `src/graph/store.py`

Add `Neo4jGraphStore.list_node_ids() -> list[str]` — `MATCH (n) WHERE n.node_id IS NOT NULL RETURN n.node_id`. Cache on first call.

### Modify `src/pipeline/query.py`

`run_query_structured` becomes a 3-stage orchestrator:

```python
triples = graph_retrieve(store, question, depth)
if not triples and client is not None:
    parsed = understand_query(client, model, question)
    resolved = resolve_entities_against_graph(store, parsed.entities)
    for entity in resolved:
        triples.extend(store.neighbors_multi_hop(entity, depth))
if not triples:
    triples = _vector_fallback(question, store, depth)
return generate_answer(client, model, question, triples)
```

`_vector_fallback`:
- Lazy-loads `SimpleVectorStore` from `data/processed/graph_items.json` once per process (module-level cache).
- For each top-K hit, pulls 1-hop neighbors from the graph to assemble triples.

## Acceptance

- `python -m src.pipeline.query --question "Which thermostat works with two-stage heat pumps?" --depth 2` returns triples + a non-empty prose answer (instead of "not found").
- `python -m src.pipeline.query --question "What replaces TH1110D?"` still returns the same answer it does today, with no extra LLM call (verified by absence of new latency).
- Streamlit Ask tab calls the same `run_query_structured` and exhibits the same upgrade with no UI changes.
- Existing tests (if any) still pass.

## Files

- `src/retrieval/query_understanding.py` — NEW
- `src/retrieval/graph_retriever.py` — add `resolve_entities_against_graph`
- `src/graph/store.py` — add `list_node_ids` to `Neo4jGraphStore`
- `src/pipeline/query.py` — orchestrate 3-stage pipeline + vector fallback
