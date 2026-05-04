"""Unit tests for src.graph.provenance.scoped_delete_doc.

These tests use unittest.mock.MagicMock for the Neo4j ManagedTransaction so
they require no live database. They lock the 5-step Cypher sequence, the
parametrised $doc_id passing, the verified MENTIONED_IN direction
(entity -> :Document), and the orphan-step exclusion of :Document.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.graph.provenance import scoped_delete_doc


def _mk_tx(counts):
    """Build a MagicMock tx where consecutive .run().single() return dicts with 'c'."""
    tx = MagicMock()
    results = []
    for c in counts:
        single_obj = {"c": c} if c is not None else None
        result_mock = MagicMock()
        result_mock.single.return_value = single_obj
        results.append(result_mock)
    tx.run.side_effect = results
    return tx


def test_runs_five_step_sequence_in_order():
    tx = _mk_tx([1, 2, 3, 4, 1])
    scoped_delete_doc(tx, "x")
    assert tx.run.call_count == 5
    queries = [call.args[0] for call in tx.run.call_args_list]
    # Step 1: edges by source_doc
    assert "source_doc: $doc_id" in queries[0] and "DELETE r" in queries[0]
    # Step 2: MENTIONED_IN to :Document{doc_id}
    assert "MENTIONED_IN" in queries[1] and "Document" in queries[1]
    # Step 3: source_docs[] prune
    assert "source_docs" in queries[2] and "SET" in queries[2]
    # Step 4: orphan delete excluding :Document
    assert "size(n.source_docs) = 0" in queries[3]
    assert "NOT n:Document" in queries[3]
    assert "DETACH DELETE n" in queries[3]
    # Step 5: :Document detach-delete
    assert "MATCH (d:Document {doc_id: $doc_id})" in queries[4]
    assert "DETACH DELETE d" in queries[4]


def test_returns_counts_dict():
    tx = _mk_tx([10, 20, 30, 40, 1])
    out = scoped_delete_doc(tx, "doc_a")
    assert out == {
        "edges": 10,
        "mentioned_in": 20,
        "nodes_pruned": 30,
        "orphans": 40,
        "document": 1,
    }


def test_passes_doc_id_param():
    tx = _mk_tx([0, 0, 0, 0, 0])
    scoped_delete_doc(tx, "thp9045")
    for call in tx.run.call_args_list:
        # all calls must pass doc_id kwarg, not interpolate it
        assert call.kwargs.get("doc_id") == "thp9045"
        # ensure literal string of doc_id NOT spliced into the query body itself
        assert "thp9045" not in call.args[0]


def test_mentioned_in_direction_matches_loader():
    tx = _mk_tx([0, 0, 0, 0, 0])
    scoped_delete_doc(tx, "x")
    step2 = tx.run.call_args_list[1].args[0]
    # entity -> :Document direction (matches merge_node_with_provenance L118)
    assert "(e)-[m:MENTIONED_IN]->(:Document {doc_id: $doc_id})" in step2


def test_orphan_step_excludes_document_label():
    tx = _mk_tx([0, 0, 0, 0, 0])
    scoped_delete_doc(tx, "x")
    step4 = tx.run.call_args_list[3].args[0]
    assert "NOT n:Document" in step4


def test_handles_empty_results_gracefully():
    # Any/all .single() returning None should yield count 0, never crash.
    tx = _mk_tx([None, None, None, None, None])
    out = scoped_delete_doc(tx, "x")
    assert out == {
        "edges": 0,
        "mentioned_in": 0,
        "nodes_pruned": 0,
        "orphans": 0,
        "document": 0,
    }
