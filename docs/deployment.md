# Deployment Guide

> **Submission note:** Public Streamlit Cloud + Aura deployment is documented but
> not active for the final submission. Graders should use the Docker Compose setup
> below.

---

## Local Docker Setup (one-command bring-up)

This is the primary graded deliverable. It starts Neo4j and the Streamlit app in
containers and seeds the knowledge graph from the committed corpus JSONs — no Python
environment setup required beyond Docker Desktop.

### Prerequisites

- **Docker Desktop** (Windows/macOS) or **Docker Engine** (Linux) — v24+
- A **Groq API key** (obtain from [console.groq.com](https://console.groq.com))
- Ports **7474**, **7687**, and **8501** free on your machine

---

### Step-by-step

**Step 1 — Clone the repo and enter it**

```bash
git clone <repo-url>
cd Graph-RAG
```

**Step 2 — Export your Groq API key**

The app service reads `GROQ_API_KEY` from your shell environment.

```bash
# macOS / Linux
export GROQ_API_KEY=your_key_here

# Windows PowerShell
$env:GROQ_API_KEY="your_key_here"
```

**Step 3 — Start Neo4j and the Streamlit app**

```bash
docker compose up -d
```

This builds the app image, pulls `neo4j:5`, and starts both containers in the
background. Neo4j takes ~30 seconds to initialise — the app container waits for the
Neo4j healthcheck to pass before it starts serving traffic.

> **Note:** First run downloads ~600 MB of images. Subsequent runs start in seconds.

**Step 4 — Wait for Neo4j to finish booting (~30 seconds)**

Watch the healthcheck status:

```bash
docker compose ps
```

Wait until the `neo4j` service shows `healthy` before proceeding.

**Step 5 — Seed the knowledge graph**

Load the 4-PDF Honeywell HVAC corpus into the local Neo4j container:

```bash
docker compose --profile seed run seed
```

Expected output: a per-doc table showing nodes and edges loaded, followed by
database statistics. This step is idempotent — safe to run again if interrupted.

**Step 6 — Open the app**

| URL | What it is |
|-----|------------|
| http://localhost:8501 | Streamlit GraphRAG demo |
| http://localhost:7474 | Neo4j Browser (login: `neo4j` / `devpassword`) |

---

### Local dev credentials

The Docker Compose setup uses hardcoded local-only credentials:

```
Username: neo4j
Password: devpassword
```

These are intentionally simple and documented here. Do **not** use them in any
internet-facing deployment.

---

### Troubleshooting

**Port conflict (7474 / 7687 / 8501 already in use)**

Find and stop whatever is using the port, or edit `docker-compose.yml` to map to
different host ports (e.g. `"7688:7687"`).

```bash
# macOS / Linux — find what's on port 7687
lsof -i :7687

# Windows
netstat -ano | findstr :7687
```

**Neo4j is slow to start / app shows "Could not connect to Neo4j"**

Neo4j can take up to 60 seconds on first boot with an empty volume. The app
healthcheck retries for up to 130 seconds (`start_period: 30s` + 10 retries × 10s).
If the app still fails, run:

```bash
docker compose logs neo4j
```

And wait until you see `Remote interface available at http://localhost:7474/` in the
logs before retrying the seed step.

**Wipe everything and start fresh**

```bash
docker compose down -v   # stops containers AND deletes the neo4j_data volume
docker compose up -d     # fresh start
docker compose --profile seed run seed   # re-seed
```

---

## Public Streamlit Cloud + Aura (not active for final submission)

The application is architected to support deployment to Streamlit Community Cloud
backed by a Neo4j Aura free-tier instance. The required changes are:

1. Set the following secrets in the Streamlit Cloud dashboard:
   - `NEO4J_URI` = `neo4j+s://<id>.databases.neo4j.io`
   - `NEO4J_USER` = `neo4j`
   - `NEO4J_PASSWORD` = `<aura-password>`
   - `GROQ_API_KEY` = `<groq-key>`
2. Pre-seed Aura with `scripts/seed_aura.py` (reads the same env vars from `.env`
   locally, or from shell env in CI).
3. Push to the branch connected to Streamlit Cloud.

The app reads all four values via `os.getenv()` at runtime (Phase 1 config refactor),
so no code changes are required — only secret configuration.
