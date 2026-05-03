import os
import subprocess
import sys
from pathlib import Path
import pytest

from src.ingest.manifest import get_doc

# T9 is listed first so it's in Neo4j before the new PDFs are loaded.
# Shared nodes (wiring configs, HVAC system types, product cross-refs) then
# accumulate source_docs entries from both T9 and the new docs, forming the
# SC-2 cross-doc bridges that test_cross_doc_bridges.py asserts.
_ALL_CORPUS_IDS = [
    "t9_install_guide",
    "t6_pro_install",
    "thp9045_wiring_module",
    "t10_pro_user_guide",
]
_PROCESSED = Path("data/processed")

# Which LLM backend the corpus ingest fixture should use.
# Override with `INFERENCER=openrouter pytest ...` to dodge Groq daily quotas.
_INFERENCER = os.getenv("INFERENCER", "groq")
_KEY_VAR = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
}.get(_INFERENCER)


@pytest.fixture(scope="session")
def corpus_ingested(neo4j_driver):
    """Session-scoped: ingest T9 + 3 new PDFs into Neo4j. Shared by SC-2 and SC-3 tests."""
    if _KEY_VAR is None:
        pytest.skip(f"Unknown INFERENCER={_INFERENCER!r}; expected groq|openrouter|gemini")
    if not os.getenv(_KEY_VAR):
        pytest.skip(f"{_KEY_VAR} not set -- corpus ingest requires live LLM (inferencer={_INFERENCER})")
    _PROCESSED.mkdir(parents=True, exist_ok=True)
    ingested = []
    for doc_id in _ALL_CORPUS_IDS:
        doc = get_doc(doc_id)
        pdf_path = Path("data/raw") / doc["filename"]
        if not pdf_path.exists():
            pytest.skip(f"PDF missing: {pdf_path}")
        out_json = _PROCESSED / f"_{doc_id}_corpus.json"
        r1 = subprocess.run(
            [sys.executable, "-m", "src.pipeline.ingest",
             "--input", str(pdf_path),
             "--doc-id", doc_id,
             "--inferencer", _INFERENCER,
             "--output", str(out_json)],
            capture_output=True, text=True,
        )
        assert r1.returncode == 0, f"ingest failed for {doc_id}: {r1.stderr}"
        assert out_json.exists(), f"ingest produced no output for {doc_id}"
        r2 = subprocess.run(
            [sys.executable, "-m", "src.graph.neo4j_loader",
             "--doc-id", doc_id,
             "--doc-title", doc.get("title", doc_id),
             "--doc-sku", doc.get("sku", doc_id.upper()),
             "--doc-source-url", doc.get("source_url") or "",
             "--input", str(out_json)],
            capture_output=True, text=True,
        )
        assert r2.returncode == 0, f"neo4j_loader failed for {doc_id}: {r2.stderr}"
        ingested.append(doc_id)
    return ingested
