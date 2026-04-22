# How To Use

This guide is the practical runbook for this GraphRAG repo.

## 1) Prerequisites
- Python 3.11+ (Windows)
- Docker Desktop (for Neo4j)
- PowerShell terminal

## 2) Setup
```powershell
Set-Location "g:\Spring 2026\GenAI Development\Graph RAG"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 3) Configure Environment
Edit `.env` and make sure these values exist and are consistent:

```dotenv
LLM_PROVIDER=groq
GROQ_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=<your_key>

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

Notes:
- Use `NEO4J_USER` (not `NEO4J_USERNAME`) for loader compatibility.
- Keep only one `NEO4J_PASSWORD` entry.

## 4) Start Neo4j
```powershell
docker run --name graphrag-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password -d neo4j:5
```

If already created:
```powershell
docker start graphrag-neo4j
```

Open Neo4j Browser: `http://localhost:7474`

## 5) Build Graph Data From PDF
```powershell
python -m src.pipeline.ingest --input data/raw/t9-thermostat.pdf --replacements data/raw/replacements.json --output data/processed/graph_items.json --verbose
```

Expected: message showing output file with node and edge counts.

## 6) Load Data Into Neo4j
```powershell
python -m src.graph.neo4j_loader --input data/processed/graph_items.json --verify
```

Expected: database stats (total nodes/edges, labels, relation types).

## 7) Query From CLI
Depth comparison example:
```powershell
python -m src.pipeline.query --question "What is the modern replacement for this discontinued part?" --depth 1
python -m src.pipeline.query --question "What is the modern replacement for this discontinued part?" --depth 2
```

Expected:
- `depth 1`: mostly direct replacement edges
- `depth 2`: replacement + richer downstream context (compatibility/wiring/spec constraints)

## 8) Evaluate Query Set
```powershell
python -m src.pipeline.evaluate --queries data/eval/queries.json --output data/eval/results.json
```

Check output in `data/eval/results.json`.

## 9) Run Streamlit App
```powershell
python -m streamlit run app.py
```

Use the URL printed in terminal (for example `http://localhost:8503`).

In app:
- ask a query
- change depth slider (1 vs 2)
- open **Graph Evidence**
- use **Download Evidence (JSON/TXT)** for report artifacts

## 10) Common Issues
- `ModuleNotFoundError` for packages:
  - Ensure `.venv` is active and reinstall: `python -m pip install -r requirements.txt`
- Streamlit import/runtime mismatch:
  - Launch from venv with `python -m streamlit run app.py` (not global Anaconda streamlit).
- Neo4j connection failure:
  - Verify container is running and `.env` password matches Docker auth.
- Query says not found:
  - Ask with concrete entity IDs or use the replacement question shown above.

## 11) Deliverable Evidence Checklist
- Neo4j graph screenshot
- CLI depth=1 output screenshot
- CLI depth=2 output screenshot
- Streamlit answer + evidence screenshot
- Exported evidence JSON/TXT attached to report
