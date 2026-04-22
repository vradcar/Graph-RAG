# Member 4 + Member 5 Execution Checklist (Tonight)

## Scope
- Member 4: Prompt and context pipeline (LLM + fallback + traceable evidence)
- Member 5: UI and report integration (Streamlit controls + exportable evidence)

## What is implemented
- Deterministic fallback answer generation if Groq/OpenAI provider setup fails.
- Triple normalization and deduplication before answer generation.
- Streamlit evidence export panel with downloadable JSON and TXT outputs.
- Existing depth slider and Neo4j link remain in place.

## Run sequence
1. Start Neo4j and confirm Bolt endpoint (`bolt://localhost:7687`).
2. Set `.env` values:
   - `NEO4J_PASSWORD=...`
   - `GROQ_API_KEY=...` or `OPENAI_API_KEY=...` (optional now due to fallback mode)
3. Run ingestion:
   - `python -m src.pipeline.ingest --input data/raw/t9-thermostat.pdf --replacements data/raw/replacements.json --output data/processed/graph_items.json`
4. Load graph into Neo4j:
   - `python -m src.graph.neo4j_loader --input data/processed/graph_items.json --verify`
5. Run Streamlit UI:
   - `streamlit run app.py`
6. Ask at least 2 queries at depth 1 and depth 2.
7. Use **Export Evidence** buttons to download:
   - `query_evidence.json`
   - `query_evidence.txt`

## Screenshot checklist (for report)
- UI with depth slider and query input visible.
- Query response with Graph Evidence expander visible.
- Export Evidence section with download buttons visible.
- Optional: Neo4j Browser graph view.

## Submission note
If LLM key is unavailable, the app still produces deterministic evidence-backed fallback output suitable for demonstrating multi-hop traversal and context assembly behavior.
