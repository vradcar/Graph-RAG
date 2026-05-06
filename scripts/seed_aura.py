"""Seed a Neo4j Aura (or any remote Neo4j) instance from the committed corpus JSONs.

Reads the pre-extracted ``data/processed/_<doc_id>_corpus.json`` files produced
by the batch ingestion pipeline and loads them into the target database.  No LLM
calls are made — this is a pure graph-load step that is safe to re-run (MERGE).

Required env vars (set in .env for local Aura testing, or in Streamlit Cloud
Secrets dashboard for the public demo):

    NEO4J_URI      neo4j+s://<id>.databases.neo4j.io   (Aura)
                   bolt://localhost:7687                 (local Docker)
    NEO4J_USER     neo4j
    NEO4J_PASSWORD <password>

Usage:
    # Seed all 4 docs (idempotent — safe to run multiple times)
    python scripts/seed_aura.py

    # Wipe the database first, then seed fresh
    python scripts/seed_aura.py --reset

    # Verify counts only — no data load
    python scripts/seed_aura.py --verify

    # Seed a single document
    python scripts/seed_aura.py --doc-id t9_install_guide

    # Point at a specific manifest / corpus dir
    python scripts/seed_aura.py --manifest data/raw/manifest.json \\
                                 --corpus-dir data/processed
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from neo4j import GraphDatabase

# Reuse the battle-tested loader helpers from the existing pipeline.
from src.graph.neo4j_loader import (
    create_constraints,
    upsert_document,
    load_nodes,
    load_edges,
    verify as neo4j_verify,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
log = logging.getLogger("seed_aura")


# ---------------------------------------------------------------------------
# Driver factory
# ---------------------------------------------------------------------------

def _build_driver(uri: str, user: str, password: str):
    """Create and verify a Neo4j driver.  Raises SystemExit on failure."""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
    except Exception as exc:
        raise SystemExit(
            f"Cannot connect to Neo4j at {uri}\n"
            f"  → {exc}\n"
            "Check NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD in your .env or "
            "Streamlit Cloud Secrets."
        ) from exc
    return driver


# ---------------------------------------------------------------------------
# Corpus loader
# ---------------------------------------------------------------------------

def _load_corpus(doc_id: str, corpus_dir: Path) -> dict:
    """Return the graph_items dict for a doc_id, or raise FileNotFoundError."""
    path = corpus_dir / f"_{doc_id}_corpus.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Corpus file not found: {path}\n"
            "Run 'python scripts/batch_ingest.py --dry-run' to regenerate it."
        )
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Per-doc seed
# ---------------------------------------------------------------------------

def seed_one_doc(doc: dict, driver, corpus_dir: Path) -> dict:
    """Load one document into Neo4j from its cached corpus JSON.

    Returns a result dict with keys: doc_id, status, nodes, edges, runtime_s,
    error (None on success).
    """
    doc_id = doc["doc_id"]
    t0 = perf_counter()
    error = None
    nodes_loaded = edges_loaded = 0

    try:
        graph_items = _load_corpus(doc_id, corpus_dir)

        doc_metadata = {
            "doc_id": doc_id,
            "title": doc.get("title") or doc_id,
            "sku": doc.get("sku"),
            "source_url": doc.get("source_url"),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }

        upsert_document(driver, doc_metadata)
        nodes_loaded = load_nodes(driver, graph_items.get("nodes", []), doc_id)
        edges_loaded = load_edges(driver, graph_items.get("edges", []), doc_id)

    except Exception as exc:
        error = str(exc)
        log.error("Failed to seed %s: %s", doc_id, exc)

    runtime = perf_counter() - t0
    return {
        "doc_id": doc_id,
        "status": "ok" if error is None else "fail",
        "nodes": nodes_loaded,
        "edges": edges_loaded,
        "runtime_s": round(runtime, 3),
        "error": error,
    }


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_summary(results: list[dict]) -> None:
    COL_DOC, COL_STATUS, COL_NODES, COL_EDGES, COL_RT = 32, 6, 7, 7, 10

    header = (
        f"{'doc_id':<{COL_DOC}} {'status':<{COL_STATUS}} "
        f"{'nodes':>{COL_NODES}} {'edges':>{COL_EDGES}} {'runtime_s':>{COL_RT}}"
    )
    sep = f"{'-'*COL_DOC} {'-'*COL_STATUS} {'-'*COL_NODES} {'-'*COL_EDGES} {'-'*COL_RT}"
    print(header)
    print(sep)

    ok = fail = 0
    for r in results:
        print(
            f"{r['doc_id']:<{COL_DOC}} {r['status']:<{COL_STATUS}} "
            f"{r['nodes']:>{COL_NODES}} {r['edges']:>{COL_EDGES}} "
            f"{r['runtime_s']:>{COL_RT}}"
        )
        if r["status"] == "ok":
            ok += 1
        else:
            fail += 1
            print(f"  error: {r['error']}")

    print()
    print(f"summary: {ok} ok / {fail} fail")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="seed_aura",
        description="Seed a Neo4j Aura instance from committed corpus JSONs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--doc-id",
        metavar="SLUG",
        default=None,
        help="Seed only this doc_id (e.g. t9_install_guide). Default: all manifest docs.",
    )
    parser.add_argument(
        "--manifest",
        default="data/raw/manifest.json",
        metavar="PATH",
        help="Path to manifest JSON (default: data/raw/manifest.json).",
    )
    parser.add_argument(
        "--corpus-dir",
        default="data/processed",
        metavar="PATH",
        help="Directory containing _<doc_id>_corpus.json files (default: data/processed).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe all Neo4j data before seeding. Use with care against Aura.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Print database counts and exit without loading.",
    )
    args = parser.parse_args(argv)

    # Credential resolution — env vars only (no settings.yaml dependency here).
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    if not password:
        print("error: NEO4J_PASSWORD is not set.", file=sys.stderr)
        return 1

    print(f"Connecting to {uri} as {user} …")
    driver = _build_driver(uri, user, password)

    if args.verify:
        neo4j_verify(driver)
        driver.close()
        return 0

    # Load manifest
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"error: manifest not found: {manifest_path}", file=sys.stderr)
        driver.close()
        return 1

    with manifest_path.open(encoding="utf-8") as fh:
        all_docs: list[dict] = json.load(fh).get("documents", [])

    if args.doc_id:
        docs = [d for d in all_docs if d["doc_id"] == args.doc_id]
        if not docs:
            available = [d["doc_id"] for d in all_docs]
            print(f"error: doc_id {args.doc_id!r} not in manifest. Available: {available}", file=sys.stderr)
            driver.close()
            return 1
    else:
        docs = all_docs

    corpus_dir = Path(args.corpus_dir)

    # Optional wipe
    if args.reset:
        print("--reset: wiping all nodes and relationships …")
        with driver.session() as sess:
            sess.run("MATCH (n) DETACH DELETE n")
        print("Database wiped.")

    # Schema constraints (idempotent)
    create_constraints(driver)

    # Seed each doc
    print(f"\nSeeding {len(docs)} document(s) …\n")
    results = []
    for doc in docs:
        print(f"  → {doc['doc_id']} …", end=" ", flush=True)
        result = seed_one_doc(doc, driver, corpus_dir)
        results.append(result)
        status_str = f"ok ({result['nodes']} nodes, {result['edges']} edges)" if result["status"] == "ok" else f"FAIL: {result['error']}"
        print(status_str)

    print()
    _print_summary(results)

    # Always run verify at the end so you can see total Aura state
    print()
    neo4j_verify(driver)

    driver.close()
    return 0 if all(r["status"] == "ok" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
