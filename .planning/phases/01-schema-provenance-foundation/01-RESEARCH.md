# Phase 1: Schema & Provenance Foundation - Research

**Researched:** 2026-05-02
**Domain:** Neo4j graph schema design, MERGE/provenance patterns, Cypher idempotency
**Confidence:** HIGH

## Summary

Phase 1 introduces document-level provenance into the existing Neo4j graph so that, in later phases, the same fact extracted from multiple Honeywell PDFs is both **citable** (which PDF said it) and **deduplicated** (one canonical entity, multiple evidence edges). The schema change is strictly additive: a new `:Document` node kind, a `MENTIONED_IN` relation, and a `source_doc` property on every business edge — no existing kind or relation is renamed or restructured.

The right Cypher primitives are already well-established: `MERGE … ON CREATE SET … ON MATCH SET …` for nodes, with `coll.distinct(coalesce(n.source_docs, []) + $doc_id)` to accumulate `source_docs[]` without duplicates [VERIFIED: Context7 / Neo4j Cypher Manual]. Edge MERGE keys must include `source_doc` so re-extracting the same fact from a different PDF creates a parallel evidence edge rather than overwriting the existing one (SCHEMA-04). Re-extracting the same fact from the *same* PDF must remain a no-op (idempotency for BATCH-04 in Phase 3).

The current `neo4j_loader.py` already does node MERGE on `id` and edge MERGE on `(source, type, target)`. Phase 1 must (a) add `source_doc` to the edge MERGE key, (b) wrap node MERGE with the `source_docs[]` accumulator, and (c) introduce a `:Document` upsert and `MENTIONED_IN` edge per node-document pair. Existing T9 ingest must continue to produce identical node/edge counts when re-run (success criteria + INGEST-05 dependency from Phase 2).

**Primary recommendation:** Build a thin `provenance.py` helper module exposing `merge_document(tx, doc)`, `merge_node_with_provenance(tx, node, doc_id)`, and `merge_edge_with_provenance(tx, edge, doc_id)`. Refactor `neo4j_loader.py` to call these helpers instead of inlining Cypher. This isolates the additive schema change from the existing loader logic and gives Phase 2/3 a stable seam to call into.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Document metadata storage | Neo4j (graph DB) | — | Documents are first-class graph entities, queryable alongside facts |
| Per-fact provenance | Neo4j edge property | — | `source_doc` lives on the edge so a single Cypher query reveals citation |
| Node deduplication across docs | Neo4j MERGE on canonical id | Python normalizer (Phase 2) | DB enforces single-instance via uniqueness constraint; normalizer ensures the id is canonical before the loader sees it |
| `source_docs[]` accumulation | Cypher `coll.distinct` in MERGE | — | DB-side accumulation is atomic per transaction, avoids read-modify-write race |
| Schema definition (Python-side) | `src/graph/schema.py` dataclasses | — | Existing pattern; Phase 1 only adds new types, no rewrite |
| PDF identity assignment (`doc_id`) | Ingest pipeline (Phase 2 owns) | Phase 1 defines the contract | Phase 1 must specify what `doc_id` *is* (slug, hash, manifest key) so Phase 2 can supply it |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCHEMA-01 | Add `:Document` node kind with `(doc_id, title, sku, source_url, ingested_at)` | "Schema design" + "Code Examples / Document upsert" sections |
| SCHEMA-02 | Add `MENTIONED_IN` relation (entity → document) | "Schema design" + "Code Examples / MENTIONED_IN edge" |
| SCHEMA-03 | All extracted edges carry `source_doc` property | "Loader architecture" — `source_doc` injected at write time |
| SCHEMA-04 | Edge MERGE keyed on `(source, target, relation, source_doc)` → parallel evidence edges | "Provenance edge model" — Pattern A; "Code Examples / Edge MERGE with provenance" |
| SCHEMA-05 | Nodes deduplicate; `source_docs[]` via ON CREATE / ON MATCH | "Neo4j MERGE patterns" + "Code Examples / Node MERGE with source_docs" |

## Standard Stack

### Core (already in `requirements.txt` — no new deps needed for Phase 1)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `neo4j` | 5.28.1 | Bolt driver, sync sessions, transactions | Already pinned; SCHEMA-04/05 patterns are pure Cypher, driver-agnostic [VERIFIED: requirements.txt] |
| `python-dotenv` | 1.0.1 | Load NEO4J_URI / USER / PASSWORD | Already used by `neo4j_loader.py` |
| `pydantic` | >=2.7 | Validate `Document` payloads before write | Already in tree (used by `instructor`); use for the new `Document` dataclass-or-model symmetric to `EntityNode` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | (add to requirements.txt — currently missing) | Unit/integration tests for Cypher idempotency & MERGE semantics | Phase 1 test suite |
| `testcontainers[neo4j]` | optional | Spin up disposable Neo4j for integration tests | If we want CI tests against a real DB; otherwise document a manual `docker run neo4j:5` step |

