"""
Tests for src/ingest/pdf_parser.py

Integration tests run against the real T9 PDF at data/raw/t9-thermostat.pdf.
No mocking of fitz/pdfplumber — these tests validate real extraction behavior.
"""
import pytest
from pathlib import Path

PDF_PATH = "data/raw/t9-thermostat.pdf"


@pytest.fixture(scope="module")
def pages():
    """Extract all pages once for the module; reuse across tests."""
    from src.ingest.pdf_parser import extract_page_content
    return extract_page_content(PDF_PATH)


def test_extract_page_content_returns_pages(pages):
    assert len(pages) >= 1, "Expected at least 1 page from T9 PDF"


def test_page_dict_has_required_keys(pages):
    for page in pages:
        assert "page_num" in page, f"Missing 'page_num' on page {page}"
        assert "prose" in page, f"Missing 'prose' on page {page}"
        assert "tables" in page, f"Missing 'tables' on page {page}"


def test_page_num_is_one_indexed(pages):
    assert pages[0]["page_num"] == 1, f"First page_num should be 1, got {pages[0]['page_num']}"


def test_prose_is_string(pages):
    for page in pages:
        assert isinstance(page["prose"], str), (
            f"prose on page {page['page_num']} is {type(page['prose'])}, expected str"
        )


def test_tables_is_list(pages):
    for page in pages:
        assert isinstance(page["tables"], list), (
            f"tables on page {page['page_num']} is {type(page['tables'])}, expected list"
        )


def test_tables_are_nested_lists_not_strings(pages):
    """Critical: tables must be cell-by-cell (nested list), not fused column strings."""
    tables_found = False
    for page in pages:
        for table in page["tables"]:
            tables_found = True
            assert isinstance(table, list), f"Table is not a list: {type(table)}"
            for row in table:
                assert isinstance(row, list), (
                    f"Table row is not a list (got {type(row)}). "
                    "This suggests extract_text() was used instead of extract_tables()."
                )
    if not tables_found:
        pytest.skip("No tables found in PDF — table structure test skipped")


def test_missing_pdf_raises_file_not_found():
    from src.ingest.pdf_parser import extract_page_content
    with pytest.raises(FileNotFoundError):
        extract_page_content("data/raw/nonexistent_file_xyzzy.pdf")


def test_format_page_for_llm_returns_string(pages):
    from src.ingest.pdf_parser import format_page_for_llm
    for page in pages:
        result = format_page_for_llm(page)
        assert isinstance(result, str)
    # At least one page should have non-empty output
    non_empty = [p for p in pages if format_page_for_llm(p).strip()]
    assert len(non_empty) >= 1, "All pages produced empty LLM format output"
