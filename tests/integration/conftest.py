import os
import subprocess
import sys
from pathlib import Path
import pytest

from src.ingest.manifest import get_doc

_NEW_DOC_IDS = ["t6_pro_install", "thp9045_wiring_module", "t10_pro_user_guide"]
_PROCESSED = Path("data/processed")


@pytest.fixture(scope="session")
def corpus_ingested(neo4j_driver):
    """Session-scoped: ingest all 3 new PDFs into Neo4j once. Shared by SC-2 and SC-3 tests."""
    if not os.getenv("GROQ_API_KEY"):
        pytest.skip("GROQ_API_KEY not set -- corpus ingest requires live LLM")
    _PROCESSED.mkdir(parents=True, exist_ok=True)
    ingested = []
    for doc_id in _NEW_DOC_IDS:
        doc = get_doc(doc_id)
        pdf_path = Path("data/raw") / doc["filename"]
        if not pdf_path.exists():
            pytest.skip(f"PDF missing: {pdf_path}")
        out_json = _PROCESSED / f"_{doc_id}_corpus.json"
        r1 = subprocess.run(
            [sys.executable, "-m", "src.pipeline.ingest",
             "--input", str(pdf_path),
             "--doc-id", doc_id,
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
