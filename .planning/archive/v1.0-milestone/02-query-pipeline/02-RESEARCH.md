# Phase 2: Query Pipeline - Research

**Researched:** 2026-04-15
**Domain:** Neo4j Cypher traversal, LLM entity detection, instructor + Pydantic structured output
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Use LLM-based entity extraction (Groq/OpenAI via existing provider factory) to map questions to graph nodes
- **D-02:** LLM returns direct node_ids — prompt includes the list of known node_ids loaded from Neo4j at startup
- **D-03:** No keyword fallback — LLM handles all entity resolution
- **D-04:** Use specific Cypher pattern queries per relationship type (COMPATIBLE_WITH, HAS_SPEC, SUPPORTS_WIRING, REPLACES) — not generic BFS or LLM-generated Cypher
- **D-05:** Default traversal depth is 2 (matches existing config default)
- **D-06:** LLM produces structured prose followed by a "Graph Evidence" section listing the triples used
- **D-07:** When no relevant graph nodes are found, return an honest "not found" message suggesting what the user can ask about
- **D-08:** Use instructor + Pydantic for structured answer output (consistent with Phase 1 extraction pattern)
- **D-09:** Demo queries stored in `data/eval/queries.json`
- **D-10:** Standard 3-query set: 1) "What accessories are compatible with the T9?" 2) "What wiring configs does the T9 support?" 3) "What are the T9 specifications?"

### Claude's Discretion

- Exact Cypher query patterns per relationship type
- Answer prompt template wording
- Pydantic model structure for query response

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QUERY-01 | User can ask natural language questions about product compatibility, replacements, and specs | Covered by LLM entity detection + Cypher traversal rewrite of `query.py` |
| QUERY-02 | System detects relevant entities from the question and maps them to graph nodes | Covered by LLM entity resolver using node_id list from Neo4j |
| QUERY-03 | System performs multi-hop Cypher traversal (depth 2+) to gather graph context | `Neo4jGraphStore.neighbors_multi_hop()` already supports depth parameter; plus per-relation Cypher queries |
| QUERY-04 | System generates structured answers via Groq LLM using graph context | `generate.py` rewritten using `build_instructor_client()` + Pydantic answer model |
| QUERY-05 | At least 3 canned demo queries produce verified correct answers | `data/eval/queries.json` updated to D-10 query set; smoke test via `evaluate.py` rewrite |
| QUERY-06 | Groq model name is a single configurable key in settings.yaml | Already satisfied in `config/settings.yaml` `llm.model`; verify no hardcoded model strings remain in rewritten code |
</phase_requirements>

---

## Summary

Phase 2 rewrites three existing stub/skeleton files — `src/pipeline/query.py`, `src/retrieval/graph_retriever.py`, and `src/llm/generate.py` — to use real Neo4j-backed retrieval and Groq LLM answer generation. Phase 1 delivered the full infrastructure (`Neo4jGraphStore`, `build_instructor_client()`, `provider.py`, `schema.py`) that Phase 2 consumes. No new libraries are needed.

The key design choice (D-02) is loading all node_ids from Neo4j at startup and injecting them into the entity-resolution prompt. This is viable because the T9 thermostat graph will have O(10s–100s) of nodes — small enough for a prompt list. The approach makes entity resolution deterministic and avoids embedding-based semantic search.

The four per-relation Cypher patterns (D-04) give the planner four discrete query functions, each matching a single relationship type. `neighbors_multi_hop()` is already implemented in `Neo4jGraphStore` and handles depth 2+ BFS — it should be used as the primary traversal with per-relation queries layered on top for precision.

**Primary recommendation:** Rewrite the three files in sequence: entity resolver first, Cypher retriever second, answer generator third; wire them together in `query.py` CLI last.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Entity resolution (NL → node_id) | API/Backend (`graph_retriever.py`) | LLM (Groq) | Backend calls LLM to map question text to known node IDs; browser has no role |
| Graph traversal | Database (Neo4j) | API/Backend | Cypher runs in Neo4j; Python driver marshals results |
| Answer generation | API/Backend (`generate.py`) | LLM (Groq) | Backend formats prompt, calls LLM, validates structured output with instructor |
| CLI interface | Pipeline (`query.py`) | — | Argparse entry point; orchestrates the three layers above |
| Evaluation / demo queries | Pipeline (`evaluate.py`) | — | Reads `queries.json`, calls query pipeline, writes `results.json` |

