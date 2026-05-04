"""
Schema and invariant tests for data/eval/multi_doc_queries.json.

Guards the >=6 / >=2-doc / >=2-graph-only invariants for QUALITY-01.
No Neo4j, no LLM, no network — pure file-based assertions.
"""
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module-scope fixtures — JSON loaded once per test session
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
QUERIES_PATH = REPO_ROOT / "data" / "eval" / "multi_doc_queries.json"
MANIFEST_PATH = REPO_ROOT / "data" / "raw" / "manifest.json"

REQUIRED_FIELDS = {
    "id",
    "question",
    "depth",
    "expected_source_docs",
    "expected_min_distinct_source_docs",
    "graph_only",
    "notes",
}


@pytest.fixture(scope="module")
def queries():
    """Load multi_doc_queries.json once for the test session."""
    with open(QUERIES_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def canonical_doc_ids():
    """Read canonical doc_id slugs from manifest.json at test time (not hard-coded)."""
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    return {doc["doc_id"] for doc in manifest["documents"]}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_query_set_has_at_least_6_questions(queries):
    """The query set file loads, is a list, and has at least 6 entries."""
    assert isinstance(queries, list), "multi_doc_queries.json must be a JSON array"
    assert len(queries) >= 6, f"Expected >=6 queries, got {len(queries)}"


def test_every_query_has_required_fields(queries):
    """Each entry contains all required fields."""
    for q in queries:
        missing = REQUIRED_FIELDS - set(q.keys())
        assert not missing, (
            f"Query {q.get('id', '?')} is missing required fields: {missing}"
        )


def test_ids_are_unique(queries):
    """No duplicate id values."""
    seen = set()
    for q in queries:
        qid = q["id"]
        assert qid not in seen, f"Duplicate id found: {qid!r}"
        seen.add(qid)


def test_expected_source_docs_are_canonical(queries, canonical_doc_ids):
    """Every expected_source_docs entry must be a doc_id from manifest.json."""
    for q in queries:
        unknown = set(q["expected_source_docs"]) - canonical_doc_ids
        assert not unknown, (
            f"Query {q['id']} references unknown doc_ids: {unknown}. "
            f"Canonical ids from manifest.json: {canonical_doc_ids}"
        )


def test_each_query_spans_at_least_two_docs(queries):
    """Every query's expected_source_docs has >=2 distinct values and expected_min_distinct_source_docs >= 2."""
    for q in queries:
        distinct = set(q["expected_source_docs"])
        assert len(distinct) >= 2, (
            f"Query {q['id']} needs >=2 distinct expected_source_docs, "
            f"got {len(distinct)}: {distinct}"
        )
        assert q["expected_min_distinct_source_docs"] >= 2, (
            f"Query {q['id']} expected_min_distinct_source_docs must be >=2, "
            f"got {q['expected_min_distinct_source_docs']}"
        )


def test_at_least_two_graph_only_questions(queries):
    """At least 2 questions must be marked graph_only=true (QUALITY-04 precondition)."""
    graph_only_count = sum(1 for q in queries if q["graph_only"])
    assert graph_only_count >= 2, (
        f"QUALITY-04 requires >=2 graph_only=true questions, got {graph_only_count}"
    )


def test_questions_extract_an_entity_or_trigger_replacement_fallback(queries):
    """
    For each question, either extract_candidate_entities returns >=1 token,
    OR the question text contains a replacement keyword so the Cypher fallback fires.

    This test imports extract_candidate_entities directly — no Neo4j needed.
    """
    from src.retrieval.graph_retriever import extract_candidate_entities

    REPLACEMENT_KEYWORDS = {"replacement", "replace", "replaced"}

    for q in queries:
        question = q["question"]
        entities = extract_candidate_entities(question)
        has_entities = len(entities) >= 1
        has_replacement_keyword = any(kw in question.lower() for kw in REPLACEMENT_KEYWORDS)

        assert has_entities or has_replacement_keyword, (
            f"Query {q['id']} would produce no graph context: "
            f"extract_candidate_entities returned {entities!r} and "
            f"no replacement keyword found in: {question!r}"
        )
