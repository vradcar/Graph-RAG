# Phase 2: Query Pipeline - Pattern Map

**Mapped:** 2026-04-15
**Files analyzed:** 5
**Analogs found:** 5 / 5

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/retrieval/graph_retriever.py` | service | request-response | `src/ingest/entity_extractor.py` | role-match (same LLM + instructor pattern) |
| `src/llm/generate.py` | service | request-response | `src/ingest/entity_extractor.py` | exact (same instructor + Pydantic output model pattern) |
| `src/pipeline/query.py` | pipeline/CLI | request-response | `src/pipeline/ingest.py` | exact (same CLI structure + Neo4jGraphStore wiring) |
| `src/pipeline/evaluate.py` | pipeline/CLI | batch | `src/pipeline/ingest.py` | role-match (same CLI + settings + dotenv structure) |
| `data/eval/queries.json` | config/data | — | existing `data/eval/queries.json` | update (replace 3 entries) |

---

## Pattern Assignments

### `src/retrieval/graph_retriever.py` (service, request-response)

**Analog:** `src/ingest/entity_extractor.py`

**What changes:** Remove `extract_candidate_entities()` regex. Add two classes:
- `EntityResolver` — LLM call that maps a question to known node_ids
- `CypherRetriever` — four per-relation Cypher MATCH queries + `neighbors_multi_hop()` BFS

**Imports pattern** (copy from `src/ingest/entity_extractor.py` lines 1-16):
```python
from typing import List, Tuple
import instructor
from pydantic import BaseModel, Field
from src.llm.provider import build_instructor_client, get_llm_config
from src.graph.store import Neo4jGraphStore
```

**Pydantic model pattern** (copy structure from `src/ingest/entity_extractor.py` lines 22-55):
```python
class EntityResolution(BaseModel):
    node_ids: List[str] = Field(
        description=(
            "Node IDs from the provided list that are relevant to the question. "
            "Return empty list if no node matches."
        )
    )
```

**LLM call pattern** (copy from `src/ingest/entity_extractor.py` lines 144-152):
```python
result = client.chat.completions.create(
    model=model,
    response_model=EntityResolution,
    messages=[
        {"role": "system", "content": ENTITY_RESOLUTION_SYSTEM},
        {"role": "user", "content": f"Known node IDs:\n{chr(10).join(known_ids)}\n\nQuestion: {question}"},
    ],
    max_retries=2,
)
return result.node_ids
```

**Neo4j session pattern** (copy from `src/graph/store.py` lines 77-91):
```python
# Per-relation Cypher queries — use undirected -[r:TYPE]- to match both storage directions
RELATION_QUERIES = {
    "COMPATIBLE_WITH": "MATCH (a {node_id: $node_id})-[r:COMPATIBLE_WITH]-(b) RETURN a.node_id AS src, 'COMPATIBLE_WITH' AS rel, b.node_id AS tgt",
    "REPLACES":        "MATCH (a {node_id: $node_id})-[r:REPLACES]-(b)        RETURN a.node_id AS src, 'REPLACES' AS rel, b.node_id AS tgt",
    "SUPPORTS_WIRING": "MATCH (a {node_id: $node_id})-[r:SUPPORTS_WIRING]-(b) RETURN a.node_id AS src, 'SUPPORTS_WIRING' AS rel, b.node_id AS tgt",
    "HAS_SPEC":        "MATCH (a {node_id: $node_id})-[r:HAS_SPEC]-(b)        RETURN a.node_id AS src, 'HAS_SPEC' AS rel, b.node_id AS tgt",
}

# Session usage pattern (from store.py lines 80-91):
with store._driver.session() as session:
    result = session.run(query, node_id=nid)
    triples = [(r["src"], r["rel"], r["tgt"]) for r in result]
```

**Node ID validation pattern** (copy from `src/graph/store.py` lines 107-118):
```python
# After resolve_entities() returns, filter with store.has_node() before Cypher traversal
validated_ids = [nid for nid in resolved_ids if store.has_node(nid)]
```

**Load all node IDs at startup** (new helper, session pattern from `src/graph/store.py` lines 33-38):
```python
def load_all_node_ids(store: Neo4jGraphStore) -> List[str]:
    with store._driver.session() as session:
        result = session.run("MATCH (n) RETURN n.node_id AS node_id ORDER BY n.node_id")
        return [r["node_id"] for r in result if r["node_id"]]