---

## Standard Stack

### Core (all already in requirements.txt / existing codebase)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `neo4j` (Python driver) | 5.28.1 | Execute Cypher queries; `_driver.session()` | Already pinned; `Neo4jGraphStore` uses it |
| `groq` SDK | 0.9.x | LLM completions via Groq API | Project constraint; `provider.py` already wraps it |
| `instructor` | 1.4.x | Structured output (JSON mode) wrapping Groq | Already used in `entity_extractor.py` (Phase 1 pattern) |
| `pydantic` v2 | 2.7.x | Pydantic models for entity resolver + answer | Already used in `entity_extractor.py` |
| `pyyaml` | 6.0.2 | Load `settings.yaml` | Already used via `src/common/config.py` |
| `python-dotenv` | 1.0.1 | Load API keys from `.env` | Already used in `ingest.py` |

### No New Installs Required

All dependencies are already present. Phase 2 is a rewrite of logic, not a dependency expansion.

---

## Architecture Patterns

### System Architecture Diagram

```
User question (CLI --question)
        │
        ▼
[query.py: load_settings(), load_dotenv()]
        │
        ├─── load node_id list from Neo4j (startup)
        │
        ▼
[graph_retriever.py: EntityResolver]
  LLM call (Groq via build_instructor_client())
  Prompt: question + known node_id list
  Returns: EntityResolution(node_ids=[...])
        │
        ▼ matched node_ids
[graph_retriever.py: CypherRetriever]
  Per-relation Cypher queries (COMPATIBLE_WITH, HAS_SPEC,
  SUPPORTS_WIRING, REPLACES) via Neo4jGraphStore._driver.session()
  + neighbors_multi_hop(depth=2) for BFS context
        │
        ▼ list of (src, relation, tgt) triples
[generate.py: AnswerGenerator]
  LLM call (Groq via build_instructor_client())
  Prompt: question + triples formatted as evidence
  Returns: QueryAnswer(prose=..., evidence=[...])
        │
        ▼
stdout: prose answer + "Graph Evidence:" section
```

### Recommended Project Structure

No structural changes needed. Existing layout accommodates all rewrites:

```
src/
├── retrieval/
│   └── graph_retriever.py   # REWRITE: EntityResolver + CypherRetriever
├── llm/
│   └── generate.py          # REWRITE: AnswerGenerator using instructor
└── pipeline/
    ├── query.py             # REWRITE: wire all three, Neo4jGraphStore
    └── evaluate.py          # UPDATE: remove in-memory imports, use new query.py helpers
```

### Pattern 1: LLM Entity Resolver with Known Node_ID Injection (D-01, D-02, D-03)

**What:** Load all node_ids from Neo4j at startup, inject as a list into the LLM prompt. LLM returns a Pydantic model containing `node_ids: List[str]` drawn only from that list.

**When to use:** Query time, once per question.

