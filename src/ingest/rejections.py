"""JSON-line rejection log writer for closed-world enforcement failures.

One line per rejection: {ts, doc_id, page_num, error_class, message, snippet}.
Phase 3's reports/ingest_failures.log is a superset; we use the same directory
to avoid log proliferation (per RESEARCH Q4)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REJECTION_LOG_PATH = Path("reports/extraction_rejections.log")


def log_rejection(
    doc_id: str,
    page_num: int,
    error_class: str,
    message: str,
    snippet: str = "",
    path: Path = REJECTION_LOG_PATH,
) -> None:
    """Append one JSON line describing an extraction rejection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "doc_id": doc_id,
        "page_num": page_num,
        "error_class": error_class,
        "message": message[:1000],   # cap to keep log readable
        "snippet": snippet[:500],
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
