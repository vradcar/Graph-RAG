"""
Unit tests for src/ingest/entity_extractor.py.
All Groq API calls are mocked — no API key required.
"""
import os
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError


def test_closed_world_enum_rejects_invalid_relation():
    from src.ingest.entity_extractor import ExtractedEdge
    with pytest.raises((ValidationError, ValueError)):
        ExtractedEdge(source_id="a", target_id="b", relation="WORKS_WITH")


def test_closed_world_enum_rejects_invalid_kind():
    from src.ingest.entity_extractor import ExtractedNode
    with pytest.raises((ValidationError, ValueError)):
        ExtractedNode(node_id="x", label="x", kind="Device")


def test_valid_extraction_result_accepted():
    from src.ingest.entity_extractor import ExtractedNode, ExtractedEdge, ExtractionResult
    node = ExtractedNode(node_id="rcht9510wf", label="T9 Thermostat", kind="Product")
    edge = ExtractedEdge(source_id="rcht9510wf", target_id="thm301", relation="COMPATIBLE_WITH")
    result = ExtractionResult(nodes=[node], edges=[edge])
    assert len(result.nodes) == 1
    assert len(result.edges) == 1


def test_build_client_raises_without_api_key():
    from src.ingest.entity_extractor import build_client
    original = os.environ.pop("GROQ_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            build_client()
    finally:
        if original:
            os.environ["GROQ_API_KEY"] = original


def test_extract_from_page_returns_empty_for_blank_page():
    """Blank page (no prose, no tables) should return empty ExtractionResult without calling LLM."""
    from src.ingest.entity_extractor import extract_from_page, ExtractionResult
    mock_client = MagicMock()
    blank_page = {"page_num": 1, "prose": "  ", "tables": []}
    result = extract_from_page(mock_client, "llama-3.1-8b-instant", blank_page)
    assert isinstance(result, ExtractionResult)
    assert len(result.nodes) == 0
    assert len(result.edges) == 0
    # LLM should NOT be called for blank pages
    mock_client.chat.completions.create.assert_not_called()


def test_extract_from_page_calls_groq_with_correct_roles():
    """Non-blank page should call the LLM with system + user messages."""
    from src.ingest.entity_extractor import extract_from_page, ExtractionResult
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = ExtractionResult()
    page = {"page_num": 2, "prose": "The T9 thermostat model RCHT9510WF.", "tables": []}
    extract_from_page(mock_client, "llama-3.1-8b-instant", page)
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args[1]
    messages = call_kwargs["messages"]
    roles = [m["role"] for m in messages]
    assert "system" in roles
    assert "user" in roles
