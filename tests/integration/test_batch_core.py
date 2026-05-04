"""Failing tests for src/ingest/batch.py (Task 1, TDD RED gate).

These tests verify ingest_one_doc, iter_manifest_docs, and run_batch
before the implementation file exists.
"""
from __future__ import annotations

import argparse
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_args(tmp_path: Path, **overrides) -> argparse.Namespace:
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


FAKE_GRAPH_ITEMS = {"nodes": [{"node_id": "n1", "kind": "Product"}], "edges": []}


# ---------------------------------------------------------------------------
# iter_manifest_docs
# ---------------------------------------------------------------------------

class TestIterManifestDocs:
    def test_yields_all_docs_when_no_filter(self):
        from src.ingest.batch import iter_manifest_docs
        docs = list(iter_manifest_docs(Path("data/raw/manifest.json"), None))
        assert len(docs) == 4

    def test_yields_single_doc_when_filter_matches(self):
        from src.ingest.batch import iter_manifest_docs
        docs = list(iter_manifest_docs(Path("data/raw/manifest.json"), "t9_install_guide"))
        assert len(docs) == 1
        assert docs[0]["doc_id"] == "t9_install_guide"

    def test_raises_value_error_for_unknown_doc_id(self):
        from src.ingest.batch import iter_manifest_docs
        with pytest.raises(ValueError) as exc_info:
            list(iter_manifest_docs(Path("data/raw/manifest.json"), "bogus_id"))
        msg = str(exc_info.value)
        # Should list available doc_ids
        assert "t9_install_guide" in msg
        assert "t6_pro_install" in msg


# ---------------------------------------------------------------------------
# ingest_one_doc
# ---------------------------------------------------------------------------

class TestIngestOneDoc:
    def test_dry_run_returns_graph_items_and_stage_extract(self, tmp_path):
        """dry_run=True returns graph_items with stage_completed='extract'."""
        from src.ingest.batch import ingest_one_doc

        doc = {"doc_id": "t9_install_guide", "filename": "t9-thermostat.pdf"}
        output_dir = Path("data/processed")

        with patch("src.ingest.batch._extract_to_graph_items", return_value=FAKE_GRAPH_ITEMS):
            result = ingest_one_doc(doc, dry_run=True, inferencer=None, force=False,
                                     output_dir=output_dir, driver=None)

        graph_items, stage, warnings, model = result
        assert stage == "extract"
        assert "nodes" in graph_items
        assert "edges" in graph_items

    def test_dry_run_allows_none_driver(self, tmp_path):
        """dry_run=True must not raise when driver=None."""
        from src.ingest.batch import ingest_one_doc

        doc = {"doc_id": "t9_install_guide", "filename": "t9-thermostat.pdf"}
        output_dir = Path("data/processed")

        with patch("src.ingest.batch._extract_to_graph_items", return_value=FAKE_GRAPH_ITEMS):
            # Should not raise
            result = ingest_one_doc(doc, dry_run=True, inferencer=None, force=False,
                                     output_dir=output_dir, driver=None)
        assert result is not None

    def test_non_dry_run_raises_not_implemented(self, tmp_path):
        """Non-dry-run branch is stubbed until Plan 03-03."""
        from src.ingest.batch import run_batch

        args = make_args(tmp_path, dry_run=False)
        with pytest.raises(NotImplementedError) as exc_info:
            run_batch(args)
        assert "03-03" in str(exc_info.value) or "Plan" in str(exc_info.value)


# ---------------------------------------------------------------------------
# run_batch
# ---------------------------------------------------------------------------

