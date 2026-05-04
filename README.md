# Honeywell GraphRAG — Milestone v2.0 (T1-Sai)

A Graph-based Retrieval-Augmented Generation prototype for Honeywell's HVAC product documentation. It extracts entities and relationships from product PDFs into a Neo4j knowledge graph, then answers cross-document questions by traversing the graph and generating cited, structured answers via Groq.

**Branch:** `topic/t1-sai` · **Track:** T1 (ingestion + multi-doc verification) · **Reviewer goal:** decide whether this milestone is ready to merge.

---

## TL;DR for reviewers

1. **What was promised (v2.0 goal):** harden the ingestion pipeline so it handles multiple Honeywell HVAC PDFs, with per-document provenance, cross-document edges, and a verifiable graph-vs-vector advantage.
2. **What was delivered:** all 4 phases (13 plans) closed; 4 PDFs ingested into Neo4j with full provenance; 7 curated cross-doc queries with 3 documented graph-only wins; demo Streamlit UI; full pipeline (graph → LLM understanding → vector fallback → answer) wired into the Ask tab.
3. **Out of scope (other tracks):** evaluation framework polish (T2), demo UX (T3), deployment (T4), report (T5). The integration mindset means T1 code is structured for those tracks to consume — see "Integration surface" below.
4. **Final graph state visualized:** see `data/eval/neo4j-final-graph-1.png`, `data/eval/neo4j-final-graph-2.png`.

---

## Milestone scope

**Goal (from `.planning/PROJECT.md`):** prove GraphRAG's multi-document advantage over flat RAG by building a hardened ingestion pipeline across 4 Honeywell HVAC PDFs.

**Constraints carried from v1.0:**
- Graph backend: **Neo4j 5.x** (not networkx).
- LLM provider: **Groq** (with OpenAI/OpenRouter fallback hooks).
- Single configurable model placeholder (`config/settings.yaml`).
- Demo/prototype quality, not production.

**Corpus:**

| doc_id | Title | SKU(s) |
|---|---|---|
| `t9_install_guide` | T9 Smart Thermostat Installation Guide | T9 / RCHT9510WF |
| `t6_pro_install` | T6 Pro Programmable Thermostat Installation Guide | TH6320U2008, TH6220U2000, TH6210U2001 |
| `thp9045_wiring_module` | THP9045 C-Wire Adapter Wiring Module | THP9045A1023 |
| `t10_pro_user_guide` | T10 Pro Smart Thermostat User Guide | THX321WFS3001W |

---

## Phases (all complete)

| Phase | Outcome | Plans |
|---|---|---|
| **1 — Schema & Provenance Foundation** | `:Document` node + `MENTIONED_IN` relation + `source_doc` on every edge. Same fact from two PDFs creates two parallel evidence-bearing edges; a node mentioned in N PDFs has `source_docs[]` length N. | 3 |
| **2 — Corpus Curation & Extractor Hardening** | 3 new PDFs onboarded with manifest. `pdf_parser`, `entity_extractor`, `normalizer` hardened (page filter, footnote stripping, ValidationError logging, multi-SKU prompt, normalizer alias map for UWP / THX9321R / terminals / system types). T9 baseline non-regression verified. | 5 |
| **3 — Batch Ingestion Tooling** | `scripts/batch_ingest.py` runs end-to-end with `--dry-run`, per-doc JSON reports in `reports/batch/`, structured failure log at `reports/ingest_failures.log`, scoped delete by `source_doc` for idempotent re-runs. | 3 |
| **4 — Multi-Document Quality Verification** | 7 curated cross-doc queries in `data/eval/multi_doc_queries.json`. Comparison artifact at `data/eval/multi_doc_comparison.md` shows graph wins or ties on every query, with **3 documented graph-only wins** (mq01, mq02, mq05). | 2 |

Detailed plan-level artifacts live under `.planning/phases/`.

---

## How the pipeline works