**Version verification:**
- `neo4j==5.28.1` — pinned; no change. `coll.distinct()` is available in Neo4j 5.x [VERIFIED: Context7 / Cypher Manual `current` channel].
- `pytest` is referenced in CLAUDE.md but not pinned in requirements.txt — Phase 1 should add `pytest>=8.0` so subsequent phases inherit it.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Edge property `source_doc` (single string) | Edge property `source_docs[]` (array) | Array on edges defeats SCHEMA-04 (parallel evidence edges). Single-string is the requirement; arrays belong on **nodes** only. |
| `MENTIONED_IN` separate relation | Reuse existing edges with `source_doc` | `MENTIONED_IN` makes "which docs mention entity X?" a 1-hop traversal regardless of which business relation the entity participates in — required by SCHEMA-02 and QUALITY-03. |
| `coll.distinct()` for dedup | `apoc.coll.toSet()` | `coll.distinct` is built-in (no APOC dependency). Confirmed in Neo4j 5.x [CITED: neo4j.com/docs/cypher-manual/current/functions/list]. |
| Reading existing `source_docs`, deduping in Python, writing back | DB-side `coll.distinct(coalesce(...) + [$doc])` | Python-side read-modify-write is non-atomic; two concurrent loaders would race. DB-side keeps the operation single-transaction. |

## Architecture Patterns

### System Architecture Diagram

```
                       data/raw/<pdf>            data/raw/manifest.json
                            │                            │
                            ▼                            ▼
                    pdf_parser.py              (Phase 2 — out of scope)
                            │                            │
                            ▼                            │
                    entity_extractor.py                  │
                            │                            │
                            ▼                            ▼
                  rich graph dict   +   doc_id, title, sku, source_url, ingested_at
                            │                            │
                            └────────────┬───────────────┘
                                         ▼
                            ┌──────────────────────────────┐
                            │  neo4j_loader.py             │
                            │   1. merge_document()        │
                            │   2. for each node:          │
                            │       merge_node + accumulate│
                            │       source_docs[]          │
                            │       MERGE MENTIONED_IN     │
                            │   3. for each edge:          │
                            │       MERGE keyed on         │
                            │       (s,t,rel,source_doc)   │
                            └──────────────────────────────┘
                                         │
                                         ▼
                                  Neo4j (Bolt 7687)
                                  ├─ :Document {doc_id ...}
                                  ├─ :Product / :Accessory / :Thermostat / ...
                                  │     └─ source_docs: [doc_id, ...]
                                  ├─ (entity)-[:MENTIONED_IN]->(:Document)
                                  └─ (entity)-[business_rel {source_doc}]->(entity)
```

### Component Responsibilities

| File | Responsibility |
|------|----------------|
| `src/graph/schema.py` | Add `Document` model + `MENTIONED_IN` to `ALLOWED_RELATIONS`; expose `VALID_KINDS` including `Document` |
| `src/graph/provenance.py` (NEW) | Cypher helpers for document upsert, node-with-provenance MERGE, edge-with-provenance MERGE |
| `src/graph/neo4j_loader.py` | Accept `doc_metadata` parameter; route every write through `provenance.py` helpers |
| `src/graph/store.py` | `Neo4jGraphStore` may need a `doc_id`-aware `upsert_edge` overload (or leave as-is and call `provenance.py` directly from the loader) |
| `tests/test_provenance.py` (NEW) | Assert: parallel edges from 2 PDFs, single node with `source_docs` length 2, every edge has `source_doc`, idempotent re-run |

### Pattern 1: Single-Transaction MERGE with Provenance Accumulation
**What:** Combine node MERGE, `source_docs[]` accumulation, and `MENTIONED_IN` edge in one Cypher statement so the operation is atomic.
**When to use:** Every node write during PDF ingestion.
**Example:**
```cypher
// Source: Context7 / neo4j.com/docs/cypher-manual/current/clauses/merge
MERGE (n:Product {id: $node_id})
ON CREATE SET
  n += $props,
  n.source_docs = [$doc_id],
  n.first_seen = timestamp()
ON MATCH SET
  n += $props,
  n.source_docs = coll.distinct(coalesce(n.source_docs, []) + $doc_id),
  n.last_seen = timestamp()
WITH n
MATCH (d:Document {doc_id: $doc_id})
MERGE (n)-[m:MENTIONED_IN]->(d)
ON CREATE SET m.first_mentioned = timestamp()
RETURN n.id, size(n.source_docs) AS doc_count
```

