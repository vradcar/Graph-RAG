"""
Root conftest.py — registers custom marks and applies skip conditions.

Marks:
  @pytest.mark.integration
    Requires a live Neo4j instance and NEO4J_PASSWORD env var.
    Skipped automatically unless both are present.
"""
import os
import pytest


def _neo4j_reachable() -> bool:
    if not os.getenv("NEO4J_PASSWORD"):
        return False
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            "neo4j://127.0.0.1:7687",
            auth=("neo4j", os.environ["NEO4J_PASSWORD"]),
        )
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


_NEO4J_UP = None  # evaluated once per session


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring a live Neo4j instance (skipped if not running)",
    )


def pytest_runtest_setup(item):
    global _NEO4J_UP
    if "integration" in item.keywords:
        if _NEO4J_UP is None:
            _NEO4J_UP = _neo4j_reachable()
        if not _NEO4J_UP:
            pytest.skip("Neo4j not reachable — skipping integration test")
