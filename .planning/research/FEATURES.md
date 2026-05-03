# Feature Landscape: GraphRAG for Product/Catalog Data

**Domain:** Knowledge graph + RAG for product compatibility and catalog data
**Project:** Honeywell T9 thermostat GraphRAG prototype
**Researched:** 2026-04-15
**Confidence:** MEDIUM (domain reasoning from codebase analysis; web search unavailable)

---

## Table Stakes

Features that must be present for the demo to be convincing. Missing any of these means the demo fails to prove the core value proposition.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| PDF entity extraction into typed graph nodes | Core thesis — the graph must come from the actual document, not hand-coded data | High | Nodes: Product, WiringConfig, SystemType, Spec, Accessory. Must handle PDF noise. |
| Typed relationship edges in Neo4j | Relationship-awareness is the differentiator vs flat RAG; demo dies without real edge types | Medium | REPLACES, COMPATIBLE_WITH, REQUIRES, HAS_SPEC, WORKS_WITH minimum set |
| Multi-hop graph traversal (depth 2+) | Single-hop retrieval misses indirect compatibility chains ("what wires work with C-wire on a heat pump?") | Medium | Already stubbed in `GraphStore.neighbors_multi_hop()`; needs Neo4j Cypher translation |
| Natural language question → graph retrieval → LLM answer | End-to-end pipeline is the demo; any broken link kills credibility | Medium | Groq API call replaces `generate_answer()` stub |
| At least 3 canned example queries that return correct answers | Demo needs reliable showcase moments | Low | Queries: replacement lookup, compatibility check, wiring spec question |
| Web UI with text input and answer display | Without a UI the demo is a CLI script; non-technical stakeholders can't engage | Low | Streamlit is fastest; single page, no auth |
| Graph visualization of retrieved subgraph | Makes the "graph" in GraphRAG visible; absence makes the demo feel like regular RAG | Medium | Neo4j Browser is acceptable; embedded iframe or screenshot in UI also works |
| Configurable Groq model name | PROJECT.md explicitly requires this; single-string config, not hardcoded | Low | One env var or one settings.yaml key |

---

## Differentiators

Features that elevate the demo from "it works" to "that's impressive." Optional but high-leverage for stakeholder demos.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Show graph context alongside answer | Transparency — user sees *why* the answer was given (which edges were traversed) | Low | Render the triplets used as "evidence" panel in UI next to the answer |
| Relationship-type filter in query | Lets user ask "show only REPLACES paths" — demonstrates graph's structural advantage over vector search | Medium | Dropdown in UI maps to WHERE r.type = '...' in Cypher |
| Node property display on click | Clicking a node in the graph visualization shows its spec properties | Medium | Requires Neo4j Browser embed or custom D3/vis.js; skip if time-constrained |
| Graceful "not found" with nearest neighbor suggestion | When entity not in graph, suggest closest match; shows robustness | Medium | Fuzzy match on node labels before giving up |
| Comparison query support | "How does T9 differ from T6?" — requires fetching two subgraphs and prompting LLM to compare | Medium | Requires NL parsing to detect comparison intent |
| Wiring diagram context in answer | HVAC installers care about wire labels (R, C, W, Y, G); structured answer format per wire terminal | High | Needs wire-terminal entity type and careful PDF extraction |

---

## Anti-Features

Things to deliberately NOT build for this prototype. Each has a cost-vs-value rationale.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Embedding-based vector search | PROJECT.md explicitly excludes it; adds infra complexity, masks graph contribution | Use graph traversal as the only retrieval mechanism |
| Multi-document ingestion | Scope creep; single PDF already proves the architecture | Hard-code input path to `data/raw/t9-thermostat.pdf` |
| User authentication / session management | Prototype, not product; auth adds 0 demo value | No login, single shared session |
| Automatic PDF re-ingestion on change | Over-engineering for a single static file | Manual ingest CLI command only |
| LLM fine-tuning or custom embeddings | Weeks of effort, zero prototype value | Use Groq as-is |
| Production error recovery / retry logic | Makes code harder to read for collaborators and evaluators | Let exceptions bubble; log clearly |
| Pagination of graph results | Single-product queries return small subgraphs; not needed at prototype scale | Return all hits up to a configurable depth limit |
| REST API / FastAPI layer | Streamlit/Gradio calls Python functions directly; an API layer adds indirection with no demo benefit | Streamlit calls pipeline functions in-process |
| Docker / containerization | Adds setup complexity for a local prototype | venv + README instructions |
| Test suite / CI | Time-consuming; prototype changes rapidly | Manual spot-check with canned queries |

---

## Feature Dependencies

```
PDF extraction (PyMuPDF/pdfplumber)
    → Entity/Relationship identification (LLM-assisted or rule-based)
        → Neo4j node/edge creation (neo4j Python driver)
            → Multi-hop Cypher traversal
                → Graph context passed to Groq
                    → Answer displayed in Streamlit

Streamlit UI
    → Text input → query pipeline in-process
    → Answer panel (text)
    → Evidence panel (triplets shown) [differentiator, depends on answer]
    → Graph visualization [depends on Neo4j data being populated]
```

Key dependency: graph visualization requires the Neo4j backend to be populated first; do not build the UI before ingest works end-to-end.

---

## MVP Recommendation

Prioritize in this order:

1. **PDF extraction → Neo4j nodes/edges** — nothing else works without data in the graph
2. **Cypher-based multi-hop retrieval** — replace networkx traversal with Neo4j queries
3. **Groq LLM integration** — replace `generate_answer()` stub
4. **3 canned demo queries returning correct answers** — validate the pipeline before building UI
5. **Streamlit UI with answer + evidence panel** — wrap the working pipeline
6. **Graph visualization** — add Neo4j Browser link or embedded view last

Defer:
- Relationship-type filter UI — adds complexity, medium value; do only if Phase 1 is ahead of schedule
- Comparison queries — interesting but requires extra NL parsing work
- Wiring diagram structured output — highest value for HVAC domain but highest extraction complexity; prototype with flat text first

---

## Sources

- Codebase analysis: `/Users/jsk/Desktop/anthropic/Graph-RAG/src/` skeleton
- Project requirements: `/Users/jsk/Desktop/anthropic/Graph-RAG/.planning/PROJECT.md`
- Domain reasoning from GraphRAG literature and product catalog RAG patterns (training knowledge, MEDIUM confidence)
- Web search unavailable during this research session; claims about "what GraphRAG demos show" are based on training data only — validate against Microsoft GraphRAG paper and Neo4j Graph Academy examples if needed