class TestRunBatch:
    def test_run_batch_dry_run_returns_reports_list(self, tmp_path):
        """run_batch returns a list of 4 reports (one per manifest doc)."""
        from src.ingest.batch import run_batch

        def fake_ingest(doc, *, dry_run, inferencer, force, output_dir, driver=None, scoped_delete=False):
            return FAKE_GRAPH_ITEMS, "extract", [], None

        args = make_args(tmp_path)
        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest):
            reports = run_batch(args)

        assert len(reports) == 4

    def test_run_batch_writes_report_files(self, tmp_path):
        """run_batch writes one JSON file per doc into report_dir."""
        from src.ingest.batch import run_batch

        def fake_ingest(doc, *, dry_run, inferencer, force, output_dir, driver=None, scoped_delete=False):
            return FAKE_GRAPH_ITEMS, "extract", [], None

        args = make_args(tmp_path)
        report_dir = Path(args.report_dir)
        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest):
            run_batch(args)

        report_files = list(report_dir.glob("*_report.json"))
        assert len(report_files) == 4

    def test_run_batch_failure_isolated_loop_continues(self, tmp_path):
        """When one doc fails, run continues for remaining docs."""
        from src.ingest.batch import run_batch

        call_count = {"n": 0}

        def fake_ingest(doc, *, dry_run, inferencer, force, output_dir, driver=None, scoped_delete=False):
            call_count["n"] += 1
            if doc["doc_id"] == "t6_pro_install":
                raise RuntimeError("simulated failure")
            return FAKE_GRAPH_ITEMS, "extract", [], None

        args = make_args(tmp_path, fail_fast=False)
        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest):
            reports = run_batch(args)

        assert len(reports) == 4
        statuses = {r["doc_id"]: r["status"] for r in reports}
        assert statuses["t6_pro_install"] == "fail"
        assert statuses["t9_install_guide"] == "ok"

    def test_run_batch_fail_fast_stops_on_first_error(self, tmp_path):
        """With fail_fast=True, stops after first failure."""
        from src.ingest.batch import run_batch

        def fake_ingest(doc, *, dry_run, inferencer, force, output_dir, driver=None, scoped_delete=False):
            if doc["doc_id"] == "t9_install_guide":
                raise RuntimeError("fail first doc")
            return FAKE_GRAPH_ITEMS, "extract", [], None

        args = make_args(tmp_path, fail_fast=True)
        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest):
            reports = run_batch(args)

        # Only one report (the failed doc) should be present
        assert len(reports) == 1
        assert reports[0]["status"] == "fail"

    def test_run_batch_failure_appends_to_failure_log(self, tmp_path):
        """Failed docs are logged to the JSONL failure log."""
        from src.ingest.batch import run_batch

        def fake_ingest(doc, *, dry_run, inferencer, force, output_dir, driver=None, scoped_delete=False):
            if doc["doc_id"] == "t6_pro_install":
                raise RuntimeError("log-me")
            return FAKE_GRAPH_ITEMS, "extract", [], None

        failure_log = tmp_path / "failures.log"
        args = make_args(tmp_path, fail_fast=False)

        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest), \
             patch("src.ingest.batch.log_failure") as mock_log:
            run_batch(args)

        # log_failure should have been called exactly once (for t6_pro_install)
        assert mock_log.call_count == 1
        called_doc_id = mock_log.call_args[0][0]
        assert called_doc_id == "t6_pro_install"

    def test_run_batch_doc_id_filter_runs_single_doc(self, tmp_path):
        """--doc-id restricts run to exactly one doc."""
        from src.ingest.batch import run_batch

        def fake_ingest(doc, *, dry_run, inferencer, force, output_dir, driver=None, scoped_delete=False):
            return FAKE_GRAPH_ITEMS, "extract", [], None

        args = make_args(tmp_path, doc_id="t6_pro_install")
        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest):
            reports = run_batch(args)

        assert len(reports) == 1
        assert reports[0]["doc_id"] == "t6_pro_install"

    def test_run_batch_report_has_status_ok(self, tmp_path):
        """Successful docs produce reports with status='ok'."""
        from src.ingest.batch import run_batch

        def fake_ingest(doc, *, dry_run, inferencer, force, output_dir, driver=None, scoped_delete=False):
            return FAKE_GRAPH_ITEMS, "extract", [], None

        args = make_args(tmp_path)
        with patch("src.ingest.batch.ingest_one_doc", side_effect=fake_ingest):
            reports = run_batch(args)

        for r in reports:
            assert r["status"] == "ok"