### Pattern 2: Edge MERGE Keyed on `source_doc` (parallel evidence)
**What:** Include `source_doc` in the MERGE key dictionary so the same business fact from two PDFs creates two parallel relationships.
**When to use:** Every business edge write.
**Example:**
```cypher
// Source: Context7 / neo4j.com/docs/cypher-manual/current/clauses/merge
// Note: relationship type ($rel) must be parameterized at the Python level
// (Cypher doesn't allow rel-type as a $param). Validate $rel against
// VALID_RELATIONS before f-string substitution.
MATCH (a {id: $source_id})
MATCH (b {id: $target_id})
MERGE (a)-[r:COMPATIBLE_WITH {source_doc: $doc_id}]->(b)
ON CREATE SET r += $props, r.created = timestamp()
ON MATCH  SET r += $props, r.updated = timestamp()
RETURN id(r) AS rid
```

Result: ingesting the *same* fact from doc A twice → 1 edge (idempotent). Ingesting the same fact from doc A and doc B → 2 parallel edges, distinguishable by `r.source_doc`. This satisfies SCHEMA-04 and the Phase 3 BATCH-04 idempotency goal simultaneously.

### Pattern 3: Document Upsert (one per PDF)
**What:** Write the `:Document` node before any entities so the `MENTIONED_IN` MATCH always finds it.
**When to use:** Once at the start of each PDF ingest.
**Example:**
```cypher
MERGE (d:Document {doc_id: $doc_id})
ON CREATE SET
  d.title = $title,
  d.sku = $sku,
  d.source_url = $source_url,
  d.ingested_at = datetime(),
  d.first_ingested = datetime()
ON MATCH SET
  d.title = $title,
  d.sku = $sku,
  d.source_url = $source_url,
  d.last_reingested = datetime()
RETURN d.doc_id
```

### Recommended Project Structure
```
src/graph/
├── schema.py            # +Document model, +MENTIONED_IN literal (additive)
├── provenance.py        # NEW — Cypher helper functions
├── neo4j_loader.py      # MODIFIED — accepts doc_metadata, routes through provenance.py
├── store.py             # unchanged or thin pass-through additions
└── extract.py           # unchanged in Phase 1 (Phase 2 modifies for multi-PDF)

tests/
├── test_provenance.py   # NEW — integration tests against live or testcontainer Neo4j
└── test_schema.py       # NEW — unit tests for Document dataclass validation
```

### Anti-Patterns to Avoid
- **Storing `source_doc` only on `MENTIONED_IN`, not on business edges.** This breaks "trace a specific fact back to its PDF" — you'd only know which docs mention an entity, not which doc supplied a particular `COMPATIBLE_WITH` claim. SCHEMA-03 explicitly requires `source_doc` on edges.
- **Using `+=` to append to a list property.** `n.source_docs += $doc_id` does **not** work in Cypher — the `+=` operator on a node only merges property maps. Use `n.source_docs = coalesce(n.source_docs, []) + $doc_id` (then wrap in `coll.distinct`).
- **Setting `source_docs` unconditionally on MATCH.** If you do `ON MATCH SET n.source_docs = [$doc_id]`, you wipe prior provenance. Always coalesce + concat + distinct.
- **MERGEing edges without `source_doc` in the key map.** This collapses two PDFs into one edge and silently loses citation surface — directly violates SCHEMA-04.
- **Writing `:Document` after entity nodes in the same transaction.** If `MENTIONED_IN`'s `MATCH (d:Document …)` runs before `:Document` is committed, the relationship is silently dropped. Always upsert document first, *then* nodes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| List deduplication in Cypher | Custom `[x IN list WHERE NOT x IN seen ...]` reduce | `coll.distinct(list)` | Built-in, O(n), correct null handling [VERIFIED: Context7] |
| Idempotent upsert | Read-then-write-if-missing pattern in Python | `MERGE … ON CREATE SET … ON MATCH SET …` | Atomic; eliminates race conditions; one round-trip |
| Parallel-edge dedup logic | Track edge keys in Python, skip duplicates | MERGE keyed on `(s,t,rel,source_doc)` | DB enforces it; survives concurrent loaders |
| Document timestamp parsing | Manually format ISO-8601 strings in Python | Cypher `datetime()` / `timestamp()` | DB-side, timezone-stable, comparable in queries |
| Connection pooling | Wrap driver with custom retry | `GraphDatabase.driver(...)` already pools; use `session.execute_write` | Built into 5.x driver [CITED: neo4j-python-driver docs] |