```python
# Source: established in src/ingest/entity_extractor.py — same pattern
from pydantic import BaseModel, Field
from typing import List
import instructor

class EntityResolution(BaseModel):
    node_ids: List[str] = Field(
        description="Node IDs from the provided list that are relevant to the question. "
                    "Return empty list if no node matches."
    )

ENTITY_RESOLUTION_SYSTEM = """You are a graph entity resolver for an HVAC product knowledge graph.
Given a user question and a list of known node IDs, return the node IDs that are relevant to answering the question.
Only return node IDs from the provided list — do not invent new ones."""

def resolve_entities(client: instructor.Instructor, model: str, question: str, known_ids: List[str]) -> List[str]:
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

### Pattern 2: Per-Relation Cypher Queries (D-04)

**What:** Four targeted Cypher MATCH patterns, one per allowed relation type. Each returns `(src_node_id, relation, tgt_node_id)` triples. These run in addition to BFS via `neighbors_multi_hop()`.

**When to use:** After entity resolution returns node_ids.

```python
# Source: Neo4jGraphStore._driver.session() pattern from src/graph/store.py
RELATION_QUERIES = {
    "COMPATIBLE_WITH": (
        "MATCH (a {node_id: $node_id})-[r:COMPATIBLE_WITH]-(b) "
        "RETURN a.node_id AS src, 'COMPATIBLE_WITH' AS rel, b.node_id AS tgt"
    ),
    "REPLACES": (
        "MATCH (a {node_id: $node_id})-[r:REPLACES]-(b) "
        "RETURN a.node_id AS src, 'REPLACES' AS rel, b.node_id AS tgt"
    ),
    "SUPPORTS_WIRING": (
        "MATCH (a {node_id: $node_id})-[r:SUPPORTS_WIRING]-(b) "
        "RETURN a.node_id AS src, 'SUPPORTS_WIRING' AS rel, b.node_id AS tgt"
    ),
    "HAS_SPEC": (
        "MATCH (a {node_id: $node_id})-[r:HAS_SPEC]-(b) "
        "RETURN a.node_id AS src, 'HAS_SPEC' AS rel, b.node_id AS tgt"
    ),
}
```

Note: using undirected `-(r:TYPE)-` (not `->`) so traversal works in both directions (e.g., finding what replaces OR what is replaced by a given product).

### Pattern 3: Structured Answer Generation (D-06, D-07, D-08)

**What:** Pydantic model for the LLM answer. Instructor enforces the schema.

```python
# Source: same instructor + Pydantic pattern as entity_extractor.py
from pydantic import BaseModel, Field
from typing import List

class EvidenceTriple(BaseModel):
    source: str
    relation: str
    target: str

class QueryAnswer(BaseModel):
    prose: str = Field(description="Structured prose answer to the user's question")
    evidence: List[EvidenceTriple] = Field(
        description="Graph triples used to construct the answer"
    )
    not_found: bool = Field(
        default=False,
        description="True if no relevant graph data was found for this question"
    )
    suggestion: str = Field(
        default="",
        description="If not_found=True, suggest what the user could ask instead"
    )
```

### Pattern 4: Load All Node IDs from Neo4j at Startup

**What:** Simple Cypher query to fetch all node_ids for the entity resolver prompt.

```python
# Source: Neo4jGraphStore session pattern from src/graph/store.py
def load_all_node_ids(store: Neo4jGraphStore) -> List[str]:
    with store._driver.session() as session:
        result = session.run("MATCH (n) RETURN n.node_id AS node_id ORDER BY n.node_id")
        return [r["node_id"] for r in result if r["node_id"]]
