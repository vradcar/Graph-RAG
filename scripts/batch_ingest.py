"""Batch ingestion CLI — Phase 3 BATCH-01..03.

Assembles the full corpus in one command using the primitives from
Plan 03-01 (scoped delete, per-doc report, failure log) and the
orchestration core from Plan 03-02 (src/ingest/batch.py).

Usage:
    python scripts/batch_ingest.py --dry-run
    python scripts/batch_ingest.py --doc-id t9_install_guide --dry-run
    python scripts/batch_ingest.py --dry-run --inferencer groq
    python scripts/batch_ingest.py           # exits 2 — --dry-run required until Plan 03-03
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.ingest.batch import run_batch

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    """Return the fully-configured argument parser for batch_ingest."""
    parser = argparse.ArgumentParser(
        prog="batch_ingest",
        description=(
            "Batch-ingest the Honeywell HVAC corpus from data/raw/manifest.json.\n"
            "Writes one JSON report per doc to --report-dir (default reports/batch/).\n"
            "Use --dry-run to skip Neo4j and verify extraction only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help=(
            "Extract and build per-doc reports without touching Neo4j. "
            "Reads from cached data/processed/_<doc_id>_corpus.json when "
            "present; runs LLM extraction on miss."
        ),
    )

    parser.add_argument(
        "--doc-id",
        dest="doc_id",
        default=None,
        metavar="SLUG",
        help=(
            "Restrict the run to a single manifest entry identified by its "
            "doc_id slug (e.g. 't9_install_guide'). Still uses batch "
            "reporting — one report file is written for that doc only."
        ),
    )

    parser.add_argument(
        "--inferencer",
        dest="inferencer",
        default=None,
        choices=["groq", "openrouter", "gemini"],
        help=(
            "LLM backend for PDF extraction. "
            "'groq' uses GROQ_API_KEY (fastest). "
            "'openrouter' uses OPENROUTER_API_KEY. "
            "'gemini' uses GEMINI_API_KEY. "
            "Omit to auto-detect from available env-vars."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        dest="force",
        help=(
            "Bypass extraction cache and re-run LLM extraction for every "
            "doc even if data/processed/_<doc_id>_corpus.json already "
            "exists. Use after prompt or schema changes."
        ),
    )

    parser.add_argument(
        "--no-scoped-delete",
        action="store_true",
        dest="no_scoped_delete",
        help=(
            "Skip scoped-delete before re-merging (non-dry-run only). "
            "Useful for append-mode re-runs when prior data should be "
            "preserved. Wired in Plan 03-03."
        ),
    )

    parser.add_argument(
        "--report-dir",
        dest="report_dir",
        default="reports/batch",
        metavar="PATH",
        help="Directory for per-doc JSON reports (default: reports/batch/).",
    )

    parser.add_argument(
        "--manifest",
        dest="manifest",
        default="data/raw/manifest.json",
        metavar="PATH",
        help="Path to the manifest JSON file (default: data/raw/manifest.json).",
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        dest="fail_fast",
        help=(
            "Stop the loop on the first per-doc failure (default: off). "
            "When off, failures are isolated, logged to "
            "reports/ingest_failures.log, and remaining docs continue."
        ),
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        dest="verbose",
        help="Enable INFO-level logging for detailed extraction progress.",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        dest="reset",
        help=(
            "Wipe all Neo4j data before ingestion, then load fresh. "
            "Disables per-doc scoped delete inside the loop (one full wipe is sufficient)."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(reports: list[dict]) -> None:
    """Print a formatted summary table to stdout.

    Format::

        doc_id                           status   nodes   edges  runtime_s
        -------------------------------- -------- ------- ------- ----------
        t9_install_guide                 ok          42      87       7.103
        t6_pro_install                   ok          38      71       6.842
        ...
        summary: 4 ok / 0 fail / 0 skipped
    """
    COL_DOC = 32
    COL_STATUS = 8
    COL_NODES = 7
    COL_EDGES = 7
    COL_RUNTIME = 10

    header = (
        f"{'doc_id'.ljust(COL_DOC)} "
        f"{'status'.ljust(COL_STATUS)} "
        f"{'nodes'.rjust(COL_NODES)} "
        f"{'edges'.rjust(COL_EDGES)} "
        f"{'runtime_s'.rjust(COL_RUNTIME)}"
    )
    separator = (
        f"{'-' * COL_DOC} "
        f"{'-' * COL_STATUS} "
        f"{'-' * COL_NODES} "
        f"{'-' * COL_EDGES} "
        f"{'-' * COL_RUNTIME}"
    )

    print(header)
    print(separator)

    ok_count = fail_count = skip_count = 0

    for r in reports:
        doc_id = str(r.get("doc_id", ""))
        status = str(r.get("status", ""))
        counts = r.get("counts") or {}
        nodes = int(counts.get("nodes_total", 0))
        edges = int(counts.get("edges_total", 0))
        runtime = float(r.get("runtime_seconds", 0.0))

        print(
            f"{doc_id.ljust(COL_DOC)} "
            f"{status.ljust(COL_STATUS)} "
            f"{str(nodes).rjust(COL_NODES)} "
            f"{str(edges).rjust(COL_EDGES)} "
            f"{str(round(runtime, 3)).rjust(COL_RUNTIME)}"
        )

        if status == "ok":
            ok_count += 1
        elif status == "fail":
            fail_count += 1
        else:
            skip_count += 1

    print()
    print(f"summary: {ok_count} ok / {fail_count} fail / {skip_count} skipped")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an exit code."""
    load_dotenv()

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
    )

    try:
        reports = run_batch(args)
    except SystemExit as exc:
        # Neo4j connectivity failure — exit code 3
        if "Neo4j connection failed" in str(exc):
            print(f"error: {exc}", file=sys.stderr)
            return 3
        raise

    print_summary(reports)

    if not reports:
        print("warning: no documents processed (manifest empty or all filtered out)", file=sys.stderr)
        return 2
    exit_code = 0 if all(r.get("status") == "ok" for r in reports) else 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