**Key insight:** Every "tracking provenance correctly" subproblem has a one-line Cypher solution. The risk in this phase is *not* algorithmic — it's writing Python code that drifts from these patterns and reintroduces races or wipe-on-update bugs.

## Runtime State Inventory

This is a schema-additive phase, not a rename. But two state categories matter:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Existing T9 graph in Neo4j has nodes WITHOUT `source_docs[]` and edges WITHOUT `source_doc`. | One-time backfill OR document that re-running T9 ingest with `doc_id="t9_install_guide"` populates provenance retroactively. Recommendation: backfill via re-ingest, since SCHEMA-05 requires `source_docs[]` to exist. |
| Live service config | Neo4j unique-id constraints in `neo4j_loader.create_constraints()` enumerate labels explicitly (`Thermostat`, `HVACSystemType`, …). `:Document` is a new label and must be added to that list, plus a unique constraint on `doc_id`. | Code edit in `create_constraints()`. |
| OS-registered state | None — no scheduled jobs or systemd units reference graph state. | None. |
| Secrets/env vars | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` already in `.env`; no new secrets. | None. |
| Build artifacts | None — no compiled artifacts. | None. |

**The canonical question:** *After Phase 1 code lands, what's already in the developer's local Neo4j that lacks provenance?* Answer: the T9 v1.0 graph. The plan must include a step to either (a) `--reset` and re-ingest T9 with the new loader, or (b) ship a one-shot Cypher migration that backfills `source_doc = "t9_install_guide"` on all existing edges and `source_docs = ["t9_install_guide"]` on all existing nodes. Recommendation: option (a) — simpler, deterministic, and the `--reset` flag already exists in `neo4j_loader.py`.

## Common Pitfalls

### Pitfall 1: `MERGE` on edge without `source_doc` in key map
**What goes wrong:** First PDF creates edge `(T9)-[:COMPATIBLE_WITH]->(HeatPump)` with `source_doc=A`. Second PDF MERGEs the same edge — Neo4j matches the existing one, runs `ON MATCH SET source_doc=B`, and overwrites doc A's citation. Now no edge claims doc A.
**Why it happens:** Treating MERGE like an upsert on (s,t,rel) when SCHEMA-04 needs (s,t,rel,source_doc).
**How to avoid:** `MERGE (a)-[r:REL {source_doc: $doc_id}]->(b)` — `source_doc` *inside* the curly braces, part of the matching key.
**Warning signs:** Test assertion "ingesting same fact from 2 PDFs yields 2 edges" fails with count=1.

### Pitfall 2: `source_docs` overwritten on MATCH
**What goes wrong:** `ON MATCH SET n.source_docs = [$doc_id]` replaces the array each time, so the final list contains only the most recently ingested PDF.
**Why it happens:** Forgetting that `ON MATCH` fires *every* re-ingest, not only on conflict.
**How to avoid:** `ON MATCH SET n.source_docs = coll.distinct(coalesce(n.source_docs, []) + $doc_id)`.
**Warning signs:** Node mentioned in 3 PDFs has `source_docs.length == 1`.

### Pitfall 3: Idempotent re-ingest growing `source_docs` unboundedly
**What goes wrong:** Without `coll.distinct`, re-running ingest of doc A 5 times yields `source_docs = ["A","A","A","A","A"]`.
**Why it happens:** `+ $doc_id` always appends.
**How to avoid:** Always wrap with `coll.distinct(...)`.
**Warning signs:** BATCH-04 (Phase 3) idempotency test fails: same input twice → different array lengths.

### Pitfall 4: Relationship type cannot be a query parameter
**What goes wrong:** `MERGE (a)-[r:$rel]->(b)` is a Cypher syntax error. Relationship types must be string-substituted at the Python level.
**Why it happens:** Driver users assume parameter substitution applies everywhere.
**How to avoid:** Validate `relation` against `VALID_RELATIONS` set, then f-string. `neo4j_loader.py` already does this with a `safe_rel` sanitization step — keep that pattern.
**Warning signs:** `CypherSyntaxError: Invalid input '$'`.

### Pitfall 5: `:Document` not committed before `MENTIONED_IN` MATCH
**What goes wrong:** If document upsert and entity MERGE run in separate transactions in unexpected order, the `MATCH (d:Document {doc_id: $doc_id})` for `MENTIONED_IN` finds nothing and the relationship is silently skipped.
**Why it happens:** Refactoring loader into helpers without preserving transaction ordering.
**How to avoid:** Either (a) document upsert in its own committed transaction *before* entity loop begins, or (b) use `MERGE (d:Document …)` inline in every node write (slower but unconditional).
**Warning signs:** `MATCH (n)-[:MENTIONED_IN]->(d) RETURN count(*)` returns far fewer than node count.

### Pitfall 6: `source_doc` IS NULL because helper signature drift
**What goes wrong:** Some callsite of `upsert_edge` doesn't pass `doc_id`, defaults to `None`, edge gets written with `source_doc: null`.
**Why it happens:** Loose `**attributes` kwargs in `Neo4jGraphStore.upsert_edge` (current code line 78) don't enforce `source_doc`.
**How to avoid:** Make `doc_id` a required positional argument on the new helper functions; let mypy / runtime check fail loudly. The success-criterion query `MATCH ()-[r]->() WHERE r.source_doc IS NULL RETURN count(r)` should be a CI assertion, not just a manual check.
**Warning signs:** Cypher audit returns count > 0.

## Code Examples

### Adding `Document` to `schema.py` (additive)
```python
# Source: derived from existing src/graph/schema.py pattern
from typing import Literal, get_args
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

