# Phase 1: Graph Schema & Ingestion — Research

**Researched:** 2026-04-15
**Domain:** Neo4j graph schema design, PDF extraction (pymupdf + pdfplumber), LLM-based entity extraction (Groq + instructor + Pydantic), idempotent ingestion
**Confidence:** HIGH (stack verified against PyPI registry; driver patterns verified via Context7)

---

## Summary

Phase 1 converts a single PDF (`data/raw/t9-thermostat.pdf`) into a populated Neo4j graph with five node types and four edge types. The existing codebase has a networkx-backed `GraphStore`, JSON-based extraction, and a CLI ingest entry point — all three must be replaced or substantially rewritten. No new architectural invention is required: the patterns are well-established and all libraries are available on PyPI.

The dominant risk is upstream of Neo4j entirely: if PDF table extraction is handled with plain text extraction, wiring configurations and compatibility tables will be garbled before the LLM ever sees them. The second risk is schema drift — the LLM inventing relationship synonyms or node variants that fragment the graph. Both risks have well-understood mitigations that must be locked into the design before any code is written.

The neo4j Python driver has a significant version discontinuity: `requirements.txt` pins `5.28.1` but the current release is `6.1.0`. Driver 6.x docs are now the authoritative reference; the pinned version must be decided before implementation begins. All other libraries need installation from scratch (pymupdf, pdfplumber, groq are not present in the project environment).

**Primary recommendation:** Build in strict layer order — (1) schema + Neo4j adapter with idempotency tests, (2) PDF parser with visual validation of extracted text, (3) LLM extractor with closed-world enum enforcement, (4) wiring into the ingest CLI. Do not proceed to the next layer until the current one has a passing smoke test.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GRAPH-01 | Product nodes: model number, name, description, status | EntityNode dataclass already exists; needs `kind="Product"` and standard properties enforced in normalization |
| GRAPH-02 | Accessory nodes + COMPATIBLE_WITH edges | Supported by existing RelationEdge; Neo4j MERGE pattern covers idempotency |
| GRAPH-03 | WiringConfig nodes + SUPPORTS_WIRING edges | Must be nodes, not properties — see Pitfall 7; pdfplumber table extraction required |
| GRAPH-04 | HVACSystemType nodes + COMPATIBLE_WITH edges | Same node-not-property principle; extracted from prose sections of PDF |
| GRAPH-05 | Spec nodes + HAS_SPEC edges | Spec values (voltage, dimensions) must be normalized before MERGE to avoid duplicates |
| GRAPH-06 | REPLACES edges between Products | Source/target both must be Product nodes; validate after ingest |
| GRAPH-07 | All writes use MERGE + uniqueness constraints | Constraint creation (Wave 0) must precede any ingest run; MERGE keys on node_id |
| INGEST-01 | Extract text from PDF using pymupdf | PyMuPDF 1.27.2.2 on PyPI; not yet installed in project env |
| INGEST-02 | Extract tables from PDF using pdfplumber | pdfplumber 0.11.9 on PyPI; use page.extract_tables() not page.extract_text() for wiring/compat tables |
| INGEST-03 | Groq + instructor + Pydantic structured extraction | Verified pattern: instructor.from_groq(client, mode=instructor.Mode.TOOLS) + Pydantic BaseModel |
| INGEST-04 | Closed-world relationship enum in extraction prompt | Enum must be in the Pydantic model as a Literal type — not just in the prompt string |
| INGEST-05 | Normalize/deduplicate before Neo4j write | Normalization pass: lowercase + strip + alias map; MERGE keyed on canonical node_id |
| INGEST-06 | Idempotent ingestion — no duplicates on re-run | MERGE everywhere; uniqueness constraint on node_id per label; test by running ingest twice |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| PDF text extraction | Ingestion (CLI) | — | Offline batch process; no request/response cycle |
| PDF table extraction | Ingestion (CLI) | — | pdfplumber handles table structure; pymupdf handles prose |
| LLM entity extraction | Ingestion (CLI) | Groq API | LLM call is outbound from the ingestion process |
| Entity normalization | Ingestion (CLI) | — | Pure Python transform between extraction and write |
| Graph schema definition | Schema layer (src/graph/schema.py) | — | Canonical dataclasses; consumed by both ingestion and query |
| Neo4j writes (MERGE) | Graph store (src/graph/store.py) | Neo4j DB | Adapter pattern isolates driver calls |
| Uniqueness constraints | Neo4j DB | Graph store | Must be created once via Cypher before first ingest |
| Idempotency guarantee | Both: MERGE in code + constraint in DB | — | Defense in depth: constraint catches any MERGE miss |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `PyMuPDF` (import: `fitz`) | 1.27.2.2 | Extract text from PDF pages | Fastest pure-Python PDF library; superior layout handling for multi-column technical docs |
| `pdfplumber` | 0.11.9 | Extract structured tables from PDF | `page.extract_tables()` returns cell-by-cell data; prevents column-fusion bug |
| `groq` | 1.1.2 | LLM API client | Project constraint; fast inference |
| `instructor` | 1.15.1 (latest) | Structured LLM output via Pydantic | Wraps Groq with Pydantic model enforcement; already installed at 1.14.5 |
| `pydantic` | 2.12.5 (already installed) | Schema validation for extracted entities | Required by instructor; validates before Neo4j write |
| `neo4j` | 5.28.1 (pinned) or 6.1.0 | Neo4j driver | **See version note below** |

