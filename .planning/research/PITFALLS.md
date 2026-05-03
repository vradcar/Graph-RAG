# Domain Pitfalls: GraphRAG on Honeywell HVAC Product Data

**Domain:** GraphRAG — PDF entity extraction into Neo4j product knowledge graph
**Researched:** 2026-04-15
**Scope:** T9 thermostat PDF → Neo4j → Groq LLM → Streamlit UI

---

## Critical Pitfalls

Mistakes that cause rewrites or destroy graph quality.

---

### Pitfall 1: Treating PDF Tables as Prose

**What goes wrong:** HVAC installation PDFs encode the most important data (wiring terminal tables, compatibility matrices, system type tables) in multi-column tables and figures. Generic PDF text extraction (`pdfplumber`, `pypdf`, `PyMuPDF` default) reads tables left-to-right across columns, fusing unrelated cell values into nonsense strings. A wiring table with terminals R, C, G, Y1 becomes one blob: "R C G Y1 24VAC Common Fan Cool". Entity extraction then invents phantom relationships.

**Why it happens:** PDF does not have a table object model. Text elements are positioned absolutely. Most extraction libraries reconstruct reading order heuristically and fail on multi-column layouts common in installation guides.

**Consequences:** Wiring configuration nodes contain scrambled data. Compatibility relationships are extracted from fused nonsense. The graph looks populated but answers are wrong. This is invisible until you manually spot-check extracted triples.

**Warning signs:**
- Extracted text contains long runs of codes/numbers without punctuation or sentence structure
- Terminal names (R, C, G, Y1, Y2, O/B, W, W2) appear concatenated rather than as individual items
- Spec values (voltage, wire count) are off by an order of magnitude or mixed with part numbers

**Prevention:**
- Use `pdfplumber` with explicit table extraction: `page.extract_tables()` not `page.extract_text()`
- Validate raw extraction output against the PDF visually before any LLM pass
- Add a "raw extraction audit" step before ingestion — dump extracted text per page to a file and manually verify at least the wiring tables and compatibility section

**Phase:** PDF ingestion / extraction — address in the very first milestone before writing any graph logic.

---

### Pitfall 2: Schema-Less Node Explosion

**What goes wrong:** LLM-extracted entities proliferate unchecked. "24VAC", "24 VAC", "24V AC", and "24 Volt AC" all become separate nodes. "2-wire", "2 wire", "two-wire" become three Wiring_Config nodes. The graph becomes a hairball of near-duplicates with no edges connecting them, because each was extracted slightly differently. Graph traversal then silently returns empty results for queries that should find matches.

**Why it happens:** LLM entity extraction is not deterministic. Coreference resolution is not built in. Canonicalization is treated as an afterthought.

**Consequences:** High node count, near-zero useful edge density. Queries like "what wiring does the T9 support?" traverse the correct node but miss 80% of its actual connections, which are attached to duplicate nodes.

**Warning signs:**
- Node count is high (>200) for a single-product PDF
- Running `MATCH (n) RETURN n.label, count(*) ORDER BY count(*) DESC` in Neo4j shows many near-identical labels
- `COMPATIBLE_WITH` edges point to nodes with no other connections

**Prevention:**
- Define a strict node type vocabulary before extraction: Product, WiringConfig, SystemType, Spec, Accessory, Terminal. Do not allow LLM to invent types.
- Build a normalization pass between extraction and Neo4j write: lowercase, strip punctuation, apply a known-alias map (e.g., `{"24VAC": "24VAC", "24 VAC": "24VAC"}`)
- Use `MERGE` (not `CREATE`) in all Neo4j write paths — MERGE on the canonical label, not the raw extracted string

**Phase:** Schema design (before any extraction runs) and entity normalization pass (before Neo4j writes).

---

### Pitfall 3: Relationship Type Sprawl

**What goes wrong:** The extraction prompt is underspecified, so the LLM invents relationship labels freely: `WORKS_WITH`, `IS_COMPATIBLE_WITH`, `COMPATIBLE_WITH`, `CAN_USE`, `SUPPORTS`. In Neo4j these are all distinct relationship types. Cypher queries that filter on `COMPATIBLE_WITH` miss the other four. Graph traversal returns incomplete results with no error.

