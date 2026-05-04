"""Batch ingestion orchestration core — Phase 3 BATCH-01..03.

Public API:
    - iter_manifest_docs(manifest_path, doc_id_filter)  -> Iterator[dict]
    - ingest_one_doc(doc, *, dry_run, inferencer, force, output_dir, driver, scoped_delete) -> tuple
    - run_batch(args) -> list[dict]

Wave 1 plan (03-02) shipped the dry-run path.
Wave 3 plan (03-03) wires the full Neo4j path: driver lifecycle, scoped_delete_doc
before each load, and the four neo4j_loader helpers (upsert_document, load_nodes,
load_edges) per doc. --reset performs a full DB wipe before the loop.
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

from src.graph.neo4j_loader import create_constraints, upsert_document, load_nodes, load_edges
from src.graph.provenance import scoped_delete_doc
from src.ingest.batch_report import build_doc_report, capture_warnings
from src.ingest.failure_log import log_failure
from src.ingest.manifest import load_manifest

__all__ = ["ingest_one_doc", "iter_manifest_docs", "run_batch"]


# ---------------------------------------------------------------------------
# iter_manifest_docs
# ---------------------------------------------------------------------------

def iter_manifest_docs(
    manifest_path: Path | str,
    doc_id_filter: str | None,
) -> Iterator[dict[str, Any]]:
    """Yield manifest entries, optionally filtered to a single doc_id.

    Args:
        manifest_path:  Path to the manifest JSON file.
        doc_id_filter:  If set, yield only the matching doc.  Raises
                        ``ValueError`` (listing all valid doc_ids) when the
                        slug is not in the manifest — friendly UX.

    Yields:
        Manifest entry dicts with at minimum ``doc_id`` and ``filename``.
    """
    docs = load_manifest(manifest_path)
    if doc_id_filter is None:
        yield from docs
        return

    for doc in docs:
        if doc["doc_id"] == doc_id_filter:
            yield doc
            return

    available = [d["doc_id"] for d in docs]
    raise ValueError(
        f"doc_id {doc_id_filter!r} not found in manifest.\n"
        f"Available doc_ids: {available}"
    )


# ---------------------------------------------------------------------------
# Internal extraction helper
# ---------------------------------------------------------------------------

def _extract_to_graph_items(
    doc: dict,
    inferencer: str | None,
    force: bool,
    cache_path: Path,
) -> dict:
    """Run in-process extraction and return graph_items dict.

    Constructs an argparse.Namespace mirroring ``src.pipeline.ingest``'s
    CLI surface and calls ``main()`` via a programmatic entry-point.
    Captures / suppresses stdout so batch summary is not polluted.

    The produced JSON is always written to ``cache_path`` by ingest.main()
    and then read back here so callers have a dict to work with immediately.
    """
    import argparse
    import contextlib
    import io

    pdf_filename = doc.get("filename", "")
    pdf_path = Path("data/raw") / pdf_filename

    # Build a namespace that mimics parsing `python -m src.pipeline.ingest`
    ns = argparse.Namespace(
        input=str(pdf_path),
        replacements=None,
        output=str(cache_path),
        rich_output=None,
        doc_id=doc["doc_id"],
        inferencer=inferencer,
        force_extract=force,
        verbose=False,
    )

    # Redirect stdout to suppress the "Saved graph items to …" print
    with contextlib.redirect_stdout(io.StringIO()):
        from src.pipeline.ingest import main as _ingest_main
        import argparse as _ap
        _orig_parse = _ap.ArgumentParser.parse_args

        def _stub_parse(self, *a, **kw):  # noqa: ANN001
            return ns

        _ap.ArgumentParser.parse_args = _stub_parse
        try:
            _ingest_main()
        finally:
            _ap.ArgumentParser.parse_args = _orig_parse

    # Read back the produced JSON
    with cache_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Full-DB reset helper (--reset flag)
# ---------------------------------------------------------------------------

def _full_db_reset(driver: Any) -> None:
    """Wipe all nodes and relationships. Used only when args.reset=True."""
    with driver.session() as sess:
        sess.run("MATCH (n) DETACH DELETE n")


# ---------------------------------------------------------------------------
# ingest_one_doc
# ---------------------------------------------------------------------------

def ingest_one_doc(
    doc: dict,
    *,
    dry_run: bool,
    inferencer: str | None,
    force: bool,
    output_dir: Path,
    driver: Any = None,
    scoped_delete: bool = False,
) -> tuple[dict, str, list[dict], str | None]:
    """Extract one document and (optionally) load it into Neo4j.

    Args:
        doc:          Manifest entry dict (must have ``doc_id``, ``filename``).
        dry_run:      When True, skip Neo4j entirely; only extraction runs.
        inferencer:   LLM backend slug ("groq", "openrouter", "gemini") or None
                      for auto-detect.
        force:        Bypass the extraction cache (maps to --force-extract).
        output_dir:   Directory for cache JSONs (data/processed/).
        driver:       neo4j.GraphDatabase driver instance (None in dry-run).
        scoped_delete: Ignored here — scoped_delete is handled one level up in
                       _run_one_doc for correct stage attribution. This parameter
                       is kept for API compatibility but is never used inside
                       this function when driver is not None.

    Returns:
        (graph_items, stage_completed, warnings_placeholder, model_name)

        ``warnings_placeholder`` is always an empty list; ``run_batch``
        collects warnings via its own ``capture_warnings`` context and
        overrides this return value.

    Raises:
        Any exception from the extraction or Neo4j load pipeline — NOT swallowed.
    """
    cache_path = output_dir / f"_{doc['doc_id']}_corpus.json"

    graph_items = _extract_to_graph_items(doc, inferencer, force, cache_path)

    if dry_run or driver is None:
        return graph_items, "extract", [], None

    # Non-dry-run: compose loader helpers (mirrors neo4j_loader.main() L290-302)
    doc_metadata = {
        "doc_id": doc["doc_id"],
        "title": doc.get("title") or doc["doc_id"],
        "sku": doc.get("sku"),
        "source_url": doc.get("source_url"),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }

    upsert_document(driver, doc_metadata)
    load_nodes(driver, graph_items["nodes"], doc["doc_id"])
    load_edges(driver, graph_items["edges"], doc["doc_id"])

    return graph_items, "neo4j_load", [], None


# ---------------------------------------------------------------------------
# Per-doc body helper (shared by dry-run and full-mode loops)
# ---------------------------------------------------------------------------

def _run_one_doc(
    doc: dict,
    *,
    driver: Any,
    do_scoped_delete: bool,
    args: Any,
    report_dir: Path,
    output_dir: Path,
    reports: list[dict],
) -> None:
    """Execute extraction (and optional Neo4j load) for a single doc.

    Appends one report dict to ``reports``. Handles error capture and
    stage attribution so the caller (run_batch) stays clean.
    """

    started = datetime.now(timezone.utc)

    error: dict | None = None
    graph_items: dict = {"nodes": [], "edges": []}
    stage = "extract"
    model: str | None = None
    scoped_delete_ran = False

    dry_run = getattr(args, "dry_run", False)

    with capture_warnings() as warnings:
        try:
            # Step 1: optional scoped delete (non-dry-run only)
            if do_scoped_delete and driver is not None:
                stage = "scoped_delete"
                with driver.session() as s:
                    s.execute_write(scoped_delete_doc, doc["doc_id"])
                scoped_delete_ran = True

            # Step 2a: extraction only (always runs regardless of mode)
            stage = "extract"
            cache_path = output_dir / f"_{doc['doc_id']}_corpus.json"
            graph_items = _extract_to_graph_items(
                doc,
                getattr(args, "inferencer", None),
                getattr(args, "force", False),
                cache_path,
            )

            # Step 2b: Neo4j load (full-mode only)
            if not dry_run and driver is not None:
                stage = "neo4j_load"
                doc_metadata = {
                    "doc_id": doc["doc_id"],
                    "title": doc.get("title") or doc["doc_id"],
                    "sku": doc.get("sku"),
                    "source_url": doc.get("source_url"),
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                }
                upsert_document(driver, doc_metadata)
                load_nodes(driver, graph_items["nodes"], doc["doc_id"])
                load_edges(driver, graph_items["edges"], doc["doc_id"])

        except Exception as exc:
            log_failure(doc["doc_id"], stage, exc)
            error = {
                "class": type(exc).__name__,
                "message": str(exc),
                "traceback_snippet": traceback.format_exc(limit=10),
            }

    finished = datetime.now(timezone.utc)

    report = build_doc_report(
        doc=doc,
        graph_items=graph_items,
        started_at=started,
        finished_at=finished,
        inferencer=getattr(args, "inferencer", None),
        model=model,
        dry_run=dry_run,
        scoped_delete_ran=scoped_delete_ran,
        warnings=list(warnings),
        error=error,
        stage_completed=stage,
    )

    (report_dir / f"{doc['doc_id']}_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    reports.append(report)


# ---------------------------------------------------------------------------
# run_batch
# ---------------------------------------------------------------------------

def run_batch(args: Any) -> list[dict]:
    """Orchestrate batch ingestion of all manifest documents.

    Iterates manifest docs (or the single doc when ``args.doc_id`` is set),
    runs extraction + optional Neo4j load inside a per-doc try/except,
    writes one JSON report per doc, and returns the list of report dicts
    for the caller to print a summary table.

    Args:
        args:  argparse.Namespace with attributes:
               dry_run, doc_id, inferencer, force, no_scoped_delete,
               report_dir, manifest, fail_fast, verbose, reset.

    Returns:
        list of per-doc report dicts (Pattern 2 schema from build_doc_report).

    Raises:
        SystemExit: when Neo4j connection fails (exit code 3 — caught in main()).
    """
    from neo4j import GraphDatabase
    from src.graph.neo4j_loader import create_constraints

    report_dir = Path(args.report_dir if args.report_dir else "reports/batch")
    report_dir.mkdir(parents=True, exist_ok=True)

    output_dir = Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.manifest) if args.manifest else Path("data/raw/manifest.json")

    reports: list[dict] = []

    if args.dry_run:
        # Dry-run path (Plan 03-02) — no driver needed
        for doc in iter_manifest_docs(manifest_path, getattr(args, "doc_id", None)):
            _run_one_doc(
                doc,
                driver=None,
                do_scoped_delete=False,
                args=args,
                report_dir=report_dir,
                output_dir=output_dir,
                reports=reports,
            )
            if reports and reports[-1].get("status") == "fail" and getattr(args, "fail_fast", False):
                break
    else:
        # Full-mode path (Plan 03-03) — real Neo4j driver
        from neo4j import GraphDatabase
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "")

        with GraphDatabase.driver(uri, auth=(user, password)) as driver:
            try:
                driver.verify_connectivity()
            except Exception as exc:
                raise SystemExit(f"Neo4j connection failed: {exc}") from exc

            create_constraints(driver)

            if getattr(args, "reset", False):
                _full_db_reset(driver)

            # Scoped delete runs per-doc by default; disabled by --no-scoped-delete or --reset
            do_scoped_delete = (
                not getattr(args, "no_scoped_delete", False)
                and not getattr(args, "reset", False)
            )

            for doc in iter_manifest_docs(manifest_path, getattr(args, "doc_id", None)):
                _run_one_doc(
                    doc,
                    driver=driver,
                    do_scoped_delete=do_scoped_delete,
                    args=args,
                    report_dir=report_dir,
                    output_dir=output_dir,
                    reports=reports,
                )
                if reports and reports[-1].get("status") == "fail" and getattr(args, "fail_fast", False):
                    break

    return reports
