"""SC-3: pdf_parser + entity_extractor + normalizer ingest each new PDF without
unhandled exception. Uses the same skip-if-unreachable pattern as Phase 1
integration tests (Groq key required for live extraction; if absent, the LLM
extraction step is skipped but the parser smoke still runs)."""
import os
from pathlib import Path
import pytest

from src.ingest.manifest import get_doc
from src.ingest.pdf_parser import extract_page_content

NEW_DOC_IDS = ["t6_pro_install", "thp9045_wiring_module", "t10_pro_user_guide"]


@pytest.mark.parametrize("doc_id", NEW_DOC_IDS)
def test_parser_smoke_each_pdf(doc_id):
    doc = get_doc(doc_id)
    pdf_path = Path("data/raw") / doc["filename"]
    if not pdf_path.exists():
        pytest.skip(f"PDF missing: {pdf_path}")
    pages_filter = tuple(doc["pages"]) if doc.get("pages") else None
    pages = extract_page_content(str(pdf_path), pages=pages_filter)
    assert len(pages) > 0, f"{doc_id} returned 0 pages"
    for p in pages:
        assert "page_num" in p and "prose" in p and "tables" in p


@pytest.mark.integration
@pytest.mark.parametrize("doc_id", NEW_DOC_IDS)
def test_extractor_smoke_first_page(doc_id):
    """One LLM call per PDF -- proves extract_from_page is rejection-safe end-to-end."""
    if not (os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")):
        pytest.skip("No LLM API key set")
    from src.ingest.entity_extractor import build_client, extract_from_page, ExtractionResult
    doc = get_doc(doc_id)
    pdf_path = Path("data/raw") / doc["filename"]
    if not pdf_path.exists():
        pytest.skip(f"PDF missing: {pdf_path}")
    pages_filter = tuple(doc["pages"]) if doc.get("pages") else None
    pages = extract_page_content(str(pdf_path), pages=pages_filter)
    provider = "groq" if os.getenv("GROQ_API_KEY") else "openai"
    client = build_client(provider)
    model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile" if provider == "groq" else "gpt-4o-mini")
    result = extract_from_page(client, model, pages[0], doc_id=doc_id)
    assert isinstance(result, ExtractionResult)
