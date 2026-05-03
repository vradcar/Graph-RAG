# Phase 2: Query Pipeline - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Accept natural language questions about T9 thermostat compatibility, wiring, specs, and replacements. Detect entities via LLM, traverse the Neo4j graph with Cypher pattern queries, and generate structured prose answers grounded in graph evidence.

</domain>

<decisions>
## Implementation Decisions

### Entity Detection
- **D-01:** Use LLM-based entity extraction (Groq/OpenAI via existing provider factory) to map questions to graph nodes
- **D-02:** LLM returns direct node_ids — prompt includes the list of known node_ids loaded from Neo4j at startup
- **D-03:** No keyword fallback — LLM handles all entity resolution

### Graph Traversal Strategy
- **D-04:** Use specific Cypher pattern queries per relationship type (COMPATIBLE_WITH, HAS_SPEC, SUPPORTS_WIRING, REPLACES) — not generic BFS or LLM-generated Cypher
- **D-05:** Default traversal depth is 2 (matches existing config default)

### Answer Generation
- **D-06:** LLM produces structured prose followed by a "Graph Evidence" section listing the triples used
- **D-07:** When no relevant graph nodes are found, return an honest "not found" message suggesting what the user can ask about
- **D-08:** Use instructor + Pydantic for structured answer output (consistent with Phase 1 extraction pattern)

### Demo Queries
- **D-09:** Demo queries stored in `data/eval/queries.json` (path already configured in settings.yaml)
- **D-10:** Standard 3-query set: 1) "What accessories are compatible with the T9?" 2) "What wiring configs does the T9 support?" 3) "What are the T9 specifications?" — covers COMPATIBLE_WITH, SUPPORTS_WIRING, HAS_SPEC

### Claude's Discretion
- Exact Cypher query patterns per relationship type
- Answer prompt template wording
- Pydantic model structure for query response

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Code (rewrite targets)
- `src/pipeline/query.py` — Current skeleton using in-memory GraphStore (rewrite for Neo4j)
- `src/retrieval/graph_retriever.py` — Current regex entity matcher (replace with LLM extraction)
- `src/llm/generate.py` — Current stub (replace with real LLM call)

### Reusable Code (use as-is)
- `src/llm/provider.py` — `build_instructor_client()` and `get_llm_config()` for Groq/OpenAI
- `src/graph/store.py` — `Neo4jGraphStore` with `neighbors_multi_hop()` and Cypher execution
- `config/settings.yaml` — `llm.provider`, `llm.model`, `graph.neo4j_uri` settings

### Configuration
- `config/settings.yaml` — `evaluation.queries_file` points to `data/eval/queries.json`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/llm/provider.py`: `build_instructor_client()` — same factory used in Phase 1 extraction, reuse for query-time LLM calls
- `src/graph/store.py`: `Neo4jGraphStore` — has `_driver.session()` for raw Cypher execution and `neighbors_multi_hop()` for BFS
- `src/common/config.py`: `load_settings()` — loads settings.yaml

### Established Patterns
- instructor + Pydantic for structured LLM output (used in entity_extractor.py)
- `load_dotenv()` first, then imports (established in ingest.py)
- Settings-driven model name (llm.model in settings.yaml)

### Integration Points
- `query.py` CLI will be rewritten to use Neo4jGraphStore instead of in-memory GraphStore
- `graph_retriever.py` will be rewritten to use LLM entity extraction instead of regex
- `generate.py` will be rewritten to call Groq/OpenAI via provider factory

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches within the decisions above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-query-pipeline*
*Context gathered: 2026-04-15*
