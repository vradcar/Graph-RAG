"""
Unit tests for scripts/compare_graph_vs_vector.py.

All tests use MagicMock for graph_store and literal dicts for vector_hits.
No Neo4j, no LLM, no network required.
"""
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

# ---------------------------------------------------------------------------
# Ensure scripts/ is importable as a package.
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# We import specific functions rather than the whole module, so we can patch
# at the module level without touching Neo4j or dotenv.
import compare_graph_vs_vector as cgv


# ---------------------------------------------------------------------------
# 1. test_enrich_triples_with_source_doc_calls_cypher_per_unique_edge
# ---------------------------------------------------------------------------
def test_enrich_triples_with_source_doc_calls_cypher_per_unique_edge():
    """
    Given 3 triples where one is duplicated, run_cypher is called exactly 2 times
    (once per unique (src, rel, tgt) combination). Results are merged into quads.
    """
    mock_store = MagicMock()
    # (a, R, b) appears twice, (c, S, d) once — 2 unique edges
    triples = [("a", "R", "b"), ("a", "R", "b"), ("c", "S", "d")]

    # First unique edge (a, R, b) -> returns one source_doc
    # Second unique edge (c, S, d) -> returns another source_doc
    mock_store.run_cypher.side_effect = [
        [{"source_doc": "doc_alpha"}],
        [{"source_doc": "doc_beta"}],
    ]

    quads = cgv.enrich_triples_with_source_doc(mock_store, triples)

    # Called exactly 2 times — deduped
    assert mock_store.run_cypher.call_count == 2

    # Both edges present in output
    sources = {(q["source"], q["relation"], q["target"]) for q in quads}
    assert ("a", "R", "b") in sources
    assert ("c", "S", "d") in sources

    # Source docs correctly assigned
    doc_map = {(q["source"], q["relation"], q["target"]): q["source_doc"] for q in quads}
    assert doc_map[("a", "R", "b")] == "doc_alpha"
    assert doc_map[("c", "S", "d")] == "doc_beta"


# ---------------------------------------------------------------------------
# 2. test_enrich_triples_handles_edge_missing_source_doc
# ---------------------------------------------------------------------------
def test_enrich_triples_handles_edge_missing_source_doc():
    """
    When run_cypher returns [], the triple is still emitted as a quad with
    source_doc=None (edge is visible but provenance is missing).
    """
    mock_store = MagicMock()
    triples = [("x", "HAS_SPEC", "y")]
    mock_store.run_cypher.return_value = []  # no rows for this edge

    quads = cgv.enrich_triples_with_source_doc(mock_store, triples)

    assert len(quads) == 1
    assert quads[0]["source"] == "x"
    assert quads[0]["relation"] == "HAS_SPEC"
    assert quads[0]["target"] == "y"
    assert quads[0]["source_doc"] is None


# ---------------------------------------------------------------------------
# 3. test_distinct_source_doc_count_excludes_none
# ---------------------------------------------------------------------------
def test_distinct_source_doc_count_excludes_none():
    """
    distinct_source_docs() excludes None values from the set.
    """
    quads = [
        {"source": "a", "relation": "R", "target": "b", "source_doc": "doc1"},
        {"source": "c", "relation": "S", "target": "d", "source_doc": None},
        {"source": "e", "relation": "T", "target": "f", "source_doc": "doc2"},
        {"source": "g", "relation": "U", "target": "h", "source_doc": "doc1"},  # duplicate
    ]

    result = cgv.distinct_source_docs(quads)

    assert result == {"doc1", "doc2"}
    assert None not in result


# ---------------------------------------------------------------------------
# 4. test_verdict_graph_win_when_graph_meets_threshold_and_graph_only
# ---------------------------------------------------------------------------
def test_verdict_graph_win_when_graph_meets_threshold_and_graph_only():
    """
    verdict="graph" when graph meets expected_min AND graph_only is True.
    Vector mode cannot satisfy a graph_only question by definition.
    """
    query = {
        "expected_source_docs": ["doc1", "doc2"],
        "expected_min_distinct_source_docs": 2,
        "graph_only": True,
    }
    # Graph quads span 2 distinct docs — meets threshold
    graph_quads = [
        {"source": "a", "relation": "R", "target": "b", "source_doc": "doc1"},
        {"source": "c", "relation": "S", "target": "d", "source_doc": "doc2"},
    ]
    # Vector hits don't cover expected docs — but irrelevant since graph_only=True
    vector_hits = [{"id": "unrelated:chunk-01", "source_doc": "unrelated"}]

    result = cgv.verdict(query, graph_quads, vector_hits)

    assert result["verdict"] == "graph"
    assert result["gap"] is None
    assert result["graph_distinct_source_docs"] == 2


