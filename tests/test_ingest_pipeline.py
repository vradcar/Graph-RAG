"""
Integration tests for src/pipeline/ingest.py.

Tests marked with @pytest.mark.integration require:
  - Neo4j running at bolt://localhost:7687 (docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5)
  - GROQ_API_KEY in environment

Run integration tests: pytest tests/test_ingest_pipeline.py -m integration -v
Run unit tests only:    pytest tests/test_ingest_pipeline.py -m "not integration" -v
"""
import os
import pytest
from pathlib import Path

PDF_PATH = "data/raw/t9-thermostat.pdf"


def test_missing_pdf_raises():
    """run_ingest with a nonexistent path should raise FileNotFoundError or SystemExit."""
    from src.ingest.pdf_parser import extract_page_content
    with pytest.raises(FileNotFoundError):
        extract_page_content("data/raw/does_not_exist_xyzzy.pdf")


def test_dry_run_returns_zero_writes():
    """--dry-run must return nodes_written=0 and edges_written=0."""
    from src.pipeline.ingest import run_ingest
    # Dry run does not call Groq or Neo4j
    # It WILL call extract_page_content (pymupdf + pdfplumber) and build_client (raises if no key)
    # So skip this test if GROQ_API_KEY or OPENAI_API_KEY is not set
    if not os.getenv("GROQ_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        pytest.skip("No LLM API key set — skipping dry run test")
    result = run_ingest(PDF_PATH, dry_run=True)
    assert result["nodes_written"] == 0
    assert result["edges_written"] == 0
    assert result["pages_processed"] >= 1


def test_run_ingest_summary_has_expected_keys():
    """run_ingest return value has the required structure."""
    from src.pipeline.ingest import run_ingest
    if not os.getenv("GROQ_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        pytest.skip("No LLM API key set — skipping")
    result = run_ingest(PDF_PATH, dry_run=True)
    assert "pages_processed" in result
    assert "nodes_written" in result
    assert "edges_written" in result
    assert "node_counts" in result


@pytest.mark.integration
def test_double_run_idempotency():
    """
    INTEGRATION TEST — requires Neo4j + LLM API key.

    Run ingest twice. Node and edge counts must be identical.
    This verifies INGEST-06: idempotent ingestion.
    """
    from src.pipeline.ingest import run_ingest
    from src.graph.store import Neo4jGraphStore
    from src.common.config import load_settings

    settings = load_settings()
    neo4j_uri = settings["graph"]["neo4j_uri"]
    neo4j_user = settings["graph"]["neo4j_user"]
    neo4j_password = os.getenv("NEO4J_PASSWORD", settings["graph"]["neo4j_password"])

    def count_nodes_and_edges(store: Neo4jGraphStore) -> tuple[int, int]:
        with store._driver.session() as session:
            node_result = session.run("MATCH (n) RETURN count(n) AS cnt")
            node_cnt = node_result.single()["cnt"]
            edge_result = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt")
            edge_cnt = edge_result.single()["cnt"]
        return node_cnt, edge_cnt

    # First run
    run_ingest(PDF_PATH, dry_run=False)

    with Neo4jGraphStore(neo4j_uri, neo4j_user, neo4j_password) as store:
        nodes_after_first, edges_after_first = count_nodes_and_edges(store)

    assert nodes_after_first > 0, "Expected at least 1 node after first ingest"

    # Second run — must produce the same counts
    run_ingest(PDF_PATH, dry_run=False)

    with Neo4jGraphStore(neo4j_uri, neo4j_user, neo4j_password) as store:
        nodes_after_second, edges_after_second = count_nodes_and_edges(store)

    assert nodes_after_second == nodes_after_first, (
        f"Node count changed after second run: {nodes_after_first} → {nodes_after_second}. "
        "INGEST-06 (idempotency) is violated. Check that all writes use MERGE."
    )
    assert edges_after_second == edges_after_first, (
        f"Edge count changed after second run: {edges_after_first} → {edges_after_second}. "
        "INGEST-06 (idempotency) is violated. Check that all edge writes use MERGE."
    )
