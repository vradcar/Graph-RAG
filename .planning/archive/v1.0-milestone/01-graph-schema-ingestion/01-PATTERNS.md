# Phase 1: Graph Schema & Ingestion — Pattern Map

**Mapped:** 2026-04-15
**Files analyzed:** 9 new/modified files
**Analogs found:** 7 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/graph/schema.py` | model | transform | `src/graph/schema.py` (existing) | exact — extend in place |
| `src/graph/store.py` | service | CRUD | `src/graph/store.py` (existing networkx) | exact — replace implementation, keep interface |
| `src/ingest/pdf_parser.py` | utility | file-I/O | `src/graph/extract.py` (file read pattern) | partial — file-I/O role matches |
| `src/ingest/entity_extractor.py` | service | request-response | `src/graph/extract.py` (transform pattern) | role-match — transform to structured output |
| `src/ingest/normalizer.py` | utility | transform | `src/graph/extract.py` (dict transform loop) | role-match |
| `src/pipeline/ingest.py` | controller | batch | `src/pipeline/ingest.py` (existing CLI) | exact — rewrite body, keep CLI skeleton |
| `src/common/config.py` | config | — | `src/common/config.py` (existing) | exact — extend in place |
| `config/settings.yaml` | config | — | `config/settings.yaml` (existing) | exact — add keys |
| `tests/test_schema.py` | test | — | none | no analog — no tests exist yet |
| `tests/test_neo4j_store.py` | test | — | none | no analog |
| `tests/test_pdf_parser.py` | test | — | none | no analog |
| `tests/test_entity_extractor.py` | test | — | none | no analog |
| `tests/test_ingest_pipeline.py` | test | — | none | no analog |

---

## Pattern Assignments

### `src/graph/schema.py` (model, transform)

**Analog:** `src/graph/schema.py` (existing)
**Action:** Extend in place — add `kind` validation via `__post_init__` and a typed `NODE_KIND` Literal exported from this module so all other files import the enum from one place.

**Existing dataclass pattern** (lines 1-18 — copy this structure exactly):
```python
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class EntityNode:
    node_id: str
    label: str
    kind: str
    properties: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RelationEdge:
    source_id: str
    target_id: str
    relation: str
    properties: Dict[str, Any] = field(default_factory=dict)
```

**Add after the imports** — closed-world enum constants that entity_extractor.py and normalizer.py import from here:
```python
from typing import Literal

NODE_KIND = Literal["Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec"]
ALLOWED_RELATIONS = Literal[
    "COMPATIBLE_WITH", "REPLACES", "SUPPORTS_WIRING", "HAS_SPEC"
]
```

**Add `__post_init__` validation** to catch schema drift before Neo4j write:
```python
# In EntityNode.__post_init__:
VALID_KINDS = {"Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec"}
if self.kind not in VALID_KINDS:
    raise ValueError(f"Invalid node kind '{self.kind}'. Must be one of {VALID_KINDS}")
```

---

### `src/graph/store.py` (service, CRUD)

**Analog:** `src/graph/store.py` (existing networkx version)
**Action:** Replace the networkx implementation with `Neo4jGraphStore` while keeping the same public method signatures (`upsert_node`, `upsert_edge`, `neighbors_multi_hop`, `node_payload`, `has_node`) so `src/pipeline/query.py` needs no changes.

**Existing public interface to preserve** (lines 10-49 — match these signatures exactly):
```python
def upsert_node(self, node_id: str, **attributes) -> None: ...
def upsert_edge(self, source_id: str, target_id: str, relation: str, **attributes) -> None: ...
def neighbors_multi_hop(self, start_node: str, depth: int = 1) -> List[Tuple[str, str, str]]: ...
def node_payload(self, node_id: str) -> Dict: ...
def has_node(self, node_id: str) -> bool: ...
```

**Driver init pattern** — instantiate inside `__init__`, never at module level (anti-pattern: import crash when Neo4j is down):
```python
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
```

**MERGE write pattern** — use `execute_write` with a nested `_tx` function; parameterize ALL values, never f-string node_id (Cypher injection risk):
```python
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
```

**Constraint setup** — call once at ingest startup, idempotent via `IF NOT EXISTS`:
```python
def setup_constraints(self) -> None:
    with self._driver.session() as session:
        for label in ["Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec"]:
            session.run(
                f"CREATE CONSTRAINT {label.lower()}_node_id IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.node_id IS UNIQUE"
            )
```

**Close pattern** — add `close()` and support context manager (`__enter__`/`__exit__`):
```python
def close(self) -> None:
    self._driver.close()

def __enter__(self):
    return self

def __exit__(self, *_):
    self.close()
```

---

### `src/ingest/pdf_parser.py` (utility, file-I/O)

**Analog:** `src/graph/extract.py` (file read pattern)
**Action:** New file. Copy the `Path(path).open()` file-read pattern from extract.py; add pymupdf + pdfplumber dual-extraction.

**File open pattern** from `src/graph/extract.py` lines 6-8:
```python
from pathlib import Path

