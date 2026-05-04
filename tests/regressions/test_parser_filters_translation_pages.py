"""Regression: THP9045 is trilingual (EN pp 1-4, FR 5-8, ES 9-12).
Manifest declares pages=[1,4]; extract_page_content(pages=(1,4)) MUST return only those pages."""
from pathlib import Path
import pytest
from src.ingest.pdf_parser import extract_page_content

PDF = Path("data/raw/thp9045-wiring-module.pdf")


@pytest.mark.skipif(not PDF.exists(), reason="THP9045 PDF not present")
def test_pages_filter_returns_only_english_range():
    pages = extract_page_content(str(PDF), pages=(1, 4))
    assert len(pages) == 4
    assert [p["page_num"] for p in pages] == [1, 2, 3, 4]


@pytest.mark.skipif(not PDF.exists(), reason="THP9045 PDF not present")
def test_default_returns_all_12_pages():
    pages = extract_page_content(str(PDF))
    assert len(pages) == 12