**Neo4j driver version decision required:** `requirements.txt` pins `5.28.1`. Current PyPI latest is `6.1.0` (major bump). The 6.x driver docs are now standard. Recommend upgrading to `5.28.3` (latest 5.x patch) or `6.1.0` (latest) — do not stay on 5.28.1 which has known bugs fixed in .2/.3. [VERIFIED: PyPI registry, 2026-04-15]

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `networkx` | 3.4.2 (already installed) | Keep for unit tests without Neo4j | Offline graph logic tests; keep in dev path |
| `pytest` | 9.0.2 (already installed) | Unit and integration tests | All smoke tests for schema, adapter, extraction |
| `python-dotenv` | 1.0.1 (already installed) | Load `.env` for Neo4j credentials | Always — GROQ_API_KEY, NEO4J_URI, NEO4J_PASSWORD |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pymupdf for text | pypdf | pypdf has weaker layout handling for technical installation guides |
| pdfplumber for tables | camelot-py | camelot requires Ghostscript; pdfplumber is zero-dependency |
| instructor for structured output | raw JSON prompt + json.loads() | Manual parsing is fragile; instructor handles retries, validation, fence-stripping |
| MERGE idempotency | CREATE + pre-check | Pre-check is a race condition; MERGE is atomic |

**Installation (new packages only):**
```bash
pip install PyMuPDF==1.27.2.2
pip install pdfplumber==0.11.9
pip install groq==1.1.2
pip install instructor==1.15.1
# pydantic already installed at 2.12.5
# neo4j — upgrade requirements.txt from 5.28.1 to 5.28.3
```

---

## Architecture Patterns

### System Architecture Diagram

```
data/raw/t9-thermostat.pdf
        |
        v
 [PDF Parser]
 ├── pymupdf: page.get_text() → prose text per page
 └── pdfplumber: page.extract_tables() → cell arrays for wiring/compat tables
        |
        v
 [Section Chunker]
 Combine prose + table cells into labelled chunks
 (page N context passed with each chunk to preserve cross-reference)
        |
        v
 [LLM Entity Extractor]
 instructor.from_groq(client, mode=TOOLS)
 Pydantic model enforces: node kinds enum + relation types Literal
        |
        v
 [Normalization Pass]
 lowercase labels, alias map (24VAC → 24VAC), strip punctuation
 deduplicate nodes by canonical node_id
        |
        v
 [Neo4j Adapter — Neo4jGraphStore]
 MERGE (n:Product {node_id: $id}) SET n += $props
 MERGE (a)-[:COMPATIBLE_WITH]->(b)
        |
        v
 Neo4j (Docker, localhost:7474 / bolt:7687)
 Uniqueness constraints pre-created on node_id per label
```

### Recommended Project Structure