```
data/raw/*.pdf
  → src/ingest/pdf_parser.py        (page filter, footnote strip)
  → src/ingest/entity_extractor.py  (Groq + instructor + ValidationError logging)
  → src/ingest/normalizer.py        (SKU regex + alias map)
  → src/graph/neo4j_loader.py       (provenance-aware MERGE on (src,tgt,relation,source_doc))
  → Neo4j (with :Document, MENTIONED_IN, source_doc on every edge)
```

Query path (`src/pipeline/query.py:run_query_structured`) — used by both CLI and Streamlit — runs the **4-stage retrieval pipeline** added during this milestone:

1. **Fast path** — `graph_retrieve()` regex SKU detection + replacement-keyword Cypher.
2. **LLM query understanding** — Groq + `instructor` extracts entities/intent/search_terms; `resolve_entities_against_graph()` does case-insensitive substring matching against actual Neo4j node IDs; multi-hop traversal from each.
3. **Vector fallback** — `SimpleVectorStore` built lazily from all Neo4j nodes; pulls 1-hop neighbors of top-K hits.
4. **LLM answer generation** — `generate_answer()` returns a Pydantic-validated `QueryAnswer` with prose, evidence triples (`source --[relation]--> target`), and `pipeline_stage` indicating which stage produced the triples.

The Streamlit UI surfaces `pipeline_stage` as a colored banner (🟢 fast / 🟡 LLM / 🟠 vector / ⚪ none) so a reviewer can verify each stage actually fires.

---

## Final graph (visualisations)

Snapshots after the full corpus load are checked in at:

- `data/eval/neo4j-final-graph-1.png`
- `data/eval/neo4j-final-graph-2.png`

These show the cross-document bridges (UWP-wallplate, C-wire, terminal-W, heat-pump) connecting the 4 product subgraphs.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
pip install -r requirements.txt
cp .env.example .env               # then fill in keys (see below)

# Start Neo4j (Docker)
docker run -d --name graphrag-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5
```

Required `.env` keys:
- `NEO4J_PASSWORD` — must match the `NEO4J_AUTH` value in the Docker command.
- `GROQ_API_KEY` — used for entity extraction *and* query understanding/answer generation.
- *(Optional)* `OPENAI_API_KEY`, `OPENROUTER_API_KEY` — alternate providers.

`NEO4J_URI` and `NEO4J_USERNAME` are read from `config/settings.yaml`.

---

## Running the milestone end-to-end

```bash
# 1) Ingest the full corpus into Neo4j
python scripts/batch_ingest.py            # writes per-doc reports to reports/batch/
# (use --dry-run first to verify extraction without touching Neo4j)

# 2) Run the curated multi-doc query set + graph-vs-vector comparison
python scripts/compare_graph_vs_vector.py
# regenerates data/eval/multi_doc_results.json + multi_doc_comparison.md

# 3) Ad-hoc CLI query
python -m src.pipeline.query \
  --question "What HVAC system types does the UWP-WALLPLATE support across the T9 and T6-PRO thermostat guides?" \
  --depth 2