**Why it happens:** Without an explicit closed-world relationship vocabulary in the extraction prompt, LLMs default to natural-language paraphrasing.

**Consequences:** Cypher queries must be written to enumerate all synonym relationship types, or queries are silently wrong. Visualization is noisy. Graph schema is not inspectable.

**Warning signs:**
- `CALL db.relationshipTypes()` returns more than 8-10 types for a single-product graph
- Similar queries about "compatibility" return different results depending on exact phrasing

**Prevention:**
- Hard-code the allowed relationship set in the extraction prompt as an enum: `COMPATIBLE_WITH | REQUIRES | REPLACES | HAS_SPEC | HAS_TERMINAL | SUPPORTS_SYSTEM | ACCESSORY_FOR`
- Post-extraction: validate that every extracted edge relation is in the allowed set; reject or remap anything outside it
- Test with `CALL db.schema.visualization()` after first load to confirm the schema matches intent

**Phase:** Extraction prompt design — lock this before writing any graph insertion code.

---

### Pitfall 4: Neo4j Connection Not Properly Abstracted

**What goes wrong:** The existing codebase has `GraphStore` backed by networkx. If Neo4j integration is bolted on without a clean adapter boundary, environment differences (no Docker, wrong Bolt port, auth failure) cause import-time crashes rather than helpful errors. Worse: code paths that work against networkx silently break against Neo4j because networkx is mutation-in-memory while Neo4j requires explicit transactions and connection lifecycle management.

**Why it happens:** Prototype urgency leads to replacing networkx calls directly rather than implementing a clean adapter.

**Consequences:** The pipeline fails in any environment without Neo4j running. Partial writes during failures leave the graph in an inconsistent state (no transaction rollback). Testing requires a live Neo4j instance.

**Warning signs:**
- `from neo4j import GraphDatabase` at module top level rather than inside a class `__init__`
- `session.run()` calls not wrapped in `with session.begin_transaction()`
- No connection health check / fallback in `store.py`

**Prevention:**
- Implement a `Neo4jGraphStore` class that implements the same interface as the existing `GraphStore` (upsert_node, upsert_edge, neighbors_multi_hop). The pipeline code switches via the config `graph.backend` key — no other code changes.
- Use `driver.verify_connectivity()` on startup and raise a clear error with remediation hint if Neo4j is not reachable
- All bulk writes (ingest) go inside a single transaction — wrap with try/except and explicit rollback
- Keep the networkx backend working as a no-dependency fallback for unit tests

**Phase:** Neo4j adapter implementation — the entire adapter should be built and tested in isolation before connecting it to the pipeline.

---

### Pitfall 5: LLM Prompt Returns Unstructured Text, Graph Code Assumes JSON

**What goes wrong:** The extraction prompt asks the LLM to return JSON with `{nodes: [], edges: []}`. The LLM returns JSON wrapped in a markdown code fence (` ```json ... ``` `). The `json.loads()` call fails with a parse error. More subtly: for complex wiring tables the LLM returns partial JSON, truncated mid-array because the response hit a token limit.

**Why it happens:** Groq / most LLMs do not guarantee raw JSON output unless you use a structured output / function-calling mode. Markdown wrapping is the default for chat-tuned models.

**Consequences:** Ingestion pipeline crashes silently or raises a cryptic JSON decode error. With no retry or fallback, the entire extraction is lost.

