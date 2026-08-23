"""
End-to-end fixture tests for the query pipeline.

Everything external (Neo4j, LLM) is mocked so no live services are needed.
These tests verify the full call chain: run_query_structured's four-stage
fallback (fast path -> LLM query understanding -> vector fallback -> answer
generation), each stage only running if the previous one found nothing.
"""
import pytest
from unittest.mock import MagicMock, patch


FAKE_TRIPLES = [
    ("rcht9610wf", "COMPATIBLE_WITH", "thm301"),
    ("rcht9610wf", "REQUIRES", "c-wire"),
]


def _mock_store():
    """A Neo4jGraphStore mock usable as a context manager."""
    store = MagicMock()
    store.__enter__ = MagicMock(return_value=store)
    store.__exit__ = MagicMock(return_value=False)
    return store


@patch("src.pipeline.query.build_instructor_client")
@patch("src.pipeline.query.Neo4jGraphStore")
@patch("src.pipeline.query.os.getenv", return_value="testpassword")
@patch("src.pipeline.query.graph_retrieve")
def test_run_query_structured_fast_path_returns_query_answer(
    mock_graph_retrieve, mock_getenv, mock_store_cls, mock_build_client
):
    """When the regex fast path finds triples, generation runs on them directly
    and no LLM query-understanding or vector fallback is needed."""
    from src.pipeline.query import run_query_structured
    from src.llm.generate import QueryAnswer, EvidenceTriple

    mock_graph_retrieve.return_value = FAKE_TRIPLES
    mock_store_cls.return_value = _mock_store()

    fake_answer = QueryAnswer(
        prose="The T9 is compatible with the C-Wire Adapter.",
        evidence=[EvidenceTriple(source="T9", relation="COMPATIBLE_WITH", target="C-Wire Adapter")],
        not_found=False,
        suggestion="",
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_answer
    mock_build_client.return_value = mock_client

    answer = run_query_structured("What is compatible with T9?")

    assert hasattr(answer, "prose")
    assert hasattr(answer, "evidence")
    assert hasattr(answer, "not_found")
    assert answer.pipeline_stage == "fast_path"


@patch("src.pipeline.query.build_instructor_client")
@patch("src.pipeline.query.Neo4jGraphStore")
@patch("src.pipeline.query.os.getenv", return_value="testpassword")
@patch("src.pipeline.query.resolve_entities_against_graph")
@patch("src.pipeline.query.understand_query")
@patch("src.pipeline.query.graph_retrieve")
def test_run_query_structured_llm_understanding_stage(
    mock_graph_retrieve, mock_understand, mock_resolve, mock_getenv, mock_store_cls, mock_build_client
):
    """When the fast path finds nothing, LLM query understanding resolves
    entities against the graph and BFS-traverses from each match."""
    from src.pipeline.query import run_query_structured
    from src.retrieval.query_understanding import QueryUnderstanding

    mock_graph_retrieve.return_value = []
    mock_understand.return_value = QueryUnderstanding(
        entities=["T9"], intent="compatibility", search_terms=["compatible"]
    )
    mock_resolve.return_value = ["rcht9610wf"]

    mock_store = _mock_store()
    mock_store.neighbors_multi_hop.return_value = FAKE_TRIPLES
    mock_store_cls.return_value = mock_store

    mock_build_client.return_value = MagicMock()  # non-None so understand_query is exercised

    answer = run_query_structured("Tell me about the T9's compatible accessories")

    assert answer.pipeline_stage == "llm_understanding"
    mock_store.neighbors_multi_hop.assert_called_with("rcht9610wf", depth=2)


@patch("src.pipeline.query.build_instructor_client")
@patch("src.pipeline.query.Neo4jGraphStore")
@patch("src.pipeline.query.os.getenv", return_value="testpassword")
@patch("src.pipeline.query._vector_fallback")
@patch("src.pipeline.query.graph_retrieve")
def test_run_query_structured_not_found_when_all_stages_empty(
    mock_graph_retrieve, mock_vector_fallback, mock_getenv, mock_store_cls, mock_build_client
):
    """When every stage comes up empty, the pipeline returns a not_found
    answer with a guidance suggestion instead of hallucinating."""
    from src.pipeline.query import run_query_structured

    mock_graph_retrieve.return_value = []
    mock_vector_fallback.return_value = []
    mock_store_cls.return_value = _mock_store()
    mock_build_client.return_value = None  # forces query_understanding's no-op stub

    answer = run_query_structured("What is the meaning of life?")

    assert answer.not_found is True
    assert answer.suggestion  # a rephrasing suggestion is always provided
    assert answer.pipeline_stage == "none"


@patch("src.pipeline.query.build_instructor_client")
@patch("src.pipeline.query.Neo4jGraphStore")
@patch("src.pipeline.query.os.getenv", return_value="testpassword")
@patch("src.pipeline.query._vector_fallback")
@patch("src.pipeline.query.graph_retrieve")
def test_run_query_structured_vector_fallback_returns_answer_with_data(
    mock_graph_retrieve, mock_vector_fallback, mock_getenv, mock_store_cls, mock_build_client
):
    """When graph retrieval (fast path + LLM understanding) finds nothing but
    the vector fallback does, generation still runs on that evidence."""
    from src.pipeline.query import run_query_structured

    mock_graph_retrieve.return_value = []
    mock_vector_fallback.return_value = [("t9", "MENTIONED_IN", "t9_install_guide")]
    mock_store_cls.return_value = _mock_store()
    mock_build_client.return_value = None  # deterministic fallback answer mode

    answer = run_query_structured("What does the wireless sensor need?")

    assert hasattr(answer, "prose")
    assert answer.pipeline_stage == "vector_fallback"


@patch("src.pipeline.query.build_instructor_client")
@patch("src.pipeline.query.Neo4jGraphStore")
@patch("src.pipeline.query.os.getenv", return_value="testpassword")
@patch("src.pipeline.query.graph_retrieve")
def test_run_query_returns_string(mock_graph_retrieve, mock_getenv, mock_store_cls, mock_build_client):
    """run_query (string wrapper) must return a non-empty formatted string."""
    from src.pipeline.query import run_query

    mock_graph_retrieve.return_value = FAKE_TRIPLES
    mock_store_cls.return_value = _mock_store()
    mock_build_client.return_value = None  # deterministic fallback answer mode

    result = run_query("anything?")

    assert isinstance(result, str)
    assert len(result) > 0
