"""
PDF parser for T9 thermostat documentation.

Uses a dual-extraction strategy:
- pymupdf (fitz): prose text extraction via page.get_text("text")
- pdfplumber: table extraction via page.extract_tables() — cell-by-cell, not fused

NEVER use pdfplumber.page.extract_text() for tables — it fuses columns.
"""
from pathlib import Path
from typing import Any

import fitz          # pymupdf
import pdfplumber


def extract_page_content(pdf_path: str) -> list[dict[str, Any]]:
    """
    Extract text and tables from every page of the given PDF.

    Returns a list of page dicts:
        {
            "page_num": int,         # 1-indexed
            "prose": str,            # pymupdf text — good for prose sections
            "tables": list[list[list[str | None]]],  # pdfplumber tables — cell-by-cell
        }

    Args:
        pdf_path: Path to the PDF file (e.g., "data/raw/t9-thermostat.pdf")

    Raises:
        FileNotFoundError: If the PDF does not exist at pdf_path
        RuntimeError: If either library fails to open the file
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    pages: list[dict[str, Any]] = []

    pdf_mupdf = fitz.open(str(path))
    try:
        with pdfplumber.open(str(path)) as pdf_plumber:
            for page_num, (page_plumber, page_fitz) in enumerate(
                zip(pdf_plumber.pages, pdf_mupdf), start=1
            ):
                prose: str = page_fitz.get_text("text")
                tables: list[list[list[str | None]]] = page_plumber.extract_tables()
                pages.append({
                    "page_num": page_num,
                    "prose": prose,
                    "tables": tables,
                })
    finally:
        pdf_mupdf.close()

    return pages


def format_page_for_llm(page: dict[str, Any]) -> str:
    """
    Format a page dict into a single string suitable for the LLM extraction prompt.

    Tables are stringified as pipe-delimited rows so structure is preserved.
    """
    parts: list[str] = []

    if page["prose"].strip():
        parts.append(f"=== Page {page['page_num']} — Text ===\n{page['prose'].strip()}")

    if page["tables"]:
        for table_idx, table in enumerate(page["tables"], start=1):
            rows = []
            for row in table:
                cells = [str(cell).strip() if cell is not None else "" for cell in row]
                rows.append(" | ".join(cells))
            table_str = "\n".join(rows)
            parts.append(
                f"=== Page {page['page_num']} — Table {table_idx} ===\n{table_str}"
            )

    return "\n\n".join(parts)
