"""Regression test for the dangling-edge drop invariant.

The repair logic in `src/pipeline/ingest.py` previously synthesized
``kind="Unknown"`` stub nodes whenever an edge referenced an endpoint that
was not extracted as a node. ``Unknown`` is not in ``NODE_KIND``
(see ``src/graph/schema.py``), so those corpora fail to load through
``EntityNode``. The correct behavior is to DROP the dangling edge and never
synthesize a stub node.

This test guards that invariant.
"""

from src.pipeline.ingest import drop_dangling_edges


def _node(node_id: str, kind: str = "Product") -> dict:
    return {"node_id": node_id, "label": node_id, "kind": kind}


def _edge(src: str, tgt: str, relation: str = "COMPATIBLE_WITH") -> dict:
    return {"source_id": src, "target_id": tgt, "relation": relation}


def test_drops_dangling_edges_and_never_synthesizes_unknown():
    nodes = [_node("A"), _node("B")]
    edges = [_edge("A", "B"), _edge("A", "Z"), _edge("Y", "B")]

    out_nodes, out_edges = drop_dangling_edges(nodes, edges)

    # Only the fully-grounded edge survives.
    assert out_edges == [_edge("A", "B")]
    # No synthesized Unknown stubs were appended.
    assert all(n.get("kind") != "Unknown" for n in out_nodes)


def test_node_set_unchanged():
    nodes = [_node("A"), _node("B")]
    edges = [_edge("A", "Z"), _edge("Y", "B")]

    out_nodes, _ = drop_dangling_edges(nodes, edges)

    assert {n["node_id"] for n in out_nodes} == {"A", "B"}
    assert all(n.get("kind") != "Unknown" for n in out_nodes)


def test_no_drop_when_all_endpoints_present():
    nodes = [_node("A"), _node("B"), _node("C")]
    edges = [_edge("A", "B"), _edge("B", "C"), _edge("A", "C")]

    out_nodes, out_edges = drop_dangling_edges(nodes, edges)

    assert out_edges == edges
    assert out_nodes == nodes


def test_idempotence():
    nodes = [_node("A"), _node("B")]
    edges = [_edge("A", "B"), _edge("A", "Z"), _edge("Y", "B")]

    once_nodes, once_edges = drop_dangling_edges(nodes, edges)
    twice_nodes, twice_edges = drop_dangling_edges(once_nodes, once_edges)

    assert once_nodes == twice_nodes
    assert once_edges == twice_edges
    assert all(n.get("kind") != "Unknown" for n in twice_nodes)