# ---------------------------------------------------------------------------
# 5. test_verdict_graph_win_when_graph_meets_and_vector_misses
# ---------------------------------------------------------------------------
def test_verdict_graph_win_when_graph_meets_and_vector_misses():
    """
    verdict="graph" when graph meets threshold AND vector hits cover 0
    of the expected_source_docs.
    """
    query = {
        "expected_source_docs": ["doc1", "doc2"],
        "expected_min_distinct_source_docs": 2,
        "graph_only": False,
    }
    graph_quads = [
        {"source": "a", "relation": "R", "target": "b", "source_doc": "doc1"},
        {"source": "c", "relation": "S", "target": "d", "source_doc": "doc2"},
    ]
    # Vector hits mention completely unrelated docs
    vector_hits = [
        {"id": "other:chunk-01", "source_doc": "other_doc"},
    ]

    result = cgv.verdict(query, graph_quads, vector_hits)

    assert result["verdict"] == "graph"
    assert result["gap"] is None
    assert result["vector_distinct_expected_docs_covered"] == 0


# ---------------------------------------------------------------------------
# 6. test_verdict_tie_when_both_meet_threshold
# ---------------------------------------------------------------------------
def test_verdict_tie_when_both_meet_threshold():
    """
    verdict="tie" when graph meets threshold AND vector hits cover >=
    expected_min distinct expected_source_docs.
    """
    query = {
        "expected_source_docs": ["doc1", "doc2"],
        "expected_min_distinct_source_docs": 2,
        "graph_only": False,
    }
    graph_quads = [
        {"source": "a", "relation": "R", "target": "b", "source_doc": "doc1"},
        {"source": "c", "relation": "S", "target": "d", "source_doc": "doc2"},
    ]
    # Vector hits cover both expected docs
    vector_hits = [
        {"id": "doc1:chunk-01", "source_doc": "doc1"},
        {"id": "doc2:chunk-01", "source_doc": "doc2"},
    ]

    result = cgv.verdict(query, graph_quads, vector_hits)

    assert result["verdict"] == "tie"
    assert result["vector_distinct_expected_docs_covered"] == 2


# ---------------------------------------------------------------------------
# 7. test_verdict_graph_fail_when_graph_below_threshold
# ---------------------------------------------------------------------------
def test_verdict_graph_fail_when_graph_below_threshold():
    """
    verdict="graph_fail" with a descriptive gap when graph returns fewer
    distinct source_docs than expected_min.
    """
    query = {
        "expected_source_docs": ["doc1", "doc2"],
        "expected_min_distinct_source_docs": 2,
        "graph_only": True,
    }
    # Graph only covers 1 distinct source_doc — below threshold
    graph_quads = [
        {"source": "a", "relation": "R", "target": "b", "source_doc": "doc1"},
    ]
    vector_hits = []

    result = cgv.verdict(query, graph_quads, vector_hits)

    assert result["verdict"] == "graph_fail"
    assert result["gap"] is not None
    assert "1" in result["gap"]  # gap describes actual count
    assert "2" in result["gap"]  # gap describes expected count


# ---------------------------------------------------------------------------
# 8. test_load_queries_round_trip
# ---------------------------------------------------------------------------
def test_load_queries_round_trip(tmp_path):
    """
    load_queries(path) returns the parsed list with all required fields preserved.
    """
    import json

    sample = [
        {
            "id": "mq01",
            "question": "Test question?",
            "depth": 2,
            "expected_source_docs": ["doc_a", "doc_b"],
            "expected_min_distinct_source_docs": 2,
            "graph_only": True,
            "notes": "Some note",
        }
    ]
    query_file = tmp_path / "test_queries.json"
    query_file.write_text(json.dumps(sample))

    loaded = cgv.load_queries(str(query_file))

    assert len(loaded) == 1
    q = loaded[0]
    assert q["id"] == "mq01"
    assert q["question"] == "Test question?"
    assert q["depth"] == 2
    assert q["expected_source_docs"] == ["doc_a", "doc_b"]
    assert q["expected_min_distinct_source_docs"] == 2
    assert q["graph_only"] is True
    assert q["notes"] == "Some note"
