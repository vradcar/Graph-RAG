"""Integration tests for provenance helpers (SCHEMA-01..05 + idempotency).

These tests are marked @pytest.mark.integration and require a live Neo4j instance.
They import from src.graph.provenance which does NOT exist yet — Plan 02 creates it.
Tests will fail/error on ImportError until Plan 02 is complete (expected RED baseline).
"""
import pytest
from src.graph.provenance import (  # noqa: F401  -- RED: module doesn't exist yet
    merge_document,
    merge_node_with_provenance,
    merge_edge_with_provenance,
)


@pytest.mark.integration
def test_document_upsert(clean_db, neo4j_driver, sample_doc_a):
    """merge_document writes :Document with all 5 props; re-run updates last_reingested."""
    with neo4j_driver.session() as session:
        session.execute_write(lambda tx: merge_document(tx, sample_doc_a))
        result = session.run(
            "MATCH (d:Document {doc_id: $doc_id}) RETURN d",
            doc_id=sample_doc_a["doc_id"],
        ).single()
    assert result is not None
    node = result["d"]
    assert node["doc_id"] == sample_doc_a["doc_id"]
    assert node["title"] == sample_doc_a["title"]
    assert node["sku"] == sample_doc_a["sku"]
    assert node["source_url"] == sample_doc_a["source_url"]
    assert node["ingested_at"] is not None
    # second upsert: last_reingested updated, first_ingested unchanged
    first_ingested = node.get("first_ingested")
    assert first_ingested is not None, "first_ingested must be set on CREATE"
    with neo4j_driver.session() as session:
        session.execute_write(lambda tx: merge_document(tx, sample_doc_a))
        result2 = session.run(
            "MATCH (d:Document {doc_id: $doc_id}) RETURN d",
            doc_id=sample_doc_a["doc_id"],
        ).single()
    node2 = result2["d"]
    assert node2.get("first_ingested") == first_ingested
    assert node2.get("last_reingested") is not None, "last_reingested must be set on MATCH"


@pytest.mark.integration
def test_mentioned_in_created(clean_db, neo4j_driver, sample_doc_a):
    """merge_node_with_provenance creates (n)-[:MENTIONED_IN]->(:Document); re-run yields exactly 1 edge."""
    node_data = {"node_id": "T9", "label": "T9 Thermostat", "kind": "Product", "properties": {}}
    with neo4j_driver.session() as session:
        session.execute_write(lambda tx: merge_document(tx, sample_doc_a))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node_data, sample_doc_a["doc_id"]))
        # run again (idempotent)
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node_data, sample_doc_a["doc_id"]))
        count = session.run(
            "MATCH (:Product {node_id: 'T9'})-[r:MENTIONED_IN]->(:Document) RETURN count(r) AS cnt"
        ).single()["cnt"]
    assert count == 1


@pytest.mark.integration
def test_no_null_source_doc(clean_db, neo4j_driver, sample_doc_a):
    """After ingesting a fact, no non-MENTIONED_IN edge has source_doc=NULL."""
    node_a = {"node_id": "T9", "label": "T9 Thermostat", "kind": "Product", "properties": {}}
    node_b = {"node_id": "ACC1", "label": "Accessory 1", "kind": "Accessory", "properties": {}}
    edge_data = {"source_id": "T9", "target_id": "ACC1", "relation": "COMPATIBLE_WITH", "properties": {}}
    with neo4j_driver.session() as session:
        session.execute_write(lambda tx: merge_document(tx, sample_doc_a))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node_a, sample_doc_a["doc_id"]))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node_b, sample_doc_a["doc_id"]))
        session.execute_write(lambda tx: merge_edge_with_provenance(tx, edge_data, sample_doc_a["doc_id"]))
        null_count = session.run(
            "MATCH ()-[r]->() WHERE type(r) <> 'MENTIONED_IN' AND r.source_doc IS NULL RETURN count(r) AS cnt"
        ).single()["cnt"]
    assert null_count == 0


@pytest.mark.integration
def test_parallel_evidence_edges(clean_db, neo4j_driver, sample_doc_a, sample_doc_b):
    """Ingesting same (source, target, relation) from doc_a and doc_b yields exactly 2 parallel edges."""
    node_a = {"node_id": "T9", "label": "T9 Thermostat", "kind": "Product", "properties": {}}
    node_b = {"node_id": "ACC1", "label": "Accessory 1", "kind": "Accessory", "properties": {}}
    edge_data = {"source_id": "T9", "target_id": "ACC1", "relation": "COMPATIBLE_WITH", "properties": {}}
    with neo4j_driver.session() as session:
        session.execute_write(lambda tx: merge_document(tx, sample_doc_a))
        session.execute_write(lambda tx: merge_document(tx, sample_doc_b))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node_a, sample_doc_a["doc_id"]))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node_b, sample_doc_a["doc_id"]))
        session.execute_write(lambda tx: merge_edge_with_provenance(tx, edge_data, sample_doc_a["doc_id"]))
        session.execute_write(lambda tx: merge_edge_with_provenance(tx, edge_data, sample_doc_b["doc_id"]))
        edges = session.run(
            "MATCH (:Product {node_id: 'T9'})-[r:COMPATIBLE_WITH]->(:Accessory {node_id: 'ACC1'}) RETURN r.source_doc AS sd"
        ).data()
    assert len(edges) == 2
    source_docs = {e["sd"] for e in edges}
    assert source_docs == {"doc_a", "doc_b"}


