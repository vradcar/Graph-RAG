"""Unit tests for src/ingest/normalizer.py — no external dependencies."""
import pytest


@pytest.mark.parametrize("raw,expected", [
    ("RCHT9510WF", "rcht9510wf"),
    ("2 Wire Heat Only", "2-wire-heat-only"),
    ("Heat Pump", "heat-pump"),
    ("24VAC", "24vac"),
    ("T9 Smart Thermostat", "rcht9610wf"),   # alias: t9-smart-thermostat → rcht9610wf
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


# Edge normalization tests

@pytest.mark.parametrize("raw_src,raw_tgt,exp_src,exp_tgt", [
    ("RCHT9510WF", "THM301", "rcht9510wf", "thm301"),
    ("T9 Smart Thermostat", "UWP Wall Plate", "rcht9610wf", "uwp-wallplate"),
    ("t9", "wireless-sensor", "rcht9610wf", "wireless-room-sensor"),
    ("already-normalized", "also-fine", "already-normalized", "also-fine"),
])
def test_normalize_edge_normalizes_source_and_target(raw_src, raw_tgt, exp_src, exp_tgt):
    from src.ingest.normalizer import normalize_edge
    edge = {"source_id": raw_src, "target_id": raw_tgt, "relation": "COMPATIBLE_WITH"}
    result = normalize_edge(edge)
    assert result["source_id"] == exp_src, f"source_id: {result['source_id']!r} != {exp_src!r}"
    assert result["target_id"] == exp_tgt, f"target_id: {result['target_id']!r} != {exp_tgt!r}"


def test_normalize_edge_preserves_relation_and_extra_fields():
    from src.ingest.normalizer import normalize_edge
    edge = {"source_id": "T9", "target_id": "ACC001", "relation": "REQUIRES", "confidence": 0.9}
    result = normalize_edge(edge)
    assert result["relation"] == "REQUIRES"
    assert result["confidence"] == 0.9


def test_deduplicate_edges_removes_exact_duplicates():
    from src.ingest.normalizer import deduplicate_edges
    edges = [
        {"source_id": "a", "target_id": "b", "relation": "COMPATIBLE_WITH"},
        {"source_id": "a", "target_id": "b", "relation": "COMPATIBLE_WITH"},  # duplicate
        {"source_id": "a", "target_id": "c", "relation": "REQUIRES"},
    ]
    result = deduplicate_edges(edges)
    assert len(result) == 2


def test_deduplicate_edges_same_nodes_different_relation_kept():
    from src.ingest.normalizer import deduplicate_edges
    edges = [
        {"source_id": "a", "target_id": "b", "relation": "COMPATIBLE_WITH"},
        {"source_id": "a", "target_id": "b", "relation": "REQUIRES"},
    ]
    result = deduplicate_edges(edges)
    assert len(result) == 2


def test_normalize_and_deduplicate_edges_filters_excluded_nodes():
    from src.ingest.normalizer import normalize_and_deduplicate_edges
    edges = [
        {"source_id": "rcht9610wf", "target_id": "thm301", "relation": "COMPATIBLE_WITH"},
        {"source_id": "rcht9610wf", "target_id": "millivolt", "relation": "COMPATIBLE_WITH"},
        {"source_id": "line-voltage", "target_id": "thm301", "relation": "REQUIRES"},
    ]
    result = normalize_and_deduplicate_edges(edges)
    result_keys = [(e["source_id"], e["target_id"]) for e in result]
    assert ("rcht9610wf", "thm301") in result_keys
    assert ("rcht9610wf", "millivolt") not in result_keys   # millivolt is excluded
    assert ("line-voltage", "thm301") not in result_keys    # line-voltage is excluded


def test_normalize_and_deduplicate_edges_normalizes_ids():
    from src.ingest.normalizer import normalize_and_deduplicate_edges
    edges = [
        {"source_id": "T9", "target_id": "wireless-sensor", "relation": "COMPATIBLE_WITH"},
        {"source_id": "t9", "target_id": "wireless-room-sensor", "relation": "COMPATIBLE_WITH"},
    ]
    result = normalize_and_deduplicate_edges(edges)
    # Both should normalize to the same edge and be deduplicated
    assert len(result) == 1
    assert result[0]["source_id"] == "rcht9610wf"
    assert result[0]["target_id"] == "wireless-room-sensor"
