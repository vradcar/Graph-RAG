"""
Integration tests for src/pipeline/ingest.py.

Tests marked with @pytest.mark.integration require:
  - Neo4j running at bolt://localhost:7687 (docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5)
  - GROQ_API_KEY in environment

Run integration tests: pytest tests/test_ingest_pipeline.py -m integration -v
Run unit tests only:    pytest tests/test_ingest_pipeline.py -m "not integration" -v
"""
import json
import os
import pytest
from pathlib import Path

PDF_PATH = "data/raw/t9-thermostat.pdf"


def test_missing_pdf_raises():
    """run_ingest with a nonexistent path should raise FileNotFoundError or SystemExit."""
    from src.ingest.pdf_parser import extract_page_content
    with pytest.raises(FileNotFoundError):
        extract_page_content("data/raw/does_not_exist_xyzzy.pdf")


def _run_main_against(output_path: Path, monkeypatch, extra_args: list[str] | None = None) -> dict:
    """Invoke src.pipeline.ingest.main() as the CLI would, writing to output_path.

    With no --doc-id, main() always routes a .pdf input through the legacy
    pdfplumber extraction path (src.graph.extract.extract_from_pdf) rather
    than the LLM path — so this needs no GROQ_API_KEY/OPENAI_API_KEY, unlike
    the --doc-id + LLM-extraction path elsewhere in ingest.py.
    """
    from src.pipeline.ingest import main

    argv = ["ingest.py", "--input", PDF_PATH, "--output", str(output_path)]
    monkeypatch.setattr("sys.argv", argv + (extra_args or []))
    main()
    with output_path.open(encoding="utf-8") as f:
        return json.load(f)


def test_ingest_writes_populated_nodes_and_edges(tmp_path, monkeypatch):
    """A bare PDF ingest (no --doc-id) must write a JSON file with at least
    one extracted node — mirrors the old 'dry run produces output' check,
    updated for the current legacy-path-by-default CLI behavior."""
    result = _run_main_against(tmp_path / "graph_items.json", monkeypatch)
    assert "nodes" in result
    assert "edges" in result
    assert len(result["nodes"]) >= 1


def test_ingest_output_nodes_have_legacy_shape():
    """Written nodes must have the node_id/kind keys GraphStore.upsert_node
    (and Neo4j loading generally) expects — the legacy shape documented at
    the top of src/pipeline/ingest.py."""
    from src.graph.extract import extract_from_pdf, graph_items_to_legacy_format

    rich_graph = extract_from_pdf(Path(PDF_PATH))
    graph_items = graph_items_to_legacy_format(rich_graph)

    assert graph_items["nodes"], "expected at least one extracted node"
    sample = graph_items["nodes"][0]
    assert "node_id" in sample
    assert "kind" in sample


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
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")

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