```

---

### `src/llm/generate.py` (service, request-response)

**Analog:** `src/ingest/entity_extractor.py`

**What changes:** Replace the stub body entirely. Add `QueryAnswer` Pydantic model and `generate_answer()` that calls Groq/OpenAI via `build_instructor_client()`.

**Imports pattern** (copy from `src/ingest/entity_extractor.py` lines 1-16):
```python
from typing import List
import instructor
from pydantic import BaseModel, Field
from src.llm.provider import build_instructor_client, get_llm_config
```

**Pydantic output model pattern** (copy structure from `src/ingest/entity_extractor.py` lines 52-55):
```python
class EvidenceTriple(BaseModel):
    source: str
    relation: str
    target: str

class QueryAnswer(BaseModel):
    prose: str = Field(description="Structured prose answer to the user's question")
    evidence: List[EvidenceTriple] = Field(description="Graph triples used to construct the answer")
    not_found: bool = Field(default=False, description="True if no relevant graph data was found")
    suggestion: str = Field(default="", description="If not_found=True, suggest a related question")
```

**System prompt pattern** (copy style from `src/ingest/entity_extractor.py` lines 62-102):
```python
ANSWER_SYSTEM_PROMPT = """You are an HVAC product knowledge assistant.
Answer the user's question using ONLY the graph evidence provided.
Return structured output with:
- prose: a clear answer in 2-4 sentences
- evidence: the specific triples that support your answer
- not_found: true if the evidence does not contain relevant information
- suggestion: if not_found, suggest a related question the user could ask
Do not add information not present in the graph evidence."""
```

**LLM call pattern** (copy from `src/ingest/entity_extractor.py` lines 144-152):
```python
return client.chat.completions.create(
    model=model,
    response_model=QueryAnswer,
    messages=[
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {question}\n\nGraph evidence:\n{formatted_triples}"},
    ],
    max_retries=2,
)
```

**Triple formatting helper** (new utility, no analog — trivial):
```python
def format_triples(triples: list[tuple[str, str, str]]) -> str:
    return "\n".join(f"- {src} --[{rel}]--> {tgt}" for src, rel, tgt in triples)
```

---

### `src/pipeline/query.py` (pipeline/CLI, request-response)

**Analog:** `src/pipeline/ingest.py`

**What changes:** Replace all networkx `GraphStore` / `load_graph_items()` / `SimpleVectorStore` references with `Neo4jGraphStore`. Wire `EntityResolver`, `CypherRetriever`, `generate_answer()`. Remove `vector` and `hybrid` modes — this pipeline is graph-only.

**Module docstring + load_dotenv() first pattern** (copy from `src/pipeline/ingest.py` lines 1-22):
```python
"""
Query CLI: natural language question → Neo4j graph traversal → LLM answer.
"""
from dotenv import load_dotenv
load_dotenv()  # MUST be first — loads .env before any os.getenv() calls

from src.common.config import load_settings
from src.graph.store import Neo4jGraphStore
```

**Settings-driven Neo4j connection pattern** (copy from `src/pipeline/ingest.py` lines 38-43):
```python
settings = load_settings()
neo4j_uri = settings["graph"]["neo4j_uri"]
neo4j_user = settings["graph"]["neo4j_user"]
neo4j_password = os.getenv("NEO4J_PASSWORD", settings["graph"]["neo4j_password"])
model = settings["llm"]["model"]
provider = settings["llm"].get("provider", "groq")
```

**Context manager pattern for Neo4jGraphStore** (copy from `src/pipeline/ingest.py` line 100):
```python
with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as store:
    ...
```

**Argparse CLI pattern** (copy from `src/pipeline/ingest.py` lines 214-238):
```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Run query against Neo4j graph")
    parser.add_argument("--question", required=True)
    parser.add_argument("--depth", type=int, default=2)
    args = parser.parse_args()
    ...

if __name__ == "__main__":
    main()
```

**Error handling pattern for missing API key** (copy from `src/pipeline/ingest.py` lines 53-56):
```python
try:
    client = build_instructor_client(provider)
except ValueError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
```

---

### `src/pipeline/evaluate.py` (pipeline/CLI, batch)

**Analog:** `src/pipeline/ingest.py` (CLI structure) + current `src/pipeline/evaluate.py` (loop/JSON write pattern)

**What changes:** Remove imports of `build_graph`, `load_graph_items`, `load_sample_docs`, `SimpleVectorStore`, `hybrid_retrieve`. Rewrite `run_eval()` to use `Neo4jGraphStore` + the new query pipeline helpers. Record full `QueryAnswer.prose` per demo query.

**load_dotenv() first + argparse pattern** (copy from `src/pipeline/ingest.py` lines 22-24):
```python
from dotenv import load_dotenv
load_dotenv()
```

**Batch loop + timing pattern** (keep from current `src/pipeline/evaluate.py` lines 23-51):
```python
results = []
for item in queries:
    question = item["question"]
    depth = item.get("depth", 2)
    start = time.perf_counter()
    # ... run query pipeline ...
    latency = time.perf_counter() - start
    results.append({
        "question": question,
        "depth": depth,
        "answer": answer.prose,
        "evidence": [e.model_dump() for e in answer.evidence],
        "not_found": answer.not_found,
        "latency_sec": latency,
        "expected": item.get("expected"),
    })