**Warning signs:**
- Extracted strings start with ` ```json ` prefix
- `json.JSONDecodeError` in ingestion logs for large PDF pages
- Node/edge counts are lower than expected (truncation)

**Prevention:**
- Strip markdown fences before parsing: `text.strip().removeprefix("```json").removesuffix("```").strip()`
- Use Groq's `response_format={"type": "json_object"}` parameter if the model supports it (llama-3 variants on Groq do support this)
- Set an explicit `max_tokens` budget per extraction call sized to the expected output, and add a length check — if the response ends without a closing `}` or `]`, log and retry with a smaller chunk
- Validate extracted JSON against a schema (pydantic or jsonschema) before writing to Neo4j

**Phase:** LLM extraction pipeline — before any Neo4j writes.

---

### Pitfall 6: Graph Traversal Returns Context the LLM Cannot Use

**What goes wrong:** `neighbors_multi_hop()` at depth 2 from a product node on a dense graph returns hundreds of triples. These are serialized linearly and stuffed into the Groq prompt. The LLM either hits the context limit and truncates, or produces a hallucinated answer because the relevant 3 triples are buried in 200 irrelevant ones. The current `generate_answer()` stub caps at 12 triples (`graph_context[:12]`) — this cap is arbitrary and may exclude critical edges.

**Why it happens:** Graph traversal is not retrieval-aware. BFS returns everything reachable, not everything relevant.

**Consequences:** Answers to simple compatibility questions are wrong or fabricated. The system is harder to debug because the raw context passed to the LLM is not logged.

**Warning signs:**
- Graph context passed to LLM exceeds 2000 tokens
- Answers are verbose and generic rather than specific (e.g., "the T9 may be compatible with various systems" instead of listing them)
- Removing the graph context from the prompt does not meaningfully change the answer

**Prevention:**
- Filter graph context before LLM call: only include triples where the relation type is relevant to the question (parse question intent → map to relation types)
- Cap context at ~20 triples but prioritize: direct edges first, then 2-hop, and deprioritize `HAS_SPEC` edges for compatibility questions
- Log the exact context string passed to Groq for every query — this is mandatory for debugging answer quality
- Start with depth=1 traversal and only increase to depth=2 if depth=1 context is insufficient

**Phase:** Query pipeline and LLM generation — critical to get right before building the UI.

---

### Pitfall 7: Wiring Configuration Modeled as a String, Not a Node

**What goes wrong:** Wiring configurations (e.g., "2-wire heat only", "4-wire heat/cool with common") are stored as string properties on Product nodes rather than as first-class WiringConfig nodes. This means you cannot traverse "which products support 4-wire?" — you must do a string search, which breaks graph-based retrieval entirely.

**Why it happens:** The product-centric schema instinct is to store everything as properties. Wiring configs look like attributes, not entities.

**Consequences:** The central value of the graph — traversal for compatibility — is broken for the most common HVAC query type ("does this thermostat work with my wiring?"). You fall back to string matching, which is no better than plain RAG.

**Warning signs:**
- WiringConfig appears as a string property rather than a node type in the schema
- Cypher query for "find products compatible with 2-wire" requires `WHERE n.wiring_config CONTAINS "2-wire"` instead of a relationship traversal

**Prevention:**
- Model WiringConfig as a node type from the start: `(:Product)-[:SUPPORTS_WIRING]->(:WiringConfig {label: "2-wire heat only", wire_count: 2, has_common: false})`
- Do the same for SystemType (conventional, heat pump, multi-stage) — these must be nodes, not properties
- Rule of thumb: if you will ever query "give me all X that have Y", Y must be a node, not a property

**Phase:** Schema design — this is a structural decision that cannot be easily retrofitted after data is loaded.

---

## Moderate Pitfalls

---

### Pitfall 8: No Idempotent Ingest

**What goes wrong:** Running the ingestion pipeline twice creates duplicate nodes and edges in Neo4j because `CREATE` is used instead of `MERGE`. The graph doubles in size on each run. All traversal results double-count.

**Prevention:** All Cypher write statements must use `MERGE` on a unique property (typically `node_id`). Test idempotency explicitly: run ingest twice, assert node count is unchanged.

**Phase:** Neo4j adapter implementation.

---

### Pitfall 9: Groq Model Name Hard-Coded in Multiple Places

**What goes wrong:** The constraint is "model name must be a single configurable placeholder." If the model name is referenced in more than one place in the codebase, changing models requires a grep-and-replace, which is fragile. This matters because Groq's model roster changes frequently (models are added and deprecated on short cycles).

**Prevention:** Single source of truth: `config/settings.yaml` has `llm.model: llama-3.1-8b-instant`. All code reads from config. Do not accept the model name as a CLI arg or hardcode it in `generate.py`.

**Phase:** LLM integration.

---

### Pitfall 10: PDF Page Ordering Loses Section Context

**What goes wrong:** When extracting entities, each PDF page is processed independently. A wiring diagram on page 7 refers to terminal names defined in a table on page 5. Extracted in isolation, the page 7 entities are orphaned — the extraction has no knowledge of the terminal definitions.

**Prevention:**
- Pass the full extracted text of the relevant section (not just the current page) as context to the LLM extraction call
- Alternatively, extract the terminal/spec reference tables first (pages with dense tables) and include them as a "known entity" seed in all subsequent extraction prompts

**Phase:** PDF ingestion — chunk strategy design.

---

### Pitfall 11: No Graph Integrity Validation Step

**What goes wrong:** After ingestion, nobody verifies that the graph is internally consistent. Edge source/target IDs reference non-existent nodes. `REPLACES` edges are one-directional but the replacement product node was never created. Traversal silently returns partial results.

**Prevention:**
- After every ingest run, execute validation Cypher queries:
  - `MATCH ()-[r]->() WHERE NOT EXISTS {MATCH (n) WHERE id(n) = id(startNode(r))} RETURN count(r)` — dangling edge sources
  - `MATCH (p:Product)-[:REPLACES]->(q) WHERE NOT (q:Product) RETURN q.node_id` — replacement targets that are not products
- Fail the pipeline if validation fails

**Phase:** Ingest pipeline — add validation as the final step.

---

## Minor Pitfalls

---

### Pitfall 12: Streamlit State Resets Graph Connection

**What goes wrong:** Streamlit reruns the entire script on every user interaction. If the Neo4j driver is instantiated at module scope, it may create a new connection pool on every rerun, exhausting connections.

**Prevention:** Use `st.cache_resource` to cache the Neo4j driver instance across reruns.

**Phase:** UI implementation.

---

### Pitfall 13: Cypher Injection via User Query

**What goes wrong:** If user natural-language input is interpolated directly into a Cypher string (prototype shortcut), a malicious input can drop the entire database. Even in a prototype this is embarrassing in a demo.

**Prevention:** Always use parameterized Cypher: `session.run("MATCH (n {label: $label})", label=user_input)`. Never f-string user input into Cypher.

**Phase:** Query pipeline.

---

## Phase-Specific Warning Map

| Phase | Topic | Likely Pitfall | Mitigation |
|-------|-------|---------------|------------|
| PDF Ingestion | Table extraction | Pitfall 1 — column fusion | Use `pdfplumber.extract_tables()`, validate raw output first |
| Schema Design | Node types | Pitfall 7 — wiring as property | WiringConfig and SystemType must be nodes |
| Schema Design | Relationship types | Pitfall 3 — type sprawl | Lock enum before writing extraction prompt |
| LLM Extraction | Output parsing | Pitfall 5 — markdown wrapping | Strip fences, use json_object mode, validate schema |
| LLM Extraction | Entity dedup | Pitfall 2 — node explosion | Normalization pass + MERGE strategy |
| Neo4j Adapter | Connection mgmt | Pitfall 4 — no abstraction | Implement adapter interface, verify_connectivity on init |
| Ingest Pipeline | Idempotency | Pitfall 8 — duplicate nodes | MERGE everywhere, test double-run |
| Ingest Pipeline | Integrity | Pitfall 11 — dangling edges | Validation Cypher as final ingest step |
| Query Pipeline | Context size | Pitfall 6 — LLM context overload | Filter and cap triples, log context |
| LLM Config | Model name | Pitfall 9 — hard-coding | Single config key in settings.yaml |
| UI | Connection pooling | Pitfall 12 — Streamlit reruns | st.cache_resource for Neo4j driver |
| UI | Security | Pitfall 13 — Cypher injection | Parameterized queries only |

---

## Sources

- Codebase inspection: `src/graph/extract.py`, `src/graph/store.py`, `src/llm/generate.py`, `config/settings.yaml`
- Domain knowledge: Neo4j driver best practices, Groq API behavior, pdfplumber table extraction, GraphRAG context assembly patterns
- Confidence: HIGH for Neo4j/Groq/pdfplumber mechanics; MEDIUM for LLM extraction behavior (model-specific, verified against known Groq llama-3 behavior)