@pytest.mark.integration
def test_node_dedup_with_source_docs(clean_db, neo4j_driver, sample_doc_a, sample_doc_b):
    """Ingesting node T9 from doc_a then doc_b yields exactly 1 :Product with source_docs==['doc_a','doc_b']."""
    node = {"node_id": "T9", "label": "T9 Thermostat", "kind": "Product", "properties": {}}
    with neo4j_driver.session() as session:
        session.execute_write(lambda tx: merge_document(tx, sample_doc_a))
        session.execute_write(lambda tx: merge_document(tx, sample_doc_b))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node, sample_doc_a["doc_id"]))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node, sample_doc_b["doc_id"]))
        result = session.run(
            "MATCH (n:Product {node_id: 'T9'}) RETURN count(n) AS cnt, n.source_docs AS sd"
        ).single()
    assert result["cnt"] == 1
    assert sorted(result["sd"]) == ["doc_a", "doc_b"]


@pytest.mark.integration
def test_idempotent_reingest(clean_db, neo4j_driver, sample_doc_a):
    """Ingesting same node from same doc twice yields exactly 1 node with source_docs==['doc_a']."""
    node = {"node_id": "T9", "label": "T9 Thermostat", "kind": "Product", "properties": {}}
    with neo4j_driver.session() as session:
        session.execute_write(lambda tx: merge_document(tx, sample_doc_a))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node, sample_doc_a["doc_id"]))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node, sample_doc_a["doc_id"]))
        result = session.run(
            "MATCH (n:Product {node_id: 'T9'}) RETURN count(n) AS cnt, n.source_docs AS sd"
        ).single()
    assert result["cnt"] == 1
    assert result["sd"] == ["doc_a"]


@pytest.mark.integration
def test_idempotent_edge_reingest(clean_db, neo4j_driver, sample_doc_a):
    """Ingesting same edge from same doc twice yields exactly 1 edge."""
    node_a = {"node_id": "T9", "label": "T9 Thermostat", "kind": "Product", "properties": {}}
    node_b = {"node_id": "ACC1", "label": "Accessory 1", "kind": "Accessory", "properties": {}}
    edge_data = {"source_id": "T9", "target_id": "ACC1", "relation": "COMPATIBLE_WITH", "properties": {}}
    with neo4j_driver.session() as session:
        session.execute_write(lambda tx: merge_document(tx, sample_doc_a))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node_a, sample_doc_a["doc_id"]))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node_b, sample_doc_a["doc_id"]))
        session.execute_write(lambda tx: merge_edge_with_provenance(tx, edge_data, sample_doc_a["doc_id"]))
        session.execute_write(lambda tx: merge_edge_with_provenance(tx, edge_data, sample_doc_a["doc_id"]))
        count = session.run(
            "MATCH (:Product {node_id: 'T9'})-[r:COMPATIBLE_WITH {source_doc: 'doc_a'}]->(:Accessory {node_id: 'ACC1'}) RETURN count(r) AS cnt"
        ).single()["cnt"]
    assert count == 1


@pytest.mark.integration
def test_mentioned_in_count_matches_source_docs(clean_db, neo4j_driver, sample_doc_a, sample_doc_b):
    """For every node with source_docs, size(source_docs) == count MENTIONED_IN edges."""
    node = {"node_id": "T9", "label": "T9 Thermostat", "kind": "Product", "properties": {}}
    with neo4j_driver.session() as session:
        session.execute_write(lambda tx: merge_document(tx, sample_doc_a))
        session.execute_write(lambda tx: merge_document(tx, sample_doc_b))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node, sample_doc_a["doc_id"]))
        session.execute_write(lambda tx: merge_node_with_provenance(tx, node, sample_doc_b["doc_id"]))
        result = session.run(
            """
            MATCH (n) WHERE n.source_docs IS NOT NULL
            WITH n, size(n.source_docs) AS sd_count,
                 count { (n)-[:MENTIONED_IN]->() } AS mi_count
            WHERE sd_count <> mi_count
            RETURN count(n) AS mismatch_count
            """
        ).single()
    assert result["mismatch_count"] == 0
