"""Unit tests for src.ingest.failure_log.log_failure (BATCH-03).

All assertions use tmp_path so the real ``reports/ingest_failures.log`` is
never touched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.ingest.failure_log import log_failure


def _read_lines(p: Path) -> list[str]:
    return p.read_text(encoding="utf-8").splitlines(keepends=True)


def test_writes_one_jsonl_line_per_call(tmp_path):
    log_path = tmp_path / "ingest_failures.log"
    log_failure("doc_x", "extract", ValueError("boom"), log_path=log_path)
    lines = _read_lines(log_path)
    assert len(lines) == 1
    assert lines[0].endswith("\n")
    parsed = json.loads(lines[0])
    assert parsed["doc_id"] == "doc_x"


def test_entry_has_all_required_fields(tmp_path):
    log_path = tmp_path / "f.log"
    log_failure("doc_x", "extract", ValueError("boom"), log_path=log_path)
    entry = json.loads(_read_lines(log_path)[0])
    assert set(entry.keys()) >= {
        "ts",
        "doc_id",
        "stage",
        "error_class",
        "message",
        "snippet",
    }
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", entry["ts"])
    assert entry["error_class"] == "ValueError"
    assert entry["message"] == "boom"
    assert isinstance(entry["snippet"], str)
    assert len(entry["snippet"]) > 0


def test_appends_does_not_overwrite(tmp_path):
    log_path = tmp_path / "f.log"
    log_failure("doc_a", "extract", ValueError("a"), log_path=log_path)
    line1 = _read_lines(log_path)[0]
    log_failure("doc_b", "load", RuntimeError("b"), log_path=log_path)
    lines = _read_lines(log_path)
    assert len(lines) == 2
    assert lines[0] == line1
    assert json.loads(lines[1])["doc_id"] == "doc_b"


def test_creates_parent_dir(tmp_path):
    nested = tmp_path / "reports" / "subdir" / "ingest_failures.log"
    assert not nested.parent.exists()
    log_failure("doc_x", "extract", ValueError("x"), log_path=nested)
    assert nested.exists()


def test_accepts_pathlib_override(tmp_path):
    custom = tmp_path / "custom.log"
    returned = log_failure("doc_x", "extract", ValueError("x"), log_path=custom)
    assert custom.exists()
    assert returned == custom


def test_handles_unicode_message(tmp_path):
    log_path = tmp_path / "f.log"
    log_failure("doc_x", "extract", ValueError("café"), log_path=log_path)
    raw = log_path.read_text(encoding="utf-8")
    # ensure_ascii=False -> the literal char survives
    assert "café" in raw
    entry = json.loads(_read_lines(log_path)[0])
    assert entry["message"] == "café"


def test_snippet_includes_real_traceback_when_in_except(tmp_path):
    log_path = tmp_path / "f.log"
    try:
        raise RuntimeError("x")
    except RuntimeError as exc:
        log_failure("doc_x", "extract", exc, log_path=log_path)
    entry = json.loads(_read_lines(log_path)[0])
    assert "RuntimeError" in entry["snippet"]
    assert "Traceback" in entry["snippet"]
