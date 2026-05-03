"""Unit tests for schema.py additions (SCHEMA-01..05 contract).

These tests pass after Task 1 — no Neo4j required.
"""
import pytest
from src.graph.schema import Document, VALID_KINDS, VALID_RELATIONS


def test_document_required_fields():
    """Document instantiates with required fields; raises TypeError without them."""
    doc = Document(doc_id="x", title="y")
    assert doc.doc_id == "x"
    assert doc.title == "y"
    assert doc.sku is None
    assert doc.source_url is None
    assert doc.ingested_at is None
    with pytest.raises(TypeError):
        Document()  # type: ignore[call-arg]


def test_document_kind_in_valid_kinds():
    assert "Document" in VALID_KINDS


def test_mentioned_in_in_valid_relations():
    assert "MENTIONED_IN" in VALID_RELATIONS


def test_existing_kinds_preserved():
    expected = {"Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec"}
    assert expected <= VALID_KINDS


def test_existing_relations_preserved():
    expected = {"COMPATIBLE_WITH", "REPLACES", "SUPPORTS_WIRING", "HAS_SPEC"}
    assert expected <= VALID_RELATIONS
