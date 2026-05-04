"""Unit tests for src/ingest/manifest.py."""
import pytest
from pathlib import Path

from src.ingest.manifest import load_manifest, get_doc

# Use absolute path so tests work regardless of cwd
MANIFEST_PATH = Path(__file__).parents[2] / "data" / "raw" / "manifest.json"


def test_manifest_has_four_entries():
    docs = load_manifest(MANIFEST_PATH)
    assert len(docs) == 4


def test_manifest_doc_ids():
    docs = load_manifest(MANIFEST_PATH)
    assert {d["doc_id"] for d in docs} == {
        "t9_install_guide",
        "t6_pro_install",
        "thp9045_wiring_module",
        "t10_pro_user_guide",
    }


def test_thp9045_pages_filter():
    doc = get_doc("thp9045_wiring_module", MANIFEST_PATH)
    assert doc["pages"] == [1, 4]


def test_t9_sku():
    doc = get_doc("t9_install_guide", MANIFEST_PATH)
    assert doc["sku"] == "T9"


def test_get_doc_missing_raises_key_error():
    with pytest.raises(KeyError):
        get_doc("does_not_exist", MANIFEST_PATH)
