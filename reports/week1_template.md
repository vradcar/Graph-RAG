# Week 1 Report — GraphRAG Foundation

## Objective
Set up a foundational GraphRAG pipeline covering the full path from raw data
ingestion through graph construction, retrieval, and answer generation. Run an
end-to-end baseline on a sample product compatibility dataset.

## Pipeline Plan
- **Graph construction:** Parse raw JSON product records → extract nodes
  (products, accessories) and edges (COMPATIBLE_WITH, REPLACES) → store in a
  networkx MultiDiGraph via `GraphStore`
- **Query understanding:** Extract candidate entity mentions from the question
  using regex (uppercase product codes e.g. `TH1110D`, `T6-PRO`)
- **Graph traversal:** BFS from matched entities up to configurable depth,
  collecting (source, relation, target) triples
- **Context assembly:** Combine graph triples and/or vector-matched document
  chunks into a context string passed to the LLM
- **LLM generation:** Placeholder in `src/llm/generate.py` — to be replaced
  with real provider call in a later week

## Data Used
- **Domain selected:** Product compatibility — HVAC thermostats and accessories
- **Source documents:**
  - `data/raw/products_sample.json` — 3 product records (TH1110D, T6-PRO, SMK-100)
  - `data/raw/doc_chunks.json` — 4 unstructured text chunks covering product
    descriptions, compatibility notes, and compliance references
- **Entity types:** Product, Accessory
- **Relationship types:** `COMPATIBLE_WITH`, `REPLACES`

## Implementation Summary
- **Tools/libraries:** Python, networkx 3.4.2, numpy, pdfplumber (ingestion),
  python-dotenv, pyyaml
- **Graph backend:** networkx `MultiDiGraph` (local, in-memory) — Neo4j
  configured in settings for future extension
- **Extraction approach:** `src/graph/extract.py` reads JSON product records,
  creates one node per product and one node per unique accessory, then adds
  directed edges for compatibility and replacement relationships. Ingest
  produces `data/processed/graph_items.json` (8 nodes, 6 edges).

## Evidence
1. **Graph built:** `python -m src.pipeline.ingest --input data/raw/products_sample.json`
   → `Saved graph items to data/processed/graph_items.json (8 nodes, 6 edges)`
2. **Sample query output (graph mode, depth 2):**
   ```
   Question: What is the modern replacement for TH1110D?
   Graph evidence:
   - TH1110D --[COMPATIBLE_WITH]--> WALL-PLATE-A
   - T6-PRO --[REPLACES]--> TH1110D
   - T6-PRO --[COMPATIBLE_WITH]--> WALL-PLATE-A
   - T6-PRO --[COMPATIBLE_WITH]--> REDLINK-GATEWAY
   ```
3. **Evaluation baseline:** 12 queries run across graph, vector, and hybrid
   retrieval — results saved to `data/eval/results.json`

## Risks / Next Steps
- LLM generation is a stub — answer quality cannot be evaluated until a real
  provider is wired in (Week 2/3, Member 4)
- Graph retriever uses regex entity extraction: only matches uppercase
  product codes — natural-language entity references will miss
- Dataset is very small (3 products); accuracy numbers will shift
  significantly once real domain data is ingested
- Week 2: extend ingestion to PDF sources and expand entity/relationship types