NODE_KIND = Literal[
    "Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec",
    "Document",  # NEW
]
ALLOWED_RELATIONS = Literal[
    "COMPATIBLE_WITH", "REPLACES", "SUPPORTS_WIRING", "HAS_SPEC",
    "MENTIONED_IN",  # NEW
]
VALID_KINDS = set(get_args(NODE_KIND))
VALID_RELATIONS = set(get_args(ALLOWED_RELATIONS))

@dataclass
class Document:
    doc_id: str           # canonical slug, e.g. "t9_install_guide"
    title: str
    sku: Optional[str]
    source_url: Optional[str]
    ingested_at: str      # ISO-8601 string; DB stores as datetime()
```

### `provenance.py` (new module — sketch)
```python
# Source: synthesized from Context7 MERGE patterns + project conventions
from typing import Any, Dict
from neo4j import ManagedTransaction

def merge_document(tx: ManagedTransaction, doc: Dict[str, Any]) -> None:
    tx.run("""
        MERGE (d:Document {doc_id: $doc_id})
        ON CREATE SET d.title=$title, d.sku=$sku, d.source_url=$source_url,
                      d.ingested_at=datetime($ingested_at),
                      d.first_ingested=datetime()
        ON MATCH  SET d.title=$title, d.sku=$sku, d.source_url=$source_url,
                      d.last_reingested=datetime()
    """, **doc)

def merge_node_with_provenance(
    tx: ManagedTransaction, label: str, node_id: str,
    props: Dict[str, Any], doc_id: str,
) -> None:
    # label validated against VALID_KINDS by caller
    tx.run(f"""
        MERGE (n:{label} {{id: $node_id}})
        ON CREATE SET n += $props,
                      n.source_docs = [$doc_id],
                      n.first_seen = timestamp()
        ON MATCH  SET n += $props,
                      n.source_docs = coll.distinct(coalesce(n.source_docs, []) + $doc_id),
                      n.last_seen = timestamp()
        WITH n
        MATCH (d:Document {{doc_id: $doc_id}})
        MERGE (n)-[m:MENTIONED_IN]->(d)
        ON CREATE SET m.first_mentioned = timestamp()
    """, node_id=node_id, props=props, doc_id=doc_id)

def merge_edge_with_provenance(
    tx: ManagedTransaction, source_id: str, target_id: str,
    rel: str, props: Dict[str, Any], doc_id: str,
) -> None:
    # rel validated against VALID_RELATIONS by caller
    tx.run(f"""
        MATCH (a {{id: $source_id}})
        MATCH (b {{id: $target_id}})
        MERGE (a)-[r:{rel} {{source_doc: $doc_id}}]->(b)
        ON CREATE SET r += $props, r.created = timestamp()
        ON MATCH  SET r += $props, r.updated = timestamp()
    """, source_id=source_id, target_id=target_id, props=props, doc_id=doc_id)
```

### Constraints to add in `create_constraints()`
```python
# Source: existing src/graph/neo4j_loader.py pattern
labels.append("Document")  # add to existing list

