"""Regression: when the LLM (after retries) returns an invalid kind, extract_from_page
must log the rejection to reports/extraction_rejections.log and return an EMPTY
ExtractionResult so the page loop continues. The unfixed code path raised
ValidationError up the stack and crashed the ingest."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import ValidationError, BaseModel

from src.ingest.entity_extractor import extract_from_page, ExtractionResult


def _make_validation_error() -> ValidationError:
    class _Probe(BaseModel):
        x: int
    try:
        _Probe(x="not-an-int")  # type: ignore[arg-type]
    except ValidationError as e:
        return e
    raise AssertionError("ValidationError not raised by probe")


def test_invalid_kind_logged_and_returns_empty(tmp_path, monkeypatch):
    log_path = tmp_path / "rejections.log"
    import src.ingest.rejections as rej
    monkeypatch.setattr(rej, "REJECTION_LOG_PATH", log_path)

    client = MagicMock()
    client.chat.completions.create.side_effect = _make_validation_error()

    page = {"page_num": 7, "prose": "Some page text mentioning T9", "tables": []}

    with patch("src.ingest.entity_extractor.log_rejection") as mock_log:
        mock_log.side_effect = lambda **kwargs: rej.log_rejection(path=log_path, **kwargs)
        result = extract_from_page(client, "fake-model", page, doc_id="t9_install_guide")

    assert isinstance(result, ExtractionResult)
    assert result.nodes == []
    assert result.edges == []
    assert log_path.exists(), "rejection log file should have been written"
    records = [json.loads(line) for line in log_path.read_text().strip().splitlines()]
    assert len(records) == 1
    rec = records[0]
    assert rec["doc_id"] == "t9_install_guide"
    assert rec["page_num"] == 7
    assert rec["error_class"] == "ValidationError"
