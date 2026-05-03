import os
import pytest
from dotenv import load_dotenv


@pytest.fixture(scope="session")
def neo4j_driver():
    load_dotenv()
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        pytest.skip("NEO4J_PASSWORD not set", allow_module_level=False)
    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import ServiceUnavailable
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        yield driver
        driver.close()
    except Exception:
        pytest.skip("Neo4j not reachable", allow_module_level=False)


@pytest.fixture(scope="function")
def clean_db(neo4j_driver):
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield


@pytest.fixture
def sample_doc_a():
    return {
        "doc_id": "doc_a",
        "title": "Doc A",
        "sku": "SKU-A",
        "source_url": "http://a",
        "ingested_at": "2026-05-02T00:00:00Z",
    }


@pytest.fixture
def sample_doc_b():
    return {
        "doc_id": "doc_b",
        "title": "Doc B",
        "sku": "SKU-B",
        "source_url": "http://b",
        "ingested_at": "2026-05-02T00:00:00Z",
    }
