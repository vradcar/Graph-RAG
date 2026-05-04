"""Failing tests for scripts/batch_ingest.py CLI (Task 2, TDD RED gate)."""
from __future__ import annotations

import subprocess
import sys
import pytest

pytestmark = pytest.mark.integration

PYTHON = sys.executable


def run_cli(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "scripts/batch_ingest.py", *args],
        capture_output=True,
        text=True,
        **kwargs,
    )


class TestBatchIngestCLI:
    def test_help_exits_zero(self):
        result = run_cli("--help")
        assert result.returncode == 0

    def test_help_lists_dry_run_flag(self):
        result = run_cli("--help")
        assert "--dry-run" in result.stdout

    def test_help_lists_doc_id_flag(self):
        result = run_cli("--help")
        assert "--doc-id" in result.stdout

    def test_help_lists_fail_fast_flag(self):
        result = run_cli("--help")
        assert "--fail-fast" in result.stdout

    def test_help_lists_inferencer_choices(self):
        result = run_cli("--help")
        assert "groq" in result.stdout

    def test_without_dry_run_exits_code_2(self):
        """Without --dry-run, script must exit 2 with a clear message."""
        result = run_cli()
        assert result.returncode == 2
        # Message should reference --dry-run or Plan 03-03
        combined = result.stdout + result.stderr
        assert "--dry-run" in combined or "03-03" in combined or "dry" in combined.lower()

    def test_build_arg_parser_importable(self):
        """build_arg_parser must be importable from the CLI module."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "batch_ingest", "scripts/batch_ingest.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "build_arg_parser")
        assert hasattr(mod, "print_summary")
        assert hasattr(mod, "main")

    def test_print_summary_outputs_header_and_totals(self, capsys):
        """print_summary prints column headers and a totals line."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "batch_ingest", "scripts/batch_ingest.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        sample_reports = [
            {
                "doc_id": "t9_install_guide",
                "status": "ok",
                "counts": {"nodes_total": 42, "edges_total": 87},
                "runtime_seconds": 7.103,
            }
        ]
        mod.print_summary(sample_reports)
        out = capsys.readouterr().out
        assert "t9_install_guide" in out
        assert "ok" in out
        # Totals line
        assert "1 ok" in out