```
src/
├── graph/
│   ├── schema.py          # EntityNode, RelationEdge (extend — add validation)
│   ├── store.py           # REPLACE: Neo4jGraphStore replacing networkx GraphStore
│   └── extract.py         # KEEP stub; new PDF extraction goes elsewhere
├── ingest/                # NEW directory
│   ├── __init__.py
│   ├── pdf_parser.py      # pymupdf text + pdfplumber table extraction
│   ├── entity_extractor.py  # Groq + instructor extraction with Pydantic models
│   └── normalizer.py      # entity/label normalization before Neo4j write
├── pipeline/
│   └── ingest.py          # REWRITE: PDF → Neo4j instead of JSON → file
└── common/
    └── config.py          # extend: add Neo4j URI + Groq model reading
config/
└── settings.yaml          # add: graph.backend=neo4j, llm.model, Neo4j defaults
data/
└── raw/
    └── t9-thermostat.pdf  # source document [VERIFIED: file exists]
```

### Pattern 1: Neo4j Adapter with MERGE

**What:** `Neo4jGraphStore` implementing the same interface as the existing `GraphStore` (upsert_node, upsert_edge, neighbors_multi_hop). Switched via `config.graph.backend`.

**When to use:** All Neo4j writes in this phase.

```python
# Source: Context7 /neo4j/neo4j-python-driver — execute_write pattern
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        try:
            self._driver.verify_connectivity()
        except ServiceUnavailable as e:
            raise RuntimeError(
                f"Neo4j not reachable at {uri}. "
                "Start with: docker run -p 7474:7474 -p 7687:7687 "
                "-e NEO4J_AUTH=neo4j/password neo4j:5"
            ) from e

    def upsert_node(self, node_id: str, kind: str, **props) -> None:
        def _tx(tx):
            tx.run(
                f"MERGE (n:{kind} {{node_id: $node_id}}) SET n += $props",
                node_id=node_id, props=props
            )
        with self._driver.session() as session:
            session.execute_write(_tx)

    def upsert_edge(self, source_id: str, target_id: str, relation: str, **props) -> None:
        def _tx(tx):
            tx.run(
                f"MATCH (a {{node_id: $src}}), (b {{node_id: $tgt}}) "
                f"MERGE (a)-[r:{relation}]->(b) SET r += $props",
                src=source_id, tgt=target_id, props=props
            )
        with self._driver.session() as session:
            session.execute_write(_tx)

    def close(self) -> None:
        self._driver.close()
```

### Pattern 2: Instructor + Groq Structured Extraction

**What:** Pydantic model with Literal types for node kinds and relationship types enforces closed-world enum at extraction time.

**When to use:** All LLM entity extraction (INGEST-03, INGEST-04).

```python
# Source: Context7 /instructor-ai/instructor — Groq structured output
import instructor
from groq import Groq
from pydantic import BaseModel, Field
from typing import Literal, List, Optional

ALLOWED_RELATIONS = Literal[
    "COMPATIBLE_WITH", "REPLACES", "SUPPORTS_WIRING", "HAS_SPEC"
]
NODE_KIND = Literal["Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec"]

class ExtractedNode(BaseModel):
    node_id: str = Field(description="Stable identifier, e.g. RCHT9510WF or '2-wire-heat-only'")
    label: str
    kind: NODE_KIND
    properties: dict = Field(default_factory=dict)

class ExtractedEdge(BaseModel):
    source_id: str
    target_id: str
    relation: ALLOWED_RELATIONS

class ExtractionResult(BaseModel):
    nodes: List[ExtractedNode]
    edges: List[ExtractedEdge]

client = instructor.from_groq(
    Groq(api_key=os.getenv("GROQ_API_KEY")),
    mode=instructor.Mode.TOOLS
)

result: ExtractionResult = client.chat.completions.create(
    model=settings["llm"]["model"],
    response_model=ExtractionResult,
    messages=[
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": page_text}
    ]
)
```

### Pattern 3: Uniqueness Constraints (Wave 0 setup)

**What:** Create Neo4j uniqueness constraints on `node_id` for each label before first ingest. This is the DB-level guarantee backing MERGE idempotency (GRAPH-07).

**When to use:** Once, as a setup Cypher script or in a `setup_constraints()` method called at ingest startup.

```cypher
-- Source: Neo4j documentation — uniqueness constraints
CREATE CONSTRAINT product_node_id IF NOT EXISTS
  FOR (n:Product) REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT accessory_node_id IF NOT EXISTS
  FOR (n:Accessory) REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT wiring_node_id IF NOT EXISTS
  FOR (n:WiringConfig) REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT hvac_node_id IF NOT EXISTS
  FOR (n:HVACSystemType) REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT spec_node_id IF NOT EXISTS
  FOR (n:Spec) REQUIRE n.node_id IS UNIQUE;
```

