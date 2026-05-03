"""Regression: T6 Pro inline `[N]` footnote markers must be stripped at parse time
so downstream node_id slugs are not polluted (e.g., 'terminal-r-2', 'power-1')."""
from pathlib import Path
from src.ingest.pdf_parser import _strip_footnote_markers

FIXTURE = Path("tests/fixtures/regressions/t6_footnote_sample.txt")


def test_no_bracketed_digits_remain():
    raw = FIXTURE.read_text()
    cleaned = _strip_footnote_markers(raw)
    # the unfixed code path leaves these markers in; the fix removes them
    import re
    assert re.search(r"\[\d+\]", cleaned) is None, cleaned


def test_surrounding_text_preserved():
    cleaned = _strip_footnote_markers("Power input [1] is 24VAC.")
    assert "Power input" in cleaned
    assert "24VAC" in cleaned
