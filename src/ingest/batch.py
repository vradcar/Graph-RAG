"""Batch ingestion orchestration core — Phase 3 BATCH-01..03.

Public API:
    - iter_manifest_docs(manifest_path, doc_id_filter)  -> Iterator[dict]
    - ingest_one_doc(doc, *, dry_run, inferencer, force, output_dir, driver, scoped_delete) -> tuple
    - run_batch(args) -> list[dict]

Wave 1 plan (03-02) ships the dry-run path. Non-dry-run (real Neo4j MERGE +
scoped delete) is wired in Plan 03-03; the branch currently raises
NotImplementedError with a clear pointer.
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

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
    import os

    from src.ingest.manifest import get_doc

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
        # ingest.main() reads sys.argv; replace argv temporarily and call
        # the function with our Namespace-style workaround.
        # We monkey-patch argparse.ArgumentParser.parse_args to return our ns
        # for the duration of this call only.
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
        scoped_delete: Run scoped_delete_doc before loading (Plan 03-03 wires).

    Returns:
        (graph_items, stage_completed, warnings_placeholder, model_name)

        ``warnings_placeholder`` is always an empty list; ``run_batch``
        collects warnings via its own ``capture_warnings`` context and
        overrides this return value.

    Raises:
        Any exception from the extraction pipeline — NOT swallowed — so
        ``run_batch``'s try/except boundary can capture it cleanly.
    """
    cache_path = output_dir / f"_{doc['doc_id']}_corpus.json"

    graph_items = _extract_to_graph_items(doc, inferencer, force, cache_path)

    if dry_run or driver is None:
        return graph_items, "extract", [], None

    # Non-dry-run: wired in Plan 03-03
    raise NotImplementedError(
        "Non-dry-run Neo4j MERGE path is not yet wired.\n"
        "Run with --dry-run to use the extraction-only path.\n"
        "Full Neo4j support lands in Plan 03-03."
    )


# ---------------------------------------------------------------------------
# run_batch
# ---------------------------------------------------------------------------

def run_batch(args: Any) -> list[dict]:
    """Orchestrate batch ingestion of all manifest documents.

    Iterates manifest docs (or the single doc when ``args.doc_id`` is set),
    runs ``ingest_one_doc`` inside a per-doc ``try/except``, writes one JSON
    report per doc, and returns the list of report dicts for the caller to
    print a summary table.

    Args:
        args:  argparse.Namespace with attributes:
               dry_run, doc_id, inferencer, force, no_scoped_delete,
               report_dir, manifest, fail_fast, verbose, reset.

    Returns:
        list of per-doc report dicts (Pattern 2 schema from build_doc_report).

    Raises:
        NotImplementedError: when ``dry_run`` is False (until Plan 03-03).
    """
    if not args.dry_run:
        raise NotImplementedError(
            "Non-dry-run (live Neo4j) path is not yet wired.\n"
            "Run with --dry-run until Plan 03-03 lands."
        )

    report_dir = Path(args.report_dir if args.report_dir else "reports/batch")
    report_dir.mkdir(parents=True, exist_ok=True)

    output_dir = Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)

    driver = None  # dry-run only in this plan

    reports: list[dict] = []

    for doc in iter_manifest_docs(
        Path(args.manifest) if args.manifest else Path("data/raw/manifest.json"),
        getattr(args, "doc_id", None),
    ):
        started = datetime.now(timezone.utc)
        perf_start = perf_counter()

        error: dict | None = None
        graph_items: dict = {"nodes": [], "edges": []}
        stage = "extract"
        model: str | None = None

        with capture_warnings() as warnings:
            try:
                graph_items, stage, _, model = ingest_one_doc(
                    doc,
                    dry_run=args.dry_run,
                    inferencer=getattr(args, "inferencer", None),
                    force=getattr(args, "force", False),
                    output_dir=output_dir,
                    driver=driver,
                    scoped_delete=not getattr(args, "no_scoped_delete", False),
                )
            except Exception as exc:
                graph_items = {"nodes": [], "edges": []}
                stage = "extract"
                model = None
                log_failure(doc["doc_id"], stage, exc)
                error = {
                    "class": type(exc).__name__,
                    "message": str(exc),
                    "traceback_snippet": traceback.format_exc(limit=10),
                }

        finished = datetime.now(timezone.utc)
        perf_end = perf_counter()

        report = build_doc_report(
            doc=doc,
            graph_items=graph_items,
            started_at=started,
            finished_at=finished,
            inferencer=getattr(args, "inferencer", None),
            model=model,
            dry_run=args.dry_run,
            scoped_delete_ran=False,
            warnings=list(warnings),
            error=error,
            stage_completed=stage,
        )

        (report_dir / f"{doc['doc_id']}_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

        reports.append(report)

        if error and getattr(args, "fail_fast", False):
            break

    return reports