### Pattern 4: pdfplumber Table Extraction

**What:** Use `page.extract_tables()` for structured tabular data (wiring configs, compatibility matrices). Use pymupdf `page.get_text()` for prose sections.

**When to use:** Any page containing wiring terminal tables or compatibility grids (INGEST-01, INGEST-02).

```python
# Source: pdfplumber documentation
import pdfplumber
import fitz  # pymupdf

def extract_page_content(pdf_path: str) -> list[dict]:
    pages = []
    pdf_mupdf = fitz.open(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, (page_plumber, page_fitz) in enumerate(
            zip(pdf.pages, pdf_mupdf)
        ):
            tables = page_plumber.extract_tables()
            prose = page_fitz.get_text("text")
            pages.append({
                "page_num": page_num + 1,
                "prose": prose,
                "tables": tables,  # List[List[List[str]]] — rows × cols
            })
    return pages
```

### Anti-Patterns to Avoid

- **Using `page.extract_text()` for wiring tables:** Returns fused column data. Use `extract_tables()` exclusively for tabular pages.
- **Storing WiringConfig as a Product property:** Breaks traversal queries. WiringConfig must be a first-class node.
- **`CREATE` instead of `MERGE`:** Will duplicate nodes on re-run. Every write must be MERGE keyed on node_id.
- **LLM relation type as free string:** Allows synonym explosion. Enforce via Pydantic `Literal` type, not just prompt instruction.
- **Instantiating Neo4j driver at module import time:** Causes import crash when Neo4j is not running. Instantiate inside `__init__` with explicit error message.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured LLM output | Custom JSON-fence stripping + retry loop | `instructor` | Handles retries, validation, fence removal, partial-JSON detection |
| PDF table parsing | Custom heuristic column detection | `pdfplumber.extract_tables()` | pdfplumber uses layout-aware algorithms; hand-rolled heuristics fail on merged cells |
| Neo4j MERGE idempotency | Application-level "check before insert" | Cypher MERGE + DB uniqueness constraint | MERGE is atomic; check-then-create has TOCTOU race |
| Entity deduplication | Fuzzy string matching library | Normalization alias map + MERGE | For a single-product graph, explicit alias map is simpler and more predictable than fuzzy match |

---

## Common Pitfalls

### Pitfall 1: PDF Table Column Fusion
**What goes wrong:** `page.extract_text()` on a wiring table reads across columns, producing "R C G Y1 24VAC Common Fan" as a single string.
**Why it happens:** PDF has no table object model; text is positioned absolutely.
**How to avoid:** Use `pdfplumber.page.extract_tables()` for pages containing tables. Validate raw output visually before LLM pass.
**Warning signs:** Extracted text has long runs of terminal codes without structure.

### Pitfall 2: Relationship Type Sprawl
**What goes wrong:** LLM invents `WORKS_WITH`, `IS_COMPATIBLE_WITH`, `CAN_USE` — all distinct in Neo4j.
**How to avoid:** Use a Pydantic `Literal` type for the `relation` field in `ExtractedEdge`. The Literal type causes instructor to retry if the LLM returns an invalid value.
**Warning signs:** `CALL db.relationshipTypes()` returns > 6 types.

### Pitfall 3: Schema-Less Node Explosion
**What goes wrong:** "24VAC", "24 VAC", "24V AC" become three separate Spec nodes.
**How to avoid:** Normalization pass before Neo4j write: `label.upper().strip().replace(" ", "")` + known alias map.
**Warning signs:** Node count > 200 for a single-product PDF.

### Pitfall 4: WiringConfig as Property
**What goes wrong:** Wiring stored as `Product.wiring_config = "2-wire"`. Query "which products support 2-wire?" requires string search, not graph traversal.
**How to avoid:** WiringConfig is a node. `(:Product)-[:SUPPORTS_WIRING]->(:WiringConfig {node_id: "2-wire-heat-only"})`.

### Pitfall 5: Neo4j Version Mismatch
**What goes wrong:** `requirements.txt` pins `neo4j==5.28.1`. The driver 6.x has breaking changes in session management. Running `pip install -r requirements.txt` gets 5.28.1 while Context7 docs describe 6.x API.
**How to avoid:** Pin an explicit version at the start of the phase. Recommend: upgrade to `5.28.3` (latest 5.x, no breaking changes) or commit to `6.1.0` after reading the migration guide.