# Plus a new constraint on Document.doc_id
sess.run("""
    CREATE CONSTRAINT constraint_document_doc_id IF NOT EXISTS
    FOR (d:Document) REQUIRE d.doc_id IS UNIQUE
""")
```

### Cypher audit queries (use as test assertions)
```cypher
// Every business edge must carry source_doc
MATCH ()-[r]->()
WHERE type(r) <> 'MENTIONED_IN' AND r.source_doc IS NULL
RETURN count(r) AS missing
// expected: 0

// Same fact from 2 PDFs → 2 parallel edges
MATCH (a)-[r]->(b)
WHERE a.id = $src AND b.id = $tgt AND type(r) = $rel
RETURN count(r) AS evidence_count, collect(r.source_doc) AS sources
// expected after ingesting docs A,B: evidence_count=2, sources=["A","B"]

// Node mentioned in N PDFs → exactly one node, source_docs length N
MATCH (n {id: $node_id})
RETURN count(n) AS instances, size(n.source_docs) AS doc_count
// expected: instances=1, doc_count=N

// Every entity has a MENTIONED_IN edge for each doc in source_docs
MATCH (n) WHERE n.source_docs IS NOT NULL
RETURN n.id,
       size(n.source_docs) AS expected,
       size([(n)-[:MENTIONED_IN]->(d) | d.doc_id]) AS actual
