"""Unit tests for src.ingest.batch_report.

Covers:
    - summarize_counts: Counter aggregation, missing-key fallback
    - build_doc_report: Pattern 2 schema, ok/fail status, ISO Z timestamps
    - capture_warnings: WARNING+ capture, handler cleanup, configurable loggers
"""

from __future__ import annotations

import datetime as _dt
import logging

import pytest

from src.ingest.batch_report import (
    build_doc_report,
    capture_warnings,
    summarize_counts,
)


# --- summarize_counts -------------------------------------------------------


def test_summarize_counts_groups_nodes_by_kind():
    out = summarize_counts(
        {
            "nodes": [
                {"kind": "Product"},
                {"kind": "Product"},
                {"kind": "WiringTerminal"},
            ],
            "edges": [],
        }
    )
    assert out["nodes_total"] == 3
    assert out["nodes_by_kind"] == {"Product": 2, "WiringTerminal": 1}
    assert out["edges_total"] == 0
    assert out["edges_by_relation"] == {}


def test_summarize_counts_groups_edges_by_relation():
    out = summarize_counts(
        {
            "nodes": [],
            "edges": [
                {"relation": "COMPATIBLE_WITH"},
                {"relation": "COMPATIBLE_WITH"},
                {},  # missing relation -> "UNKNOWN"
                {"foo": "bar"},  # missing kind on a node-style dict
            ],
        }
    )
    assert out["edges_total"] == 4
    assert out["edges_by_relation"] == {"COMPATIBLE_WITH": 2, "UNKNOWN": 2}


def test_summarize_counts_missing_kind_collapses_to_unknown():
    out = summarize_counts({"nodes": [{}, {"kind": "Product"}], "edges": []})
    assert out["nodes_by_kind"] == {"Unknown": 1, "Product": 1}


# --- build_doc_report -------------------------------------------------------


_T0 = _dt.datetime(2026, 5, 3, 19, 14, 2, 118_000, tzinfo=_dt.timezone.utc)
_T1 = _dt.datetime(2026, 5, 3, 19, 14, 9, 221_000, tzinfo=_dt.timezone.utc)


def _fake_items():
    return {
        "nodes": [{"kind": "Product"}, {"kind": "Product"}],
        "edges": [{"relation": "COMPATIBLE_WITH"}],
    }


def test_build_doc_report_status_ok_shape():
    rep = build_doc_report(
        doc={"doc_id": "thp9045", "filename": "thp9045.pdf"},
        graph_items=_fake_items(),
        started_at=_T0,
        finished_at=_T1,
        inferencer="groq",
        model="llama-3.3-70b-versatile",
        dry_run=False,
        scoped_delete_ran=True,
        warnings=[],
        error=None,
    )
    expected_keys = {
        "doc_id",
        "filename",
        "started_at",
        "finished_at",
        "runtime_seconds",
        "status",
        "stage_completed",
        "inferencer",
        "model",
        "dry_run",
        "scoped_delete_ran",
        "counts",
        "warnings",
        "error",
    }
    assert set(rep.keys()) == expected_keys
    assert rep["status"] == "ok"
    assert rep["doc_id"] == "thp9045"
    assert rep["filename"] == "thp9045.pdf"
    assert rep["counts"]["nodes_total"] == 2
    assert rep["counts"]["edges_total"] == 1
    assert rep["error"] is None


def test_build_doc_report_status_fail_shape():
    err = {"class": "ValidationError", "message": "y", "traceback_snippet": "z"}
    rep = build_doc_report(
        doc={"doc_id": "x", "filename": "x.pdf"},
        graph_items={"nodes": [], "edges": []},
        started_at=_T0,
        finished_at=_T1,
        inferencer="groq",
        model="m",
        dry_run=False,
        scoped_delete_ran=False,
        warnings=[],
        error=err,
    )
    assert rep["status"] == "fail"
    assert rep["error"] == err


def test_build_doc_report_runtime_seconds_rounded():
    rep = build_doc_report(
        doc={"doc_id": "x", "filename": "x.pdf"},
        graph_items={"nodes": [], "edges": []},
        started_at=_T0,
        finished_at=_T1,
        inferencer="groq",
        model="m",
        dry_run=False,
        scoped_delete_ran=False,
        warnings=[],
        error=None,
    )
    assert rep["runtime_seconds"] == 7.103


def test_build_doc_report_started_at_iso_z():
    rep = build_doc_report(
        doc={"doc_id": "x", "filename": "x.pdf"},
        graph_items={"nodes": [], "edges": []},
        started_at=_T0,
        finished_at=_T1,
        inferencer="groq",
        model="m",
        dry_run=False,
        scoped_delete_ran=False,
        warnings=[],
        error=None,
    )
    assert isinstance(rep["started_at"], str)
    assert rep["started_at"].endswith("Z")
    assert rep["finished_at"].endswith("Z")
    # Sanity: starts with the date
    assert rep["started_at"].startswith("2026-05-03T19:14:02")


# --- capture_warnings -------------------------------------------------------


def test_capture_warnings_collects_warning_and_above():
    lg = logging.getLogger("src.pipeline.ingest")
    with capture_warnings() as records:
        lg.info("info-msg")
        lg.warning("warn-msg")
        lg.error("err-msg")
    levels = [r["level"] for r in records]
    msgs = [r["message"] for r in records]
    assert "INFO" not in levels
    assert "WARNING" in levels
    assert "ERROR" in levels
    assert "warn-msg" in msgs
    assert "err-msg" in msgs
    # handler removed on exit
    lg.warning("post-exit")
    assert all(r["message"] != "post-exit" for r in records)


def test_capture_warnings_uses_documented_loggers():
    # Caller can override loggers list via kwarg
    lg_a = logging.getLogger("custom.logger.a")
    lg_b = logging.getLogger("src.pipeline.ingest")
    with capture_warnings(loggers=("custom.logger.a",)) as records:
        lg_a.warning("yes")
        lg_b.warning("no")
    msgs = [r["message"] for r in records]
    assert "yes" in msgs
    assert "no" not in msgs


def test_capture_warnings_cleans_up_on_exception():
    lg = logging.getLogger("src.pipeline.ingest")
    handlers_before = list(lg.handlers)
    with pytest.raises(RuntimeError):
        with capture_warnings() as _records:
            raise RuntimeError("boom")
    assert lg.handlers == handlers_before
