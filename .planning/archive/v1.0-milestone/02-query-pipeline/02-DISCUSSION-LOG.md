# Phase 2: Query Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-15
**Phase:** 02-query-pipeline
**Areas discussed:** Entity Detection, Graph Traversal Strategy, Answer Generation, Demo Queries

---

## Entity Detection

| Option | Description | Selected |
|--------|-------------|----------|
| LLM extraction | Send question to Groq/OpenAI with known node types/IDs | ✓ |
| Keyword lookup table | Fuzzy-match question tokens against Neo4j node labels | |
| Hybrid: keywords first, LLM fallback | Try keyword matching first, LLM if no hits | |

**User's choice:** LLM extraction
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Direct node IDs | Prompt includes known node_ids, LLM returns exact matches | ✓ |
| Descriptive terms + fuzzy match | LLM returns natural terms, then fuzzy-matched | |

**User's choice:** Direct node IDs
**Notes:** None

---

## Graph Traversal Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Cypher pattern queries | Specific Cypher per relationship type | ✓ |
| BFS multi-hop via driver | Generic BFS from matched node | |
| LLM-generated Cypher | LLM writes Cypher from question | |

**User's choice:** Cypher pattern queries
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Depth 2 | Default, good balance for small graph | ✓ |
| Depth 1 | Direct neighbors only | |
| Configurable via CLI flag | Default 2 with --depth override | |

**User's choice:** Depth 2
**Notes:** None

---

## Answer Generation

| Option | Description | Selected |
|--------|-------------|----------|
| Structured prose + evidence | Natural language + Graph Evidence section | ✓ |
| Free-form text only | Just natural language answer | |
| JSON structured output | Answer as structured JSON | |

**User's choice:** Structured prose + evidence
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Honest 'not found' message | Clear message suggesting valid topics | ✓ |
| LLM answers anyway | Attempt answer without graph context | |
| You decide | Claude's discretion | |

**User's choice:** Honest 'not found' message
**Notes:** None

---

## Demo Queries

| Option | Description | Selected |
|--------|-------------|----------|
| YAML/JSON eval file | Store in data/eval/queries.json | ✓ |
| Hardcoded in test file | Put in pytest test directly | |
| You decide | Claude's discretion | |

**User's choice:** YAML/JSON eval file
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Standard set | Accessories, wiring, specs — covers 3 relation types | ✓ |
| Include replacements | Tests REPLACES edge (no data yet) | |
| Custom queries | User-specified | |

**User's choice:** Standard set
**Notes:** None

---

## Claude's Discretion

- Exact Cypher query patterns per relationship type
- Answer prompt template wording
- Pydantic model structure for query response

## Deferred Ideas

None
