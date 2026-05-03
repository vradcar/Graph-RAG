"""Unit tests for src/retrieval/hybrid_retriever.py — no external dependencies."""
import pytest
from unittest.mock import MagicMock

# rank_hybrid_results

def test_rank_hybrid_both_tiers_ranked_first():
    """Triples in BOTH graph and vector results must appear before graph-only or vector-only."""
    from src.retrieval.hybrid_retriever import rank_hybrid_results

    graph_hits = [
        ("T9", "COMPATIBLE_WITH", "C-Wire Adapter"),
        ("T9", "REQUIRES", "UWP"),
    ]
    doc_hits = [
        {"source": "T9", "relation": "COMPATIBLE_WITH", "target": "C-Wire Adapter", "text": "..."},
        {"source": "T9", "relation": "CONNECTED_TO", "target": "ZoningPanel", "text": "..."},
    ]

    ranked = rank_hybrid_results(graph_hits, doc_hits)

    # ("T9", "COMPATIBLE_WITH", "C-Wire Adapter") is in both → must be first
    assert ranked[0] == ("T9", "COMPATIBLE_WITH", "C-Wire Adapter")


def test_rank_hybrid_no_duplicates():
    """Output must contain no duplicate triples even if input has overlap."""
    from src.retrieval.hybrid_retriever import rank_hybrid_results

    triple = ("A", "REL", "B")
    graph_hits = [triple, triple]
    doc_hits = [{"source": "A", "relation": "REL", "target": "B", "text": "..."}]

    ranked = rank_hybrid_results(graph_hits, doc_hits)
    assert ranked.count(triple) == 1


def test_rank_hybrid_empty_graph_hits():
    """When graph_hits is empty, vector triples are returned."""
    from src.retrieval.hybrid_retriever import rank_hybrid_results

    doc_hits = [
        {"source": "X", "relation": "IS_A", "target": "Product", "text": "..."},
    ]
    ranked = rank_hybrid_results([], doc_hits)
    assert ranked == [("X", "IS_A", "Product")]


def test_rank_hybrid_empty_doc_hits():
    """When doc_hits is empty, graph triples are returned unchanged."""
    from src.retrieval.hybrid_retriever import rank_hybrid_results

    graph_hits = [("A", "REL", "B"), ("C", "REL", "D")]
    ranked = rank_hybrid_results(graph_hits, [])
    assert ranked == graph_hits


def test_rank_hybrid_both_empty():
    from src.retrieval.hybrid_retriever import rank_hybrid_results
    assert rank_hybrid_results([], []) == []


def test_rank_hybrid_doc_hits_without_triple_fields_ignored():
    """Doc hits missing source/relation/target must not produce garbage triples."""
    from src.retrieval.hybrid_retriever import rank_hybrid_results

    doc_hits = [
        {"text": "no triple fields here"},
        {"source": "A", "text": "missing relation and target"},
        {"source": "A", "relation": "REL", "target": "B", "text": "complete"},
    ]
    ranked = rank_hybrid_results([], doc_hits)
    assert ranked == [("A", "REL", "B")]


# hybrid_retrieve (integration of graph_retrieve + vector search)

def test_hybrid_retrieve_merges_both_results():
    """hybrid_retrieve must return both graph_hits and doc_hits keys."""
    from src.retrieval.hybrid_retriever import hybrid_retrieve

    mock_graph_store = MagicMock()
    mock_vector_store = MagicMock()

    mock_graph_store.has_node.return_value = False
    mock_graph_store.run_cypher = MagicMock(return_value=[])
    mock_vector_store.search.return_value = [
        {"source": "T9", "relation": "IS_A", "target": "Product", "text": "T9 Product"},
    ]

    result = hybrid_retrieve(mock_graph_store, mock_vector_store, "T9 product", depth=1, top_k=5)

    assert "graph_hits" in result
    assert "doc_hits" in result
    assert len(result["doc_hits"]) == 1


def test_hybrid_retrieve_calls_vector_store_with_top_k():
    from src.retrieval.hybrid_retriever import hybrid_retrieve

    mock_graph_store = MagicMock()
    mock_graph_store.has_node.return_value = False
    mock_vector_store = MagicMock()
    mock_vector_store.search.return_value = []

    hybrid_retrieve(mock_graph_store, mock_vector_store, "test question", depth=2, top_k=7)

    mock_vector_store.search.assert_called_once_with("test question", top_k=7)