```

### Anti-Patterns to Avoid

- **Importing `GraphStore` (networkx) in query.py:** The existing `query.py` imports the old in-memory `GraphStore` — replace all references with `Neo4jGraphStore`. The networkx `GraphStore` is kept only for unit tests.
- **Hardcoding model name:** The LLM model name MUST come from `settings.yaml` `llm.model` (QUERY-06). Never hardcode `"llama-3.1-8b-instant"` or any other model string in `generate.py` or `graph_retriever.py`.
- **Directional Cypher assumptions:** Using `-->` instead of `-` for relationship direction will miss edges depending on how Phase 1 stored them. Use undirected `-[r:TYPE]-` or test both directions.
- **Trusting node_ids injected by LLM without validation:** After the entity resolver returns node_ids, verify each exists in Neo4j via `store.has_node()` before running traversal. Instructor retries help, but a final filter is cheap and prevents Cypher errors.
- **Building node_id list from graph_items.json (old file):** `query.py` currently loads from `data/processed/graph_items.json` — that file is from the networkx era. Neo4j is the source of truth; load node_ids live from Neo4j.
- **evaluate.py importing from old query.py helpers:** `evaluate.py` imports `build_graph`, `load_graph_items`, `load_sample_docs` — all networkx-era functions. Rewrite `evaluate.py` to use the new `Neo4jGraphStore`-based `query.py`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured LLM output | Custom JSON parsing / regex over LLM response | `instructor` + Pydantic | instructor retries on schema violations; already used in Phase 1 |
| Neo4j connection management | Custom connection pool | `neo4j` driver's built-in session management via `Neo4jGraphStore` | Already implemented; handles retries and session lifecycle |
| Entity matching | Regex / string distance | LLM via `build_instructor_client()` (D-03) | Regex misses synonyms and natural phrasing; LLM handles "T9", "RCHT9610WF", "the thermostat" equally |
| Multi-hop traversal | Manual Python BFS over Cypher results | `Neo4jGraphStore.neighbors_multi_hop()` | Already implemented correctly with parameterized depth |

**Key insight:** All infrastructure exists. Phase 2 is assembling pieces, not building new ones.

---

## Common Pitfalls

### Pitfall 1: Node ID List Too Large for Prompt Context

**What goes wrong:** If the graph grows beyond ~500 nodes, injecting all node_ids into every LLM prompt becomes expensive (token cost) or hits context limits.

**Why it happens:** D-02 is designed for the T9 prototype with O(10s–100s) nodes — fine for demo scale.

**How to avoid:** Cap the injected list at 200 node_ids max (sufficient for this prototype). Add a comment in code noting the scaling limitation for future phases.

**Warning signs:** Groq API returning 400 errors about context length; response latency above 5 seconds.

---

### Pitfall 2: Entity Resolver Returns Node IDs Not in Neo4j

**What goes wrong:** LLM occasionally returns a plausible-looking node_id that doesn't exist (hallucination despite the injected list; instructor retries don't guarantee 100% compliance on all models).

**How to avoid:** After `resolve_entities()` returns, filter with `store.has_node(nid)` before running Cypher queries. Log any filtered-out IDs for debugging.

---

### Pitfall 3: evaluate.py Imports from Old query.py Functions

**What goes wrong:** `evaluate.py` imports `build_graph`, `load_graph_items`, `load_sample_docs` from the current `query.py`. After rewriting `query.py`, those functions will no longer exist — `evaluate.py` will break with `ImportError`.

**How to avoid:** Rewrite `evaluate.py` as part of this phase. It should use `Neo4jGraphStore` directly.

---

### Pitfall 4: Cypher Direction Mismatch

**What goes wrong:** `MATCH (a)-[:REPLACES]->(b)` only matches edges stored as `a→b`. If Phase 1 stored "T9 REPLACES TH6320WF" as `T9→TH6320WF`, then querying from `TH6320WF`'s perspective misses the edge.

**How to avoid:** Use undirected pattern `MATCH (a {node_id: $nid})-[:REPLACES]-(b)` in per-relation queries. Or run both directions explicitly. Test with the demo queries after Phase 1 ingest completes.

---

### Pitfall 5: settings.yaml `llm.provider` is Currently "openai"

**What goes wrong:** `settings.yaml` currently has `provider: openai` and `model: gpt-4.1` (set by the quick task that added OpenAI support). If the developer doesn't have `OPENAI_API_KEY` set, the query pipeline will fail with a `ValueError`.

**How to avoid:** Document the dependency clearly in query.py startup. The provider is configurable — developers should set it to `groq` with a Groq model if they don't have an OpenAI key. QUERY-06 requires only that the model name be configurable — it is.

---

## Code Examples

### Loading Neo4j connection in query.py

```python
# Source: pattern from src/pipeline/ingest.py + src/graph/store.py
from dotenv import load_dotenv
load_dotenv()

from src.common.config import load_settings
from src.graph.store import Neo4jGraphStore

def build_neo4j_store() -> Neo4jGraphStore:
    settings = load_settings()
    g = settings["graph"]
    return Neo4jGraphStore(
        uri=g["neo4j_uri"],
        user=g["neo4j_user"],
        password=g["neo4j_password"],
    )
```

### Formatting triples for the answer prompt

```python
# Source: existing pattern in generate.py stub
def format_triples(triples: list[tuple[str, str, str]]) -> str:
    return "\n".join(f"- {src} --[{rel}]--> {tgt}" for src, rel, tgt in triples)
