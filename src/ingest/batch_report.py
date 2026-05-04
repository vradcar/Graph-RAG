"""Per-doc report builder + warning-capture context manager for batch ingest.

Used by ``scripts/batch_ingest.py`` (Wave 1) to emit BATCH-02 per-doc reports.

Public API:
    - summarize_counts(graph_items)       -> dict
    - build_doc_report(...)               -> dict (Pattern 2 schema)
    - capture_warnings(loggers=...)       -> context manager yielding list[dict]

All three functions are pure (no Neo4j, no PDFs) and unit-testable in isolation.
"""

from __future__ import annotations

import datetime as _dt
import logging
from collections import Counter
from contextlib import contextmanager
from typing import Any, Iterable, Iterator

__all__ = ["summarize_counts", "build_doc_report", "capture_warnings"]


# Documented default loggers for capture_warnings — covers the four modules
# whose WARNING-level output is meaningful to the per-doc report.
DEFAULT_WARNING_LOGGERS: tuple[str, ...] = (
    "src.pipeline.ingest",
    "src.graph.neo4j_loader",
    "src.ingest.entity_extractor",
    "src.ingest.normalizer",
)


def summarize_counts(graph_items: dict) -> dict:
    """Aggregate node/edge totals from in-memory graph_items.

    No Neo4j read required — works in --dry-run.

    Returns::

        {
            "nodes_total":       int,
            "edges_total":       int,
            "nodes_by_kind":     {kind: int},
            "edges_by_relation": {relation: int},
        }

    Missing/empty ``kind`` collapses to ``"Unknown"``; missing ``relation``
    collapses to ``"UNKNOWN"`` so malformed entries don't crash the batch.
    """
    nodes = graph_items.get("nodes", []) or []
    edges = graph_items.get("edges", []) or []
    return {
        "nodes_total": len(nodes),
        "edges_total": len(edges),
        "nodes_by_kind": dict(
            Counter((n.get("kind") or "Unknown") for n in nodes)
        ),
        "edges_by_relation": dict(
            Counter((e.get("relation") or "UNKNOWN") for e in edges)
        ),
    }


def _to_iso_z(value: Any) -> str:
    """Normalise a datetime (or ISO string) to UTC ISO-8601 ending in 'Z'."""
    if isinstance(value, str):
        # Parse and normalise rather than blindly append 'Z' — a non-UTC offset
        # or a naive string would produce a wrong timestamp otherwise.
        value = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Fall through to datetime branch
    if isinstance(value, _dt.datetime):
        if value.tzinfo is None:
            raise ValueError(f"Naive datetime passed to _to_iso_z: {value!r}")
        return value.astimezone(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    raise TypeError(f"Unsupported timestamp type: {type(value)!r}")


def _runtime_seconds(started_at: Any, finished_at: Any) -> float:
    """Compute runtime as float seconds rounded to 3 decimals."""
    if isinstance(started_at, (int, float)) and isinstance(finished_at, (int, float)):
        return round(float(finished_at) - float(started_at), 3)
    if isinstance(started_at, _dt.datetime) and isinstance(finished_at, _dt.datetime):
        delta = (finished_at - started_at).total_seconds()
        return round(delta, 3)
    raise TypeError(
        "started_at and finished_at must be both datetimes or both float perf_counter values"
    )


def build_doc_report(
    *,
    doc: dict,
    graph_items: dict,
    started_at: Any,
    finished_at: Any,
    inferencer: str,
    model: str,
    dry_run: bool,
    scoped_delete_ran: bool,
    warnings: list[dict],
    error: dict | None,
    stage_completed: str | None = None,
) -> dict:
    """Assemble the Pattern 2 per-doc report dict.

    ``doc`` is a manifest entry (must contain ``doc_id`` and ``filename``).
    ``started_at`` / ``finished_at`` accept either datetime objects (preferred)
    or float ``time.perf_counter()`` values.

    ``status`` derives from ``error``:
        - ``"ok"``   when ``error is None``
        - ``"fail"`` otherwise

    ``stage_completed`` defaults to ``"neo4j_load"`` on success and to
    ``"extract"`` on failure unless the caller overrides via kwarg.
    """
    status = "fail" if error else "ok"
    if stage_completed is None:
        stage_completed = "neo4j_load" if status == "ok" else "extract"

    return {
        "doc_id": doc.get("doc_id"),
        "filename": doc.get("filename"),
        "started_at": _to_iso_z(started_at),
        "finished_at": _to_iso_z(finished_at),
        "runtime_seconds": _runtime_seconds(started_at, finished_at),
        "status": status,
        "stage_completed": stage_completed,
        "inferencer": inferencer,
        "model": model,
        "dry_run": dry_run,
        "scoped_delete_ran": scoped_delete_ran,
        "counts": summarize_counts(graph_items),
        "warnings": list(warnings or []),
        "error": error,
    }


@contextmanager
def capture_warnings(
    loggers: Iterable[str] = DEFAULT_WARNING_LOGGERS,
) -> Iterator[list[dict]]:
    """Capture WARNING+ records emitted by the named loggers without altering
    normal log output.

    Yields a list that is mutated as records are emitted. INFO-level records
    are NOT captured. Handlers are removed in ``finally`` so an exception
    inside the block still leaves the logging tree clean.
    """
    records: list[dict] = []

    class _Sink(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno >= logging.WARNING:
                records.append(
                    {
                        "logger": record.name,
                        "level": record.levelname,
                        "message": record.getMessage(),
                    }
                )

    sink = _Sink(level=logging.WARNING)
    targets = [logging.getLogger(n) for n in loggers]
    for lg in targets:
        lg.addHandler(sink)
    try:
        yield records
    finally:
        for lg in targets:
            lg.removeHandler(sink)