### Pitfall 6: No Graph Integrity Validation
**What goes wrong:** Ingestion completes but REPLACES edges point to non-existent nodes. Traversal silently returns empty results.
**How to avoid:** Run validation Cypher after every ingest:
```cypher
MATCH (p:Product)-[:REPLACES]->(q)
WHERE NOT (q:Product) RETURN q.node_id
```
Fail the pipeline if this returns any rows.

---

## Code Examples

### Setting up constraints (idempotent)
```python
# Source: Neo4j Cypher documentation — IF NOT EXISTS guard
def setup_constraints(driver):
    with driver.session() as session:
        for label in ["Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec"]:
            session.run(
                f"CREATE CONSTRAINT {label.lower()}_node_id IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.node_id IS UNIQUE"
            )
```

### Smoke test (GRAPH-07 verification)
```python
# After ingest, verify idempotency:
# 1. Run ingest
# 2. Count nodes: MATCH (n) RETURN labels(n)[0], count(*) as cnt
# 3. Run ingest again
# 4. Assert counts are unchanged
def count_nodes(session) -> dict:
    result = session.run("MATCH (n) RETURN labels(n)[0] as label, count(*) as cnt")
    return {record["label"]: record["cnt"] for record in result}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `groq` 0.9.x | `groq` 1.1.2 | 2025 (1.0 release) | Major version bump; API surface compatible but verify |
| `instructor` 1.4.x | `instructor` 1.15.1 | Incremental 2025 | `instructor.from_groq()` still valid; `from_provider()` also available |
| `neo4j` 5.x | `neo4j` 6.1.0 | 2025 | Driver 6.x has changes; stay on 5.28.3 unless migration tested |
| networkx GraphStore | Neo4jGraphStore | This phase | Replaces in-memory store; keep networkx for unit tests |

**Deprecated/outdated in this codebase:**
- `src/graph/extract.py` `product_records_to_graph_items()`: JSON-only, no PDF support — REPLACE with `src/ingest/entity_extractor.py`
- `src/pipeline/ingest.py` current implementation: reads JSON file, writes to file — REWRITE for PDF → Neo4j
- `config/settings.yaml` `graph.backend: networkx`: must change to `neo4j` — add `llm.model` and `llm.provider` keys

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | All | ✓ | 3.13.1 | — |
| Docker | Neo4j container | ✓ | 28.3.3 | — |
| Neo4j container | GRAPH-07, all writes | ✗ (not running) | — | Must start before ingest |
| PyMuPDF | INGEST-01 | ✗ (not installed) | — | Must install; no fallback |
| pdfplumber | INGEST-02 | ✗ (not installed) | — | Must install; no fallback |
| groq SDK | INGEST-03 | ✗ (not installed) | — | Must install; no fallback |
| instructor | INGEST-03 | ✓ (1.14.5) | 1.14.5 | — |
| pydantic | INGEST-03 | ✓ (2.12.5) | 2.12.5 | — |
| pytest | Testing | ✓ (9.0.2) | 9.0.2 | — |
| neo4j driver | All Neo4j ops | ✗ (not installed in env) | pinned 5.28.1 in requirements.txt | — |
| GROQ_API_KEY | INGEST-03 | Unknown | — | Cannot run extraction without it |

**Missing dependencies with no fallback:**
- Neo4j Docker container (must be started before ingest): `docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5`
- PyMuPDF: `pip install PyMuPDF==1.27.2.2`
- pdfplumber: `pip install pdfplumber==0.11.9`
- groq SDK: `pip install groq==1.1.2`
- neo4j driver: `pip install neo4j==5.28.3` (or upgrade requirements.txt)
- GROQ_API_KEY: must be set in `.env` before extraction runs

**Missing dependencies with fallback:**
- None in Phase 1 scope (all are hard requirements)

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none — see Wave 0 |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GRAPH-07 | MERGE produces no duplicates on second run | integration | `pytest tests/test_neo4j_store.py::test_idempotent_ingest -x` | ❌ Wave 0 |
| GRAPH-01 | Product node has required properties | unit | `pytest tests/test_schema.py::test_product_node_properties -x` | ❌ Wave 0 |
| INGEST-04 | Relation not in enum is rejected | unit | `pytest tests/test_entity_extractor.py::test_closed_world_enum -x` | ❌ Wave 0 |
| INGEST-06 | Re-running ingest: node count unchanged | integration | `pytest tests/test_ingest_pipeline.py::test_double_run_idempotency -x` | ❌ Wave 0 |
| INGEST-02 | Table extraction returns cell structure not fused text | unit | `pytest tests/test_pdf_parser.py::test_table_not_fused -x` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/test_schema.py` — covers GRAPH-01 through GRAPH-06 property validation
- [ ] `tests/test_neo4j_store.py` — covers GRAPH-07 MERGE idempotency (requires Neo4j or testcontainers)
- [ ] `tests/test_pdf_parser.py` — covers INGEST-01, INGEST-02
- [ ] `tests/test_entity_extractor.py` — covers INGEST-03, INGEST-04 (can mock Groq)
- [ ] `tests/test_ingest_pipeline.py` — covers INGEST-05, INGEST-06 end-to-end

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes (extraction output) | Pydantic model validation before Neo4j write |
| V6 Cryptography | no | — |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cypher injection via extracted entity labels | Tampering | Parameterized Cypher: `MERGE (n:Product {node_id: $id})` — never f-string node_id |
| API key exposure in logs | Information Disclosure | Load from `.env` via python-dotenv; never log the key value |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | T9 PDF contains wiring compatibility tables that need `extract_tables()` | Common Pitfalls / Standard Stack | If the PDF has no tables, pdfplumber adds overhead but no harm |
| A2 | Groq llama-3 models available in 2026 accept `instructor.Mode.TOOLS` | Code Examples | If model was deprecated, need to select different model and verify TOOLS mode support |
| A3 | neo4j driver 5.28.3 is fully compatible with 5.28.1 (no breaking changes) | Standard Stack | Patch version bump should be safe; verify CHANGELOG before upgrade |
| A4 | GROQ_API_KEY is available to the developer | Environment Availability | Without the key, INGEST-03 cannot be tested; mocking required for CI |