with Path(path).open("r", encoding="utf-8") as file:
    ...
```

**Core dual-extraction pattern** (returns a list of page dicts; validated by smoke test before LLM pass):
```python
import fitz          # pymupdf
import pdfplumber
from pathlib import Path

def extract_page_content(pdf_path: str) -> list[dict]:
    pages = []
    pdf_mupdf = fitz.open(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, (page_plumber, page_fitz) in enumerate(
            zip(pdf.pages, pdf_mupdf)
        ):
            tables = page_plumber.extract_tables()   # List[List[List[str]]]
            prose = page_fitz.get_text("text")
            pages.append({
                "page_num": page_num + 1,
                "prose": prose,
                "tables": tables,
            })
    return pages
```

**NEVER use** `page.extract_text()` for tables — it fuses columns. Always `extract_tables()` for tabular pages.

---

### `src/ingest/entity_extractor.py` (service, request-response)

**Analog:** `src/graph/extract.py` (transform loop; dict-to-node pattern)
**Action:** New file. The loop structure in extract.py (lines 15-52) shows how to iterate source data and build node/edge dicts — copy that loop skeleton; replace the source iteration with an instructor/Groq call.

**Loop skeleton** from `src/graph/extract.py` lines 15-52:
```python
nodes = []
edges = []
for item in records:
    nodes.append({...})
    edges.append({...})
return {"nodes": nodes, "edges": edges}
```

**Instructor + Groq pattern** — import `NODE_KIND` and `ALLOWED_RELATIONS` from `src/graph/schema.py` (single source of truth):
```python
import os
import instructor
from groq import Groq
from pydantic import BaseModel, Field
from typing import List
from src.graph.schema import NODE_KIND, ALLOWED_RELATIONS

class ExtractedNode(BaseModel):
    node_id: str = Field(description="Stable identifier, e.g. 'RCHT9510WF' or '2-wire-heat-only'")
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

def build_client() -> instructor.Instructor:
    return instructor.from_groq(
        Groq(api_key=os.getenv("GROQ_API_KEY")),
        mode=instructor.Mode.TOOLS
    )

def extract_from_page(client, model: str, page: dict) -> ExtractionResult:
    content = _format_page_content(page)  # prose + stringified tables
    return client.chat.completions.create(
        model=model,
        response_model=ExtractionResult,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]
    )
```

**GROQ_API_KEY loading** — use python-dotenv at CLI entrypoint (not inside this module):
```python
# In src/pipeline/ingest.py, before any imports that use the key:
from dotenv import load_dotenv
load_dotenv()
```

---

### `src/ingest/normalizer.py` (utility, transform)

**Analog:** `src/graph/extract.py` (dict transform, deduplication-by-id logic)
**Action:** New file. The key deduplicate-by-id pattern is visible in extract.py (product_id as dict key). Copy that structure; add lowercasing and alias map.

**Deduplication-by-id pattern** from `src/graph/extract.py` line 16:
```python
product_id = item["product_id"]
# node_id is the canonical key — all merges key on this
```

**Normalization pass** — canonical form used as `node_id` before MERGE:
```python
ALIAS_MAP = {
    "24 VAC": "24VAC",
    "24 V AC": "24VAC",
    # extend as wiring table analysis reveals synonyms
}

def normalize_label(raw: str) -> str:
    normalized = raw.strip().upper().replace("  ", " ")
    return ALIAS_MAP.get(normalized, normalized)

def normalize_node_id(raw: str) -> str:
    """Produces stable, lowercase, hyphenated ID."""
    return raw.strip().lower().replace(" ", "-").replace("/", "-")

def deduplicate_nodes(nodes: list[dict]) -> list[dict]:
    seen = {}
    for node in nodes:
        node_id = node["node_id"]
        if node_id not in seen:
            seen[node_id] = node
    return list(seen.values())
```

---

### `src/pipeline/ingest.py` (controller, batch)

**Analog:** `src/pipeline/ingest.py` (existing — rewrite body, keep CLI skeleton)
**Action:** Keep the argparse + `main()` + `if __name__ == "__main__"` structure exactly; replace the body.

**CLI skeleton to preserve** from `src/pipeline/ingest.py` lines 1-30:
```python
import argparse
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--input", required=True, help="Path to PDF file")
    args = parser.parse_args()
    ...

if __name__ == "__main__":
    main()
```

**output directory creation pattern** from `src/pipeline/ingest.py` lines 20-21:
```python
output_path = Path(args.output)
output_path.parent.mkdir(parents=True, exist_ok=True)
```

**New orchestration body** — layer order enforced: constraints → parse → extract → normalize → write:
```python
from dotenv import load_dotenv
load_dotenv()

from src.common.config import load_settings
from src.graph.store import Neo4jGraphStore
from src.ingest.pdf_parser import extract_page_content
from src.ingest.entity_extractor import build_client, extract_from_page
from src.ingest.normalizer import deduplicate_nodes, normalize_node_id

