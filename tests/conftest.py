import os
import pytest
from dotenv import load_dotenv


@pytest.fixture(scope="session")
def neo4j_driver():
    load_dotenv()
    uri = os.getenv("NEO4J_TEST_URI") or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    chosen_var = "NEO4J_TEST_URI" if os.getenv("NEO4J_TEST_URI") else "NEO4J_URI"
    print(f"[conftest] using {chosen_var}={uri}")
    if not password:
        pytest.skip("NEO4J_PASSWORD not set", allow_module_level=False)
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable, AuthError
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        yield driver
        driver.close()
    except (ServiceUnavailable, AuthError, OSError):
        pytest.skip("Neo4j not reachable")


@pytest.fixture(scope="function")
def clean_db(neo4j_driver):
    # Setup: wipe any pre-existing data before the test
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield
    # Teardown: wipe again after the test, even if it errors mid-flight
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")


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