---

## Open Questions (RESOLVED)

1. **Neo4j driver version: stay on 5.28.x or upgrade to 6.1.0?** — RESOLVED: Pinned neo4j==5.28.3 (safe patch bump) in requirements.txt. 6.x evaluation deferred.

2. **Does the T9 PDF have extractable tables, or is wiring data in prose/images?** — RESOLVED: Accepted risk. Plan 01-03 tests use `pytest.skip` if no tables found — pipeline degrades gracefully to prose-only extraction.

3. **Is GROQ_API_KEY available, and which model should be the default?** — RESOLVED: Plan 01-01 adds GROQ_API_KEY to .env.example. Default model set to llama-3.1-8b-instant in settings.yaml, configurable.

---

## Sources

### Primary (HIGH confidence)
- PyPI registry (`pip3 index versions`) — all library versions verified 2026-04-15 [VERIFIED]
- Context7 `/neo4j/neo4j-python-driver` — `execute_write`, `verify_connectivity`, constraint creation patterns [VERIFIED]
- Context7 `/instructor-ai/instructor` — Groq structured output with `from_groq()` + Pydantic model [VERIFIED]
- Existing codebase: `src/graph/schema.py`, `src/graph/store.py`, `src/pipeline/ingest.py`, `config/settings.yaml`, `requirements.txt` [VERIFIED]

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` — library selection rationale (training data, mid-2025) [CITED]
- `.planning/research/PITFALLS.md` — domain-specific pitfalls (training data + codebase inspection) [CITED]
- `.planning/research/ARCHITECTURE.md` — component boundaries and build order [CITED]

### Tertiary (LOW confidence — flag for validation)
- Groq model name `llama-3.1-8b-instant` as default: verify current availability at console.groq.com [ASSUMED]

---

## Metadata

**Confidence breakdown:**
- Standard stack versions: HIGH — verified against PyPI registry 2026-04-15
- Neo4j MERGE + constraint pattern: HIGH — verified via Context7 official driver docs
- instructor + Groq integration pattern: HIGH — verified via Context7 official instructor docs
- PDF table extraction strategy: MEDIUM — based on pdfplumber docs + pitfalls research; requires PDF-specific validation in Wave 0
- Groq model name default: LOW — model availability changes; verify before committing

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (30 days; library versions may change, Groq model roster changes frequently)