```

**JSON output write pattern** (keep from current `src/pipeline/evaluate.py` lines 54-58):
```python
output = Path(output_path)
output.parent.mkdir(parents=True, exist_ok=True)
with output.open("w", encoding="utf-8") as file:
    json.dump(results, file, indent=2)
print(f"Saved evaluation results to {output}")
```

**Settings-driven paths pattern** (copy from `src/pipeline/ingest.py` lines 38-39):
```python
settings = load_settings()
queries_path = settings["evaluation"]["queries_file"]
output_path = settings["evaluation"]["output_file"]
```

---

### `data/eval/queries.json` (config/data)

**Analog:** existing `data/eval/queries.json` (same schema, update entries only)

**Current schema** (lines 1-17):
```json
[
  {
    "question": "...",
    "depth": 2,
    "expected": "..."
  }
]
```

**Replace with D-10 query set:**
```json
[
  {"question": "What accessories are compatible with the T9?", "depth": 2, "expected": "COMPATIBLE_WITH edges from T9 product node"},
  {"question": "What wiring configs does the T9 support?",    "depth": 2, "expected": "SUPPORTS_WIRING edges from T9 product node"},
  {"question": "What are the T9 specifications?",             "depth": 2, "expected": "HAS_SPEC edges from T9 product node"}
]
```

Note: exact node_id for "T9" (likely `RCHT9610WF` or similar) must be confirmed after Phase 1 ingest runs. The `expected` field is for human verification only — `evaluate.py` does not assert against it.

---

## Shared Patterns

### load_dotenv() First
**Source:** `src/pipeline/ingest.py` lines 19-22
**Apply to:** `query.py`, `evaluate.py`
```python
from dotenv import load_dotenv
load_dotenv()  # MUST be first — loads .env before any os.getenv() calls
```

### Settings-Driven Config (no hardcoded values)
**Source:** `src/pipeline/ingest.py` lines 38-51; `src/llm/provider.py` lines 17-31
**Apply to:** `query.py`, `evaluate.py`, `graph_retriever.py`, `generate.py`
```python
settings = load_settings()
model = settings["llm"]["model"]           # NEVER hardcode model name
provider = settings["llm"].get("provider", "groq")
```
QUERY-06 violation check: grep for any string matching `llama|gpt|mixtral|gemma` outside of settings.yaml before shipping.

### build_instructor_client() Factory
**Source:** `src/llm/provider.py` lines 34-72
**Apply to:** `graph_retriever.py` (EntityResolver), `generate.py` (AnswerGenerator)
```python
from src.llm.provider import build_instructor_client, get_llm_config
client = build_instructor_client(provider)   # raises ValueError with clear message if key missing
```

### Neo4jGraphStore Context Manager
**Source:** `src/pipeline/ingest.py` line 100; `src/graph/store.py` lines 120-127
**Apply to:** `query.py`, `evaluate.py`
```python
with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as store:
    store.setup_constraints()  # idempotent — only needed in ingest, not query
    ...
# store.close() called automatically on __exit__
```

### instructor + Pydantic Structured Output
**Source:** `src/ingest/entity_extractor.py` lines 144-152
**Apply to:** `graph_retriever.py` (EntityResolution model), `generate.py` (QueryAnswer model)
```python
result = client.chat.completions.create(
    model=model,
    response_model=SomePydanticModel,
    messages=[...],
    max_retries=2,   # instructor retries on schema violations
)
```

### Neo4j Session Read Pattern
**Source:** `src/graph/store.py` lines 80-91 (`neighbors_multi_hop`), lines 107-118 (`has_node`)
**Apply to:** `graph_retriever.py` (load_all_node_ids, per-relation Cypher queries)
```python
def _tx(tx):
    result = tx.run("MATCH ...", param=value)
    return [r["field"] for r in result]

with self._driver.session() as session:
    return session.execute_read(_tx)
```

---

## No Analog Found

All five files have usable analogs. No files require falling back to RESEARCH.md patterns alone.

---

## Metadata

**Analog search scope:** `src/`, `data/eval/`, `config/`
**Files read:** `src/retrieval/graph_retriever.py`, `src/llm/generate.py`, `src/pipeline/query.py`, `src/pipeline/evaluate.py`, `src/ingest/entity_extractor.py`, `src/pipeline/ingest.py`, `src/llm/provider.py`, `src/graph/store.py`, `data/eval/queries.json`, `config/settings.yaml`
**Pattern extraction date:** 2026-04-15
