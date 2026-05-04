"""SC-2 prerequisite + SC-3 end-to-end: drive the full pipeline (manifest ->
pdf_parser -> entity_extractor -> normalizer -> neo4j_loader) for each of the 3
new PDFs. Skips cleanly when GROQ_API_KEY is missing or Neo4j is unreachable
(matches Phase 1 integration skip pattern in tests/conftest.py).

The `corpus_ingested` session fixture lives in tests/integration/conftest.py
so it is shared with test_cross_doc_bridges.py without pytest_plugins magic."""
import pytest

NEW_DOC_IDS = ["t6_pro_install", "thp9045_wiring_module", "t10_pro_user_guide"]


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