```

### Answer system prompt skeleton (D-06, D-07)

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

---

## Rewrite Scope Summary

| File | Action | What Changes |
|------|--------|-------------|
| `src/retrieval/graph_retriever.py` | Full rewrite | Remove regex `extract_candidate_entities()`; add `EntityResolver` (LLM) + `CypherRetriever` (per-relation Cypher + BFS) |
| `src/llm/generate.py` | Full rewrite | Replace stub with real LLM call using `build_instructor_client()` + `QueryAnswer` Pydantic model |
| `src/pipeline/query.py` | Full rewrite | Replace networkx `GraphStore` + `load_graph_items()` with `Neo4jGraphStore`; wire new retriever + generator |
| `src/pipeline/evaluate.py` | Update | Remove networkx-era imports; use new `query.py` interface |
| `data/eval/queries.json` | Update | Replace 3 existing queries with D-10 query set |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | All code | Yes | 3.13.1 | — |
| Neo4j (bolt://localhost:7687) | Graph traversal | Unknown at research time | — | Must be running (see STATE.md resume instructions) |
| GROQ_API_KEY or OPENAI_API_KEY | LLM calls | Unknown at research time | — | Set in .env before running |
| `neo4j` Python driver | Graph store | Yes (5.28.1 in requirements.txt) | 5.28.1 | — |
| `instructor` | Structured output | Yes (in requirements.txt) | 1.4.x | — |
| `pydantic` v2 | Schema validation | Yes (in requirements.txt) | 2.7.x | — |

**Missing dependencies with no fallback:**
- Neo4j must be running before `query.py` executes. See STATE.md resume instructions: `docker run -d --name neo4j-graphrag -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5`
- At least one LLM API key (`GROQ_API_KEY` or `OPENAI_API_KEY`) must be set in `.env`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Phase 1 ingest has completed and T9 graph nodes exist in Neo4j | All sections | Query pipeline returns empty results; demo queries fail. Must run ingest before testing Phase 2. |
| A2 | 100–200 node_ids from T9 PDF is within Groq/OpenAI context limits | Pattern 1 (Entity Resolver) | Token budget exceeded; need to cap or chunk the node_id list |
| A3 | Per-relation Cypher undirected patterns will find edges regardless of storage direction | Pattern 2 (Cypher) | Demo queries miss relationships; need to verify after ingest |

---

## Open Questions

1. **What node_ids does Phase 1 ingest actually produce for the T9 PDF?**
   - What we know: Phase 1 is written but the human-verify checkpoint (live ingest) is pending
   - What's unclear: Exact node_ids — the demo queries in D-10 reference "T9" but the actual node_id may be "RCHT9610WF" or similar
   - Recommendation: After Phase 1 ingest runs, inspect Neo4j Browser to confirm node_ids before writing the D-10 queries.json entries

2. **Should `evaluate.py` call the full query pipeline (including LLM answer generation) or just retrieval?**
   - What we know: Current `evaluate.py` only measures retrieval hit count and latency
   - What's unclear: D-09/D-10 say demo queries produce "verified correct answers" — this implies the LLM call too
   - Recommendation: Rewrite `evaluate.py` to call the full pipeline (retrieval + generation) and record the `prose` answer for each demo query so they can be manually verified

---

## Sources

### Primary (HIGH confidence)
- `src/graph/store.py` (codebase) — `Neo4jGraphStore` API: `neighbors_multi_hop()`, `has_node()`, `node_payload()`, `_driver.session()`
- `src/llm/provider.py` (codebase) — `build_instructor_client()`, `get_llm_config()` signatures
- `src/ingest/entity_extractor.py` (codebase) — instructor + Pydantic structured output pattern to replicate
- `config/settings.yaml` (codebase) — confirmed `llm.model`, `llm.provider`, `graph.neo4j_uri` keys
- `src/graph/schema.py` (codebase) — `VALID_RELATIONS`, `VALID_KINDS`, `ALLOWED_RELATIONS` Literal types

### Secondary (MEDIUM confidence)
- `.planning/phases/02-query-pipeline/02-CONTEXT.md` — locked decisions from discuss-phase
- `.planning/REQUIREMENTS.md` — QUERY-01 through QUERY-06 definitions

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in requirements.txt; codebase verified
- Architecture: HIGH — all integration points confirmed by reading actual source files
- Pitfalls: HIGH — derived from direct inspection of existing code and locked decisions

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (stable stack; only risk is LLM API deprecations)
