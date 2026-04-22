"""Unit tests for src/ingest/normalizer.py — no external dependencies."""
import pytest


@pytest.mark.parametrize("raw,expected", [
    ("RCHT9510WF", "rcht9510wf"),
    ("2 Wire Heat Only", "2-wire-heat-only"),
    ("Heat Pump", "heat-pump"),
    ("24VAC", "24vac"),
    ("T9 Smart Thermostat", "t9-smart-thermostat"),
    ("2-wire-heat-only", "2-wire-heat-only"),  # already normalized
])
def test_normalize_node_id_lowercase_hyphen(raw, expected):
    from src.ingest.normalizer import normalize_node_id
    assert normalize_node_id(raw) == expected, f"normalize_node_id({raw!r}) = {normalize_node_id(raw)!r}, expected {expected!r}"


@pytest.mark.parametrize("raw,expected", [
    ("24 VAC", "24VAC"),
    ("24 V AC", "24VAC"),
    ("conventional", "conventional"),  # not in alias map — unchanged
    ("  heat pump  ", "HEAT-PUMP"),  # HEAT PUMP is in ALIAS_MAP → canonical form
])
def test_normalize_label_alias_map(raw, expected):
    from src.ingest.normalizer import normalize_label
    assert normalize_label(raw) == expected, f"normalize_label({raw!r}) = {normalize_label(raw)!r}"


def test_deduplicate_nodes_removes_duplicate_ids():
    from src.ingest.normalizer import deduplicate_nodes
    nodes = [
        {"node_id": "a", "label": "First", "kind": "Product", "properties": {}},
        {"node_id": "a", "label": "Duplicate", "kind": "Product", "properties": {}},
        {"node_id": "b", "label": "B", "kind": "Accessory", "properties": {}},
    ]
    result = deduplicate_nodes(nodes)
    assert len(result) == 2
    assert result[0]["label"] == "First"  # first wins


def test_deduplicate_nodes_empty():
    from src.ingest.normalizer import deduplicate_nodes
    assert deduplicate_nodes([]) == []


def test_normalize_and_deduplicate_pipeline():
    from src.ingest.normalizer import normalize_and_deduplicate
    nodes = [
        {"node_id": "RCHT9510WF", "label": "T9", "kind": "Product", "properties": {}},
        {"node_id": "rcht9510wf", "label": "T9 dup", "kind": "Product", "properties": {}},
    ]
    result = normalize_and_deduplicate(nodes)
    assert len(result) == 1
    assert result[0]["node_id"] == "rcht9510wf"
    assert result[0]["label"] == "T9"  # first wins after normalization