def main() -> None:
    settings = load_settings()
    store = Neo4jGraphStore(
        uri=settings["graph"]["neo4j_uri"],
        user=settings["graph"]["neo4j_user"],
        password=settings["graph"]["neo4j_password"],
    )
    store.setup_constraints()         # Wave 0 — idempotent
    pages = extract_page_content(args.input)
    client = build_client()
    all_nodes, all_edges = [], []
    for page in pages:
        result = extract_from_page(client, settings["llm"]["model"], page)
        all_nodes.extend([n.model_dump() for n in result.nodes])
        all_edges.extend([e.model_dump() for e in result.edges])
    nodes = deduplicate_nodes(all_nodes)
    for node in nodes:
        store.upsert_node(**node)
    for edge in all_edges:
        store.upsert_edge(**edge)
    store.close()
```

---

### `src/common/config.py` (config, —)

**Analog:** `src/common/config.py` (existing — extend in place)
**Action:** The `load_settings()` function is complete. No changes to the function itself — only `config/settings.yaml` grows new keys that this function will return.

**Existing pattern to preserve** (lines 1-11):
```python
from pathlib import Path
import yaml

def load_settings(path: str = "config/settings.yaml") -> dict:
    settings_path = Path(path)
    if not settings_path.exists():
        raise FileNotFoundError(f"Settings file not found: {settings_path}")
    with settings_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}
```

**Callers access new keys as:**
```python
settings["graph"]["neo4j_uri"]
settings["graph"]["neo4j_user"]
settings["graph"]["neo4j_password"]  # read from env via os.getenv fallback in caller
settings["llm"]["model"]
settings["llm"]["provider"]
```

---

### `config/settings.yaml` (config, —)

**Analog:** `config/settings.yaml` (existing — add keys)
**Action:** Add `neo4j_*` keys under `graph:` and new `llm:` section. Keep all existing keys unchanged.

**Existing keys to preserve** (lines 1-16 — do not remove):
```yaml
project:
  name: GraphRAG-POC
  domain: product_compatibility

graph:
  backend: networkx
  max_default_depth: 2

retrieval:
  mode: hybrid
  top_k_chunks: 5
```

**Add under `graph:`**:
```yaml
graph:
  backend: neo4j          # changed from networkx
  max_default_depth: 2
  neo4j_uri: bolt://localhost:7687
  neo4j_user: neo4j
  neo4j_password: "${NEO4J_PASSWORD}"   # loaded from .env
```

**Add new top-level section:**
```yaml
llm:
  provider: groq
  model: llama-3.1-8b-instant
```

---

## Shared Patterns

### Environment variable loading
**Source:** `src/pipeline/ingest.py` (new) + `.env`
**Apply to:** `src/pipeline/ingest.py` only (CLI entrypoint); never inside service/utility modules
```python
from dotenv import load_dotenv
load_dotenv()  # loads .env before any os.getenv() calls
```

### Settings consumption
**Source:** `src/common/config.py` lines 1-11
**Apply to:** `src/pipeline/ingest.py`, any future CLI entrypoints
```python
from src.common.config import load_settings
settings = load_settings()
```

### Path construction
**Source:** `src/pipeline/ingest.py` lines 20-21, `src/graph/extract.py` lines 6-8
**Apply to:** `src/ingest/pdf_parser.py`, `src/pipeline/ingest.py`
```python
from pathlib import Path
output_path = Path(args.output)
output_path.parent.mkdir(parents=True, exist_ok=True)
```

### Node/edge dict shape
**Source:** `src/graph/extract.py` lines 18-50
**Apply to:** `src/ingest/entity_extractor.py`, `src/ingest/normalizer.py`
```python
# Node dict keys must match EntityNode fields
{"node_id": str, "label": str, "kind": str, "properties": dict}

# Edge dict keys must match RelationEdge fields
{"source_id": str, "target_id": str, "relation": str, "properties": dict}
```

### Neo4j MERGE — parameterization rule
**Source:** Research Pattern 1
**Apply to:** `src/graph/store.py` (Neo4jGraphStore) exclusively
Never interpolate user-derived strings into Cypher directly. Only `kind` (validated against enum) and `relation` (validated Literal) may appear in f-strings. All `node_id` values go through `$node_id` parameter binding.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/test_schema.py` | test | — | No tests exist in the project |
| `tests/test_neo4j_store.py` | test | — | No tests exist in the project |
| `tests/test_pdf_parser.py` | test | — | No tests exist in the project |
| `tests/test_entity_extractor.py` | test | — | No tests exist in the project |
| `tests/test_ingest_pipeline.py` | test | — | No tests exist in the project |
| `src/ingest/__init__.py` | config | — | New package; empty file |

For test files, use standard pytest patterns: one test function per requirement ID, `pytest.fixture` for shared setup, `unittest.mock.patch` or `pytest-mock` to mock Groq API calls.

---

## Metadata

**Analog search scope:** `src/graph/`, `src/pipeline/`, `src/common/`, `config/`, `tests/`
**Files scanned:** 6 source files (schema.py, store.py, extract.py, ingest.py, query.py, config.py, settings.yaml)
**Pattern extraction date:** 2026-04-15
