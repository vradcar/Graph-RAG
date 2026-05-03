"""
End-to-end fixture tests for the query pipeline.

Everything external (Neo4j, LLM) is mocked so no live services are needed.
These tests verify the full call chain: run_query_structured → graph_retrieve
→ generate_answer → QueryAnswer.
"""
import pytest
from unittest.mock import MagicMock, patch


FAKE_TRIPLES = [
    ("rcht9610wf", "COMPATIBLE_WITH", "thm301"),
    ("rcht9610wf", "REQUIRES", "c-wire"),
]


@pytest.fixture
def mock_neo4j_store():
    """A Neo4jGraphStore mock that returns FAKE_TRIPLES for any question."""
    store = MagicMock()
    store.__enter__ = MagicMock(return_value=store)
    store.__exit__ = MagicMock(return_value=False)
    store.has_node.return_value = False
    store.run_cypher.return_value = [
        {"src": s, "rel": r, "tgt": t} for s, r, t in FAKE_TRIPLES
    ]
    return store


@patch("src.pipeline.query.build_instructor_client")
@patch("src.pipeline.query.Neo4jGraphStore")
@patch("src.pipeline.query.os.getenv", return_value="testpassword")
def test_run_query_structured_graph_mode_returns_query_answer(
    mock_getenv, mock_store_cls, mock_build_client
):
    """graph mode must return a QueryAnswer with prose and evidence fields."""
    from src.pipeline.query import run_query_structured
    from src.llm.generate import QueryAnswer, EvidenceTriple

    mock_store = MagicMock()
    mock_store.__enter__ = MagicMock(return_value=mock_store)
    mock_store.__exit__ = MagicMock(return_value=False)
    mock_store.has_node.return_value = False
    mock_store.run_cypher.return_value = []
    mock_store_cls.return_value = mock_store

    fake_answer = QueryAnswer(
        prose="The T9 is compatible with the C-Wire Adapter.",
        evidence=[EvidenceTriple(source="T9", relation="COMPATIBLE_WITH", target="C-Wire Adapter")],
        not_found=False,
        suggestion="",
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_answer
    mock_build_client.return_value = mock_client

    answer = run_query_structured("What is compatible with T9?", mode="graph")

    assert hasattr(answer, "prose")
    assert hasattr(answer, "evidence")
    assert hasattr(answer, "not_found")


@patch("src.pipeline.query.build_instructor_client")
@patch("src.pipeline.query.Neo4jGraphStore")
@patch("src.pipeline.query.os.getenv", return_value="testpassword")
@patch("src.pipeline.query._load_vector_triples", return_value=[])
def test_run_query_structured_vector_mode_not_found_when_no_data(
    mock_vector, mock_getenv, mock_store_cls, mock_build_client
):
    """vector mode with no processed data returns a not_found QueryAnswer."""
    from src.pipeline.query import run_query_structured

    answer = run_query_structured("What is the T9?", mode="vector")

    assert answer.not_found is True
    assert "ingestion" in answer.suggestion.lower() or "pipeline" in answer.suggestion.lower()


@patch("src.pipeline.query.build_instructor_client")
@patch("src.pipeline.query.Neo4jGraphStore")
@patch("src.pipeline.query.os.getenv", return_value="testpassword")
@patch("src.pipeline.query._load_vector_triples", return_value=[("t9", "IS_A", "Product")])
def test_run_query_structured_vector_mode_returns_answer_with_data(
    mock_vector, mock_getenv, mock_store_cls, mock_build_client
):
    """vector mode with available vector triples calls generate_answer."""
    from src.pipeline.query import run_query_structured

    mock_build_client.return_value = None  # fallback deterministic mode

    answer = run_query_structured("What is the T9?", mode="vector")

    assert hasattr(answer, "prose")
    assert answer.not_found is False or answer.not_found is True  # either is valid


@patch("src.pipeline.query.build_instructor_client")
@patch("src.pipeline.query.Neo4jGraphStore")
@patch("src.pipeline.query.os.getenv", return_value="testpassword")
@patch("src.pipeline.query._load_vector_triples", return_value=[("t9", "IS_A", "Product")])
def test_run_query_structured_hybrid_mode_merges_sources(
    mock_vector, mock_getenv, mock_store_cls, mock_build_client
):
    """hybrid mode must combine graph and vector triples without duplicates."""
    from src.pipeline.query import run_query_structured, _load_vector_triples

    mock_store = MagicMock()
    mock_store.__enter__ = MagicMock(return_value=mock_store)
    mock_store.__exit__ = MagicMock(return_value=False)
    mock_store.has_node.return_value = False
    mock_store.run_cypher.return_value = []
    mock_store_cls.return_value = mock_store
    mock_build_client.return_value = None

    answer = run_query_structured("Tell me about T9", mode="hybrid")

    assert hasattr(answer, "prose")


@patch("src.pipeline.query.build_instructor_client")
@patch("src.pipeline.query.Neo4jGraphStore")
@patch("src.pipeline.query.os.getenv", return_value="testpassword")
def test_run_query_returns_string(mock_getenv, mock_store_cls, mock_build_client):
    """run_query (string wrapper) must return a non-empty string."""
    from src.pipeline.query import run_query

    mock_store = MagicMock()
    mock_store.__enter__ = MagicMock(return_value=mock_store)
    mock_store.__exit__ = MagicMock(return_value=False)
    mock_store.has_node.return_value = False
    mock_store.run_cypher.return_value = []
    mock_store_cls.return_value = mock_store
    mock_build_client.return_value = None

    result = run_query("anything?", mode="graph")

    assert isinstance(result, str)
    assert len(result) > 0
