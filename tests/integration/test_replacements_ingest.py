"""INGEST-04: data/raw/replacements.json → Neo4j as REPLACES edges with provenance."""
from pathlib import Path
import pytest

from src.graph.extract import ingest_replacements

REPLACEMENTS = Path("data/raw/replacements.json")


@pytest.mark.integration
def test_replaces_edges_present_after_ingest(neo4j_driver, clean_db):
    if not REPLACEMENTS.exists():
        pytest.skip("data/raw/replacements.json missing")
    counts = ingest_replacements(REPLACEMENTS, neo4j_driver)
    assert counts["replaces_edges"] >= 1, f"no REPLACES edges written: {counts}"
    with neo4j_driver.session() as session:
        n = session.run("MATCH ()-[r:REPLACES]->() RETURN count(r) AS c").single()["c"]
    assert n >= 1, f"Cypher count of REPLACES edges is {n}"
