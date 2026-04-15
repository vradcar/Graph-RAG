---
phase: 01-graph-schema-ingestion
plan: "05"
subsystem: pipeline
status: checkpoint-pending
tags: [ingest, pipeline, neo4j, groq, pdf]
dependency_graph:
  requires: [01-02, 01-03, 01-04]
  provides: [ingest-cli, run_ingest]
  affects: [src/pipeline/ingest.py]
tech_stack:
  added: []
  patterns: [load_dotenv-first, setup_constraints-before-merge, dry-run-flag]
key_files:
  created: []
  modified:
    - src/pipeline/ingest.py
decisions: []
metrics:
  started: "2026-04-15T06:14:13Z"
  checkpoint_reached: "2026-04-15T06:29:06Z"
  completed: null
  tasks_completed: 1
  tasks_total: 3
  files_modified: 1
---

# Phase 01 Plan 05: Ingest Pipeline Integration Summary

**One-liner:** Rewrote ingest CLI to wire pdf_parser + entity_extractor + normalizer + Neo4jGraphStore with load_dotenv-first ordering and --dry-run support.

**Status: CHECKPOINT PENDING** — Task 2 (human-verify: Neo4j + Groq live run) is required before Task 3 (idempotency integration test) can proceed.

---

## Task 1: Rewrite src/pipeline/ingest.py — COMPLETE

**Commit:** `c34b0a2`

**What was built:**

`src/pipeline/ingest.py` was completely rewritten from the original JSON-based CLI skeleton into a full PDF → Neo4j integration pipeline. Key properties:

- `load_dotenv()` is the very first executable statement at module level, before all other imports that might access `os.getenv()`.
- `run_ingest(pdf_path, dry_run=False)` is the core logic function, separated from `main()` for testability.
- Pipeline order: `extract_page_content()` → `build_client()` / `extract_from_page()` per page → `normalize_and_deduplicate()` → `Neo4jGraphStore.setup_constraints()` → `upsert_node()` / `upsert_edge()`.
- `--dry-run` flag: parses the PDF and runs LLM extraction but skips Neo4j writes entirely; returns `nodes_written=0, edges_written=0`.
- Post-write REPLACES dangling-target validation: queries Neo4j and warns if any REPLACES edge points to a non-Product node.
- Node count summary by label printed to stdout after each live run.
- If `GROQ_API_KEY` is missing, `build_client()` raises `ValueError` and the CLI prints a clear error to stderr and exits non-zero.
- `Path(args.input).exists()` checked before passing to `fitz.open()` (T-05-02 mitigation).

**Acceptance criteria verified:**

| Check | Result |
|-------|--------|
| `load_dotenv()` appears before other imports | PASS |
| `setup_constraints()` called before MERGE | PASS |
| `def run_ingest` present | PASS |
| `normalize_and_deduplicate` imported | PASS |
| `--dry-run` appears 5+ times in file | PASS |
| `from src.pipeline import ingest` — no ImportError | PASS |
| `python -m src.pipeline.ingest --help` exits 0 | PASS |

---

## Task 2: Checkpoint — PENDING (human-verify)

**Gate:** `blocking`

The checkpoint requires the user to:

1. Start Neo4j via Docker:
   ```
   docker run -d --name neo4j-graphrag -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5
   ```
2. Ensure `GROQ_API_KEY` is set in `.env`.
3. Run a dry-run first (no cost, no Neo4j writes):
   ```
   python -m src.pipeline.ingest --input data/raw/t9-thermostat.pdf --dry-run
   ```
4. Run the live ingest:
   ```
   python -m src.pipeline.ingest --input data/raw/t9-thermostat.pdf
   ```
5. Open Neo4j Browser at `http://localhost:7474` and confirm nodes and edges appear via `MATCH (n) RETURN n LIMIT 25`.

**Resume signal:** Type "verified" once nodes appear in Neo4j Browser, or paste terminal output if errors occur.

---

## Task 3: tests/test_ingest_pipeline.py — NOT YET EXECUTED

Awaiting human-verify checkpoint resolution. Once resumed, Task 3 will write:
- `test_missing_pdf_raises` (unit — no Neo4j/Groq needed)
- `test_dry_run_returns_zero_writes` (skips if no GROQ_API_KEY)
- `test_run_ingest_summary_has_expected_keys` (skips if no GROQ_API_KEY)
- `test_double_run_idempotency` (`@pytest.mark.integration` — requires live Neo4j + Groq)

---

## Deviations from Plan

None — plan executed exactly as written for Task 1.

---

## Threat Surface Scan

No new network endpoints or auth paths introduced. Security mitigations from the threat register are present:

| Threat | Mitigation Applied |
|--------|-------------------|
| T-05-01 (key disclosure) | `load_dotenv()` first; keys never logged; clear ValueError message |
| T-05-02 (path injection) | `Path(args.input).exists()` check before pdf_parser call |
| T-05-03 (Cypher injection) | All writes via `Neo4jGraphStore.upsert_node/upsert_edge` which parameterize all ids |
| T-05-04 (DoS) | Accepted — no retry loop, Groq failures propagate as exceptions |

## Self-Check

- [x] `src/pipeline/ingest.py` exists and is importable
- [x] Commit `c34b0a2` exists in git log
- [x] No unexpected file deletions in commit