# 4) Streamlit demo
streamlit run app.py
# Opens http://localhost:8501 with 4 tabs: Ask · Multi-Doc Queries · Graph vs Vector · Corpus
```

---

## Verifying the milestone goals

| Success criterion | How to verify |
|---|---|
| Provenance on every edge | `MATCH ()-[r]->() WHERE type(r) <> 'MENTIONED_IN' AND r.source_doc IS NULL RETURN count(r)` → `0` |
| Cross-doc edges exist | `MATCH (n)-[r]-() RETURN n.node_id, count(DISTINCT r.source_doc) AS docs ORDER BY docs DESC` → top entries (UWP-wallplate, C-wire, terminal-W) span ≥3 docs |
| T9 non-regression | Phase 2 fixture in `tests/` (run `pytest tests/`) |
| Idempotent re-ingest | Run `batch_ingest.py` twice; node/edge counts identical |
| Graph beats flat RAG | `data/eval/multi_doc_comparison.md` — verdict column = `graph` or `tie` for all 7 queries; 3 graph-only wins |
| Multi-doc queries cite source PDFs | Streamlit "Graph Evidence" expander shows `[source_doc]` badge per triple |

---

## What's in here

```
.
├── app.py                          # Streamlit demo (4 tabs)
├── config/settings.yaml            # Graph + LLM config
├── data/
│   ├── raw/                        # 4 PDFs + manifest.json
│   ├── processed/                  # Per-doc extracted JSON corpora
│   └── eval/
│       ├── multi_doc_queries.json  # 7 curated cross-doc questions
│       ├── multi_doc_comparison.md # Graph-vs-vector verdict table
│       ├── multi_doc_results.json  # Raw comparison output
│       ├── neo4j-final-graph-1.png # Final graph visualisation
│       └── neo4j-final-graph-2.png
├── scripts/
│   ├── batch_ingest.py             # Phase 3 batch ingestion CLI
│   ├── compare_graph_vs_vector.py  # Phase 4 comparison runner
│   └── demo_multihop.py
├── src/
│   ├── ingest/                     # PDF parser, entity extractor, normalizer, batch
│   ├── graph/                      # schema, provenance, neo4j_loader, store
│   ├── retrieval/                  # graph_retriever, vector_store, hybrid_retriever, query_understanding
│   ├── llm/                        # provider (Groq/OpenAI/OpenRouter), generate
│   ├── pipeline/                   # ingest, query (4-stage orchestrator), evaluate
│   └── common/config.py
└── .planning/                      # GSD planning artifacts (PROJECT, ROADMAP, phases)
```

---

## Integration surface (for downstream tracks T2–T5)

T1 code was written so other tracks can integrate without rework:

- **Importable Python APIs** — every CLI is a thin wrapper around a function (`run_query_structured`, `run_batch`, `merge_node_with_provenance`, …).
- **Structured returns** — `QueryAnswer` (Pydantic) carries prose, evidence, `not_found`, `suggestion`, `pipeline_stage`. Triples carry `source_doc`.
- **Deterministic, idempotent ingest** — same input ⇒ same graph state. Scoped deletes keyed on `source_doc`.
- **Stable CLI signatures** — `--question / --depth / --provider / --model` flags are unchanged from v1.0 plus additive flags only.
- **Provider-agnostic LLM layer** — `src/llm/provider.py:build_instructor_client(provider)` accepts `groq | openai | openrouter`.

---

## Known limitations / merge considerations

- **Vector store is bag-of-words** (`SimpleVectorStore`). Adequate for the demo's fallback role but not embedding-quality. Replacing it is a future track concern.
- **`Neo4jGraphStore.list_node_ids()` is process-cached** — restart Streamlit/CLI after re-ingestion to pick up new nodes.
- **Replacement-style answers use a deterministic summarizer** (`_fallback_answer`) rather than the LLM, by design, so demo replays are stable. Toggle in `src/llm/generate.py:generate_answer`.
- **Trilingual handling** — only `thp9045_wiring_module` pages 1–4 are ingested (English); FR/ES translations are intentionally skipped via the manifest's `pages` field.

If any of these are blockers for your downstream track, raise it on the PR before merging.

---

## Quick task log (during this milestone)

Recent quick tasks (`.planning/quick/`):

- `260503-ox5-filter-unknown-kind-stub-nodes-and-dangl` — sanitise UNKNOWN-kind stubs before load.
- `260504-hk3-milestone-2-demo-ui` — 4-tab Streamlit demo.
- `260504-hrj-multi-doc-free-form-input` — free-form multi-hop query box.
- `260504-ilx-wire-rag-pipeline-multidoc` — wire RAG pipeline through multi-doc tab.
- `260504-ask-pipeline-wiring` — wire full 4-stage pipeline (graph → LLM understanding → vector fallback → answer) into the Ask tab with per-stage UI badges.

---

*Last updated: 2026-05-04 — milestone v2.0 T1-Sai ready for review.*
