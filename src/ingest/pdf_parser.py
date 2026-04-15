"""
PDF parser stub — full implementation provided by plan 03.

format_page_for_llm is defined here so entity_extractor.py can import it.
Plan 03 will replace this file with the full extract_page_content() implementation.
"""
from typing import Any


def format_page_for_llm(page: dict[str, Any]) -> str:
    """
    Format a page dict as a string for the LLM prompt.

    Args:
        page: dict with keys page_num (int), prose (str), tables (list)

    Returns:
        Formatted string combining prose and table text.
    """
    parts = []
    prose = page.get("prose", "").strip()
    if prose:
        parts.append(prose)

    tables = page.get("tables", [])
    for table in tables:
        for row in table:
            row_text = " | ".join(str(cell) if cell is not None else "" for cell in row)
            parts.append(row_text)

    return "\n".join(parts)


def extract_page_content(pdf_path: str) -> list[dict]:
    """
    Extract page content from a PDF file.

    Stub — full implementation in plan 03.
    """
    raise NotImplementedError("extract_page_content() — implemented in plan 03")
