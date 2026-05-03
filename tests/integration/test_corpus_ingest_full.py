"""SC-2 prerequisite + SC-3 end-to-end: drive the full pipeline (manifest ->
pdf_parser -> entity_extractor -> normalizer -> neo4j_loader) for each of the 3
new PDFs. Skips cleanly when GROQ_API_KEY is missing or Neo4j is unreachable
(matches Phase 1 integration skip pattern in tests/conftest.py)."""
import os
import subprocess
import sys
from pathlib import Path
import pytest

from src.ingest.manifest import get_doc

NEW_DOC_IDS = ["t6_pro_install", "thp9045_wiring_module", "t10_pro_user_guide"]
PROCESSED = Path("data/processed")


@pytest.fixture(scope="session")
def corpus_ingested(neo4j_driver):
    """Session-scoped: ingest all 3 new PDFs into Neo4j once, share with bridges test."""
    if not os.getenv("GROQ_API_KEY"):
        pytest.skip("GROQ_API_KEY not set -- corpus ingest requires live LLM")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    ingested = []
    for doc_id in NEW_DOC_IDS:
        doc = get_doc(doc_id)
        pdf_path = Path("data/raw") / doc["filename"]
        if not pdf_path.exists():
            pytest.skip(f"PDF missing: {pdf_path}")
        out_json = PROCESSED / f"_{doc_id}_corpus.json"
        # Step 1: pipeline ingest with --doc-id (uses manifest pages filter)
        r1 = subprocess.run(
            [sys.executable, "-m", "src.pipeline.ingest",
             "--input", str(pdf_path),
             "--doc-id", doc_id,
             "--output", str(out_json)],
            capture_output=True, text=True,
        )
        assert r1.returncode == 0, f"ingest failed for {doc_id}: {r1.stderr}"
        assert out_json.exists(), f"ingest produced no output for {doc_id}"
        # Step 2: load into Neo4j (no --reset; we want all 3 docs co-resident with T9)
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


@pytest.mark.integration
def test_full_corpus_ingest_into_neo4j(neo4j_driver, corpus_ingested):
    """SC-3 end-to-end: all 3 new docs reach Neo4j with at least one node each."""
    with neo4j_driver.session() as session:
        for doc_id in corpus_ingested:
            count = session.run(
                "MATCH (n) WHERE $d IN n.source_docs RETURN count(n) AS c",
                d=doc_id,
            ).single()["c"]
            assert count > 0, f"{doc_id} produced 0 nodes in Neo4j"
