import json
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST_PATH = Path("data/raw/manifest.json")


def load_manifest(path: Path | str = DEFAULT_MANIFEST_PATH) -> list[dict[str, Any]]:
    """Return the documents list from the manifest JSON file."""
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data["documents"]


def get_doc(doc_id: str, path: Path | str = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    """Look up a single doc by doc_id; raise KeyError if not found."""
    for doc in load_manifest(path):
        if doc["doc_id"] == doc_id:
            return doc
    raise KeyError(f"doc_id not in manifest: {doc_id}")
