"""Integration tests for batch dry-run, report shape, and failure isolation.

Covers BATCH-01 (dry-run, no Neo4j), BATCH-02 (report shape), and
BATCH-03 (failure JSONL + loop continuation).

All tests use monkeypatched ingest_one_doc to avoid real LLM calls.
No Neo4j connection is required.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ingest.manifest import load_manifest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_GRAPH_ITEMS = {
    "nodes": [
        {"node_id": "n1", "kind": "Product"},
        {"node_id": "n2", "kind": "Spec"},
    ],
    "edges": [
        {"source_id": "n1", "target_id": "n2", "relation": "HAS_SPEC"},
    ],
}


def make_args(tmp_path: Path, **overrides) -> argparse.Namespace:
    """Factory for argparse.Namespace with sensible dry-run defaults."""
    defaults = dict(
        dry_run=True,
        doc_id=None,
        inferencer=None,
        force=False,
        no_scoped_delete=False,
        report_dir=str(tmp_path / "reports"),
        manifest="data/raw/manifest.json",
        fail_fast=False,
        verbose=False,
        reset=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def fake_ingest_ok(doc, *, dry_run, inferencer, force, output_dir, driver=None, scoped_delete=False):
    """Monkeypatch: always succeeds, returns minimal graph_items."""
    return FAKE_GRAPH_ITEMS, "extract", [], None


def make_fail_for(target_doc_id: str):
    """Return a monkeypatch that raises RuntimeError only for target_doc_id."""

    def _ingest(doc, *, dry_run, inferencer, force, output_dir, driver=None, scoped_delete=False):
        if doc["doc_id"] == target_doc_id:
            raise RuntimeError(f"simulated failure for {target_doc_id}")
        return FAKE_GRAPH_ITEMS, "extract", [], None

    return _ingest


# ---------------------------------------------------------------------------
# BATCH-01: dry-run walks all manifest docs, no Neo4j touched
# ---------------------------------------------------------------------------

class TestDryRunNoBatchInteraction:
    def test_dry_run_walks_all_manifest_docs(self, tmp_path):
        """run_batch with dry_run=True writes one report per manifest doc."""
        from src.ingest.batch import run_batch

        args = make_args(tmp_path)
        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest_ok):
            reports = run_batch(args)

        all_docs = load_manifest("data/raw/manifest.json")
        assert len(reports) == len(all_docs)

        report_dir = Path(args.report_dir)
        report_files = list(report_dir.glob("*_report.json"))
        assert len(report_files) == len(all_docs)

    def test_dry_run_does_not_touch_neo4j(self, tmp_path):
        """Dry-run completes without triggering neo4j.GraphDatabase.driver."""
        from src.ingest.batch import run_batch

        args = make_args(tmp_path)
        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest_ok), \
             patch("neo4j.GraphDatabase.driver", side_effect=AssertionError("Neo4j must not be touched in dry-run")):
            # Should not raise AssertionError
            reports = run_batch(args)

        assert len(reports) == 4

    def test_dry_run_writes_per_doc_json_to_data_processed(self, tmp_path):
        """After dry-run, data/processed/_t9_install_guide_corpus.json exists."""
        from src.ingest.batch import run_batch

        args = make_args(tmp_path, doc_id="t9_install_guide")
        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest_ok):
            run_batch(args)

        # The cache file should already exist (Phase 2 left it there)
        cache_path = Path("data/processed/_t9_install_guide_corpus.json")
        assert cache_path.exists(), f"Expected cache file at {cache_path}"


# ---------------------------------------------------------------------------
# BATCH-02: per-doc report schema (Pattern 2)
# ---------------------------------------------------------------------------

class TestReportSchema:
    REQUIRED_KEYS = {
        "doc_id", "filename", "started_at", "finished_at", "runtime_seconds",
        "status", "stage_completed", "inferencer", "model", "dry_run",
        "scoped_delete_ran", "counts", "warnings", "error",
    }

    def test_report_schema_matches_pattern_2(self, tmp_path):
        """Each report file has all 14 documented keys with correct types."""
        from src.ingest.batch import run_batch

        args = make_args(tmp_path)
        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest_ok):
            reports = run_batch(args)

        for r in reports:
            assert self.REQUIRED_KEYS.issubset(r.keys()), (
                f"Missing keys in report for {r.get('doc_id')}: "
                f"{self.REQUIRED_KEYS - r.keys()}"
            )
            counts = r["counts"]
            assert isinstance(counts.get("nodes_total"), int)
            assert isinstance(counts.get("nodes_by_kind"), dict)
            assert isinstance(counts.get("edges_total"), int)
            assert isinstance(counts.get("edges_by_relation"), dict)
            assert r["status"] in ("ok", "fail")
            assert isinstance(r["runtime_seconds"], float)


# ---------------------------------------------------------------------------
# BATCH-03: failure isolation + JSONL log
# ---------------------------------------------------------------------------

class TestFailureIsolation:
    def test_failure_appends_jsonl_and_continues(self, tmp_path):
        """Forced failure for one doc: loop continues; failures.log appended; failed report has status='fail'."""
        from src.ingest.batch import run_batch

        fail_log = tmp_path / "test_failures.log"
        args = make_args(tmp_path, fail_fast=False)

        with patch("src.ingest.batch.ingest_one_doc", side_effect=make_fail_for("t6_pro_install")), \
             patch("src.ingest.batch.log_failure") as mock_log:
            reports = run_batch(args)

        all_docs = load_manifest("data/raw/manifest.json")
        assert len(reports) == len(all_docs)

        statuses = {r["doc_id"]: r["status"] for r in reports}
        assert statuses["t6_pro_install"] == "fail"
        assert all(statuses[d["doc_id"]] == "ok" for d in all_docs if d["doc_id"] != "t6_pro_install")

        # log_failure called exactly once, for the failing doc
        assert mock_log.call_count == 1
        assert mock_log.call_args[0][0] == "t6_pro_install"

        # Failed report must have error.class field
        failed_report = next(r for r in reports if r["doc_id"] == "t6_pro_install")
        assert failed_report["error"]["class"] == "RuntimeError"

    def test_fail_fast_stops_on_first_error(self, tmp_path):
        """With fail_fast=True, run_batch stops after first failure."""
        from src.ingest.batch import run_batch

        # t9_install_guide is first in manifest — makes it the target
        args = make_args(tmp_path, fail_fast=True)

        with patch("src.ingest.batch.ingest_one_doc", side_effect=make_fail_for("t9_install_guide")):
            reports = run_batch(args)

        # Should have exactly 1 report (the failed doc)
        assert len(reports) == 1
        assert reports[0]["doc_id"] == "t9_install_guide"
        assert reports[0]["status"] == "fail"

    def test_doc_id_filter_runs_one_doc(self, tmp_path):
        """--doc-id restricts run to exactly one doc and writes one report file."""
        from src.ingest.batch import run_batch

        args = make_args(tmp_path, doc_id="t6_pro_install")
        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest_ok):
            reports = run_batch(args)

        assert len(reports) == 1
        assert reports[0]["doc_id"] == "t6_pro_install"

        report_dir = Path(args.report_dir)
        report_files = list(report_dir.glob("*_report.json"))
        assert len(report_files) == 1
        assert report_files[0].name == "t6_pro_install_report.json"

    def test_unknown_doc_id_lists_available(self, tmp_path):
        """Bogus --doc-id raises ValueError listing all valid doc_ids."""
        from src.ingest.batch import run_batch

        args = make_args(tmp_path, doc_id="bogus_id")
        with pytest.raises(ValueError) as exc_info:
            run_batch(args)

        msg = str(exc_info.value)
        # All 4 valid doc_ids should appear in the error message
        assert "t9_install_guide" in msg
        assert "t6_pro_install" in msg
        assert "thp9045_wiring_module" in msg
        assert "t10_pro_user_guide" in msg