// expected: actual == expected for every row
```

## State of the Art

| Old Approach (v1.0 / current code) | Phase 1 Approach | Impact |
|--------------|------------------|--------|
| `neo4j_loader.py` MERGEs edges on `(source, type, target)` only | MERGE on `(source, type, target, source_doc)` | Same fact from N PDFs → N edges (was: silent overwrite) |
| Nodes have no provenance properties | Nodes carry `source_docs[]` accumulated via ON CREATE/ON MATCH | Citation queryable per node |
| No `:Document` nodes; `source_document` only in JSON metadata | First-class `:Document` nodes with unique `doc_id` constraint | Documents are joinable graph entities |
| `relation` field sanitized via regex (`upper(); ascii-only`) | Keep this; add `VALID_RELATIONS` enforcement before f-string substitution | Tighter; prevents injection of unexpected types |

**Deprecated/outdated patterns in current code to refactor:**
- `neo4j_loader.load_edges()` line 161-166: edge MERGE without `source_doc` — must be replaced.
- `neo4j_loader.load_nodes()` line 128: node MERGE without `source_docs[]` accumulation — must be replaced.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `doc_id` is a stable string slug per PDF (e.g., `"t9_install_guide"`, `"t6_pro_install"`) defined in a manifest, not a hash of the file | Schema design / Phase 1-Phase 2 contract | If `doc_id` is content-hash, re-ingesting an edited PDF creates a new document instead of updating — Phase 3 BATCH-04 idempotency breaks. **Planner must lock this with the user.** [ASSUMED] |
| A2 | Phase 1 backfills T9 by re-ingesting (option a in Runtime State Inventory), not by writing a Cypher migration | Runtime State Inventory | If user prefers migration-style backfill (preserves graph state without `--reset`), the plan needs a different task. [ASSUMED] |
| A3 | `:Document` should NOT have `MENTIONED_IN` outgoing — only entities → documents, never document → document | Schema design | If user wants document-document relations (e.g., "T6 Pro guide supersedes T9 guide"), that's a new relation type out of Phase 1 scope. [ASSUMED] |
| A4 | `ingested_at` is per-load timestamp (overwritten on re-ingest); `first_ingested` is preserved | Pattern 3 | If user wants `ingested_at` immutable (set once, never updated), swap the ON CREATE/ON MATCH semantics. [ASSUMED] |
| A5 | We will add `Document` to the `schema.py` `NODE_KIND` Literal even though documents aren't "entities" in the v1.0 sense | Code Examples | Slight mixing of concerns (a `:Document` is metadata, not a domain entity). Alternative: keep `NODE_KIND` for entities, declare `Document` separately. Cosmetic; both work. [ASSUMED] |
| A6 | `MENTIONED_IN` edges do NOT need `source_doc` themselves (they ARE the citation) | Pitfall 6 audit query | The audit query in Code Examples explicitly excludes `MENTIONED_IN` from the `source_doc IS NULL` check. If user wants uniform property coverage, change the query and the helper. [ASSUMED] |

## Open Questions

1. **What is the canonical form of `doc_id`?**
   - What we know: must be a unique key for `:Document`; must be supplied to every loader call so edges/nodes can attribute to it.
   - What's unclear: slug vs. SHA-256 of file contents vs. manifest-key. Each has different implications for re-ingest of a *modified* PDF.
   - Recommendation: slug from the manifest (`"t9_install_guide"`, `"t6_pro_install_guide"`, etc.). Phase 2 owns the manifest format; Phase 1 must declare the contract.

2. **Backfill strategy for the existing T9 graph**
   - What we know: current T9 nodes/edges have no provenance.
   - What's unclear: re-ingest with `--reset` (clean slate) vs. one-shot Cypher migration (`MATCH (n) WHERE n.source_docs IS NULL SET n.source_docs = ["t9_install_guide"]`).
   - Recommendation: re-ingest (simpler, deterministic). Add a one-line note in plan that local devs run `python -m src.graph.neo4j_loader --reset --doc-id t9_install_guide`.

3. **Should `pdf_parser.py` and `entity_extractor.py` be touched in Phase 1?**
   - What we know: ROADMAP places these in Phase 2.
   - What's unclear: the loader needs `doc_id` from somewhere — does Phase 1 wire it through `ingest.py` end-to-end, or stub it via a CLI flag?
   - Recommendation: Phase 1 adds a `--doc-id` CLI flag to `neo4j_loader.py` and a `doc_id` parameter to its public functions. Phase 2 connects manifest → ingest → loader. This keeps Phase 1 strictly schema/loader and avoids touching parser/extractor.

4. **`MENTIONED_IN` cardinality / properties**
   - What we know: SCHEMA-02 requires the relation exists.
   - What's unclear: does it carry properties (e.g., page numbers, mention count)? `extract.py` already produces `source_page` per node — should that flow onto `MENTIONED_IN`?
   - Recommendation: minimal properties for Phase 1 (`first_mentioned` timestamp only). Defer `page_numbers[]` to Phase 4 if quality work needs it.

5. **Test infrastructure**
   - What we know: CLAUDE.md mentions `pytest 8.x` but it's not in `requirements.txt`.
   - What's unclear: do we run integration tests against a live local Neo4j (developer must have docker container running) or use `testcontainers`?
   - Recommendation: live local Neo4j with a `pytest.mark.integration` marker; tests skip if `NEO4J_URI` is unreachable. Add `pytest>=8.0` to `requirements.txt`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Neo4j 5.x (running locally) | Loader integration tests, manual verification | unknown — must verify on dev machine | — | Document `docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5` in plan |
| `neo4j` Python driver 5.28.1 | All loader code | ✓ | 5.28.1 | — (already pinned) |
| `python-dotenv` | Read `.env` for NEO4J_URI etc. | ✓ | 1.0.1 | — |
| `pytest` >=8.0 | New test suite | likely missing from `requirements.txt` | — | Add to requirements.txt as part of Phase 1 |
| Existing `.env` with NEO4J_PASSWORD | Driver connection | unknown — must verify | — | If missing, document setup step in plan |

**Missing dependencies with no fallback:** none — every gap has a remediation in the plan.

**Missing dependencies with fallback:** `pytest` (just install).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 8.x (NOT YET INSTALLED — Wave 0 task) |
| Config file | none — Wave 0 creates `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_schema.py tests/test_provenance.py -x` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCHEMA-01 | `Document` dataclass validates required fields | unit | `pytest tests/test_schema.py::test_document_required_fields -x` | ❌ Wave 0 |
| SCHEMA-01 | `:Document` node created with all 5 properties + unique constraint | integration | `pytest tests/test_provenance.py::test_document_upsert -x` | ❌ Wave 0 |
| SCHEMA-02 | `MENTIONED_IN` exists in `VALID_RELATIONS` | unit | `pytest tests/test_schema.py::test_mentioned_in_in_valid_relations -x` | ❌ Wave 0 |
| SCHEMA-02 | Loading a node creates `(n)-[:MENTIONED_IN]->(:Document)` | integration | `pytest tests/test_provenance.py::test_mentioned_in_created -x` | ❌ Wave 0 |
| SCHEMA-03 | Every business edge has non-null `source_doc` | integration | `pytest tests/test_provenance.py::test_no_null_source_doc -x` | ❌ Wave 0 |
| SCHEMA-04 | Same fact from 2 PDFs → 2 parallel edges with distinct `source_doc` | integration | `pytest tests/test_provenance.py::test_parallel_evidence_edges -x` | ❌ Wave 0 |
| SCHEMA-05 | Node from N PDFs → 1 node, `source_docs` length N | integration | `pytest tests/test_provenance.py::test_node_dedup_with_source_docs -x` | ❌ Wave 0 |
| (idempotency) | Re-ingesting same PDF twice → same node/edge counts, `source_docs` length unchanged | integration | `pytest tests/test_provenance.py::test_idempotent_reingest -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_schema.py tests/test_provenance.py -x` (skips integration if Neo4j unreachable)
- **Per wave merge:** Full pytest suite + `MATCH ()-[r]->() WHERE r.source_doc IS NULL RETURN count(r)` returning 0 against a live ingest
- **Phase gate:** All 8 tests above green; manual T9 re-ingest verifies non-regression in node/edge counts

### Wave 0 Gaps
- [ ] `requirements.txt` — add `pytest>=8.0`
- [ ] `pytest.ini` (or `pyproject.toml [tool.pytest.ini_options]`) — register `integration` marker, set test paths
- [ ] `tests/conftest.py` — fixtures: `neo4j_driver` (skip if unreachable), `clean_db` (DETACH DELETE before test), sample document metadata
- [ ] `tests/test_schema.py` — covers SCHEMA-01, SCHEMA-02 unit aspects
- [ ] `tests/test_provenance.py` — covers SCHEMA-01..05 + idempotency integration aspects

## Sources

### Primary (HIGH confidence)
- [VERIFIED: Context7 / `/websites/neo4j_cypher-manual_current`] — `MERGE … ON CREATE SET … ON MATCH SET …` patterns, `coll.distinct()` semantics, list concatenation rules
- [VERIFIED: `requirements.txt`] — `neo4j==5.28.1`, `pydantic>=2.7.0`, `python-dotenv==1.0.1`
- [VERIFIED: `src/graph/neo4j_loader.py`] — current loader pattern, constraint creation loop, label list
- [VERIFIED: `src/graph/schema.py`] — current `EntityNode` / `RelationEdge` dataclass pattern
- [VERIFIED: `src/graph/store.py`] — existing `Neo4jGraphStore` MERGE-by-id behavior (the additive baseline)
- [CITED: `.planning/REQUIREMENTS.md`] — SCHEMA-01..05 verbatim
- [CITED: `.planning/ROADMAP.md`] — Phase 1 success criteria
- [CITED: `CLAUDE.md`] — Neo4j 5.x + Groq + Streamlit constraints

### Secondary (MEDIUM confidence)
- [CITED: neo4j.com/docs/cypher-manual/current/clauses/merge] — official MERGE clause documentation
- [CITED: neo4j.com/docs/cypher-manual/current/functions/list] — `coll.distinct()` reference

### Tertiary (LOW confidence)
- none — all critical claims verified against official docs or in-tree code

## Project Constraints (from CLAUDE.md)

- **Graph backend:** Neo4j 5.x — NOT networkx. networkx only retained for unit tests / offline ops.
- **LLM provider:** Groq with configurable model name in `config/settings.yaml` — out of scope for Phase 1 (no LLM calls in this phase).
- **Demo/prototype quality** — favor clarity over premature optimization (e.g., bulk UNWIND).
- **Additive schema only** — `:Document`, `MENTIONED_IN`, `source_doc`. No renames. No removed kinds. T9 baseline must not regress.
- **GSD Workflow Enforcement** — file changes go through `/gsd-execute-phase` and the standard plan/wave structure.
- **Existing v1.0 patterns to preserve:**
  - `Neo4jGraphStore.setup_constraints()` uniqueness-by-`node_id` — keep; extend for `Document.doc_id`.
  - `neo4j_loader.create_constraints()` label list — append `"Document"`.
  - `_clean_props` helper for serializing nested dicts to JSON strings — reuse, do not reinvent.
  - `--reset` and `--verify` CLI flags on loader — keep; add `--doc-id` flag.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `neo4j==5.28.1` already pinned, no new external deps required for the schema work itself.
- Architecture: HIGH — patterns are textbook MERGE/provenance, verified against Neo4j Cypher Manual via Context7.
- Pitfalls: HIGH — every pitfall is either documented in Cypher Manual or directly observable in the current loader code.
- Open questions: MEDIUM — A1 (`doc_id` form) is the only open question with material plan impact; others are cosmetic or deferrable.

**Research date:** 2026-05-02
**Valid until:** 2026-06-01 (30 days — Neo4j 5.x is stable; `coll.distinct` and MERGE semantics are not on a deprecation track)
