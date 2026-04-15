"""
Unit tests for Neo4jGraphStore and GraphStore.
Uses unittest.mock to avoid requiring a live Neo4j connection.
"""
from unittest.mock import MagicMock, patch, call
import pytest
from neo4j.exceptions import ServiceUnavailable


@pytest.fixture
def mock_driver():
    """Returns a mock neo4j driver whose verify_connectivity() succeeds."""
    driver = MagicMock()
    driver.verify_connectivity.return_value = None
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    driver.session.return_value.__exit__.return_value = False
    return driver, session


@patch("src.graph.store.GraphDatabase.driver")
def test_upsert_node_calls_merge(mock_driver_factory, mock_driver):
    driver, session = mock_driver
    mock_driver_factory.return_value = driver
    from src.graph.store import Neo4jGraphStore
    store = Neo4jGraphStore("bolt://localhost:7687", "neo4j", "password")
    store.upsert_node("RCHT9510WF", "Product", label="T9 Thermostat")
    # execute_write should have been called once
    session.execute_write.assert_called_once()
    # Extract the _tx function and call it with a mock tx to inspect the Cypher
    _tx = session.execute_write.call_args[0][0]
    mock_tx = MagicMock()
    _tx(mock_tx)
    cypher_call = mock_tx.run.call_args
    assert "MERGE" in cypher_call[0][0]
    assert "$node_id" in cypher_call[0][0]


@patch("src.graph.store.GraphDatabase.driver")
def test_upsert_edge_calls_merge(mock_driver_factory, mock_driver):
    driver, session = mock_driver
    mock_driver_factory.return_value = driver
    from src.graph.store import Neo4jGraphStore
    store = Neo4jGraphStore("bolt://localhost:7687", "neo4j", "password")
    store.upsert_edge("RCHT9510WF", "ACC001", "COMPATIBLE_WITH")
    session.execute_write.assert_called_once()
    _tx = session.execute_write.call_args[0][0]
    mock_tx = MagicMock()
    _tx(mock_tx)
    cypher_call = mock_tx.run.call_args
    assert "MERGE" in cypher_call[0][0]


@patch("src.graph.store.GraphDatabase.driver")
def test_setup_constraints_creates_five(mock_driver_factory, mock_driver):
    driver, session = mock_driver
    mock_driver_factory.return_value = driver
    from src.graph.store import Neo4jGraphStore
    store = Neo4jGraphStore("bolt://localhost:7687", "neo4j", "password")
    store.setup_constraints()
    # Each label triggers one session.run call
    assert session.run.call_count == 5
    # All calls include IF NOT EXISTS
    for c in session.run.call_args_list:
        assert "IF NOT EXISTS" in c[0][0]


@patch("src.graph.store.GraphDatabase.driver")
def test_connectivity_error_raises_runtime_error(mock_driver_factory):
    mock_drv = MagicMock()
    mock_drv.verify_connectivity.side_effect = ServiceUnavailable("down")
    mock_driver_factory.return_value = mock_drv
    from src.graph.store import Neo4jGraphStore
    with pytest.raises(RuntimeError) as exc_info:
        Neo4jGraphStore("bolt://localhost:7687", "neo4j", "password")
    assert "docker run" in str(exc_info.value).lower() or "neo4j" in str(exc_info.value).lower()


def test_graphstore_neighbors():
    from src.graph.store import GraphStore
    gs = GraphStore()
    gs.upsert_node("A")
    gs.upsert_node("B")
    gs.upsert_node("C")
    gs.upsert_edge("A", "B", "REPLACES")
    gs.upsert_edge("B", "C", "COMPATIBLE_WITH")
    paths = gs.neighbors_multi_hop("A", depth=2)
    node_ids = {p[0] for p in paths} | {p[2] for p in paths}
    assert "B" in node_ids
    assert "C" in node_ids
