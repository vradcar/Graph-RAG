"""JSONL failure-log appender for batch ingest (BATCH-03).

One JSON object per line, append-only, gitignored. Used by
``scripts/batch_ingest.py`` (Wave 1) to record per-doc failures so the loop
can continue past the first failure and surface all problems in a single
run.

Public API: ``log_failure(doc_id, stage, exc, *, log_path=None) -> Path``
"""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

__all__ = ["log_failure", "DEFAULT_LOG_PATH"]


DEFAULT_LOG_PATH: Path = Path("reports/ingest_failures.log")


def log_failure(
    doc_id: str,
    stage: str,
    exc: BaseException,
    *,
    log_path: Path | None = None,
) -> Path:
    """Append a single JSONL entry describing one failure.

    Args:
        doc_id:    Manifest doc_id of the failing document.
        stage:     Pipeline stage where the failure occurred. Documented
                   stages are {"extract", "load", "scoped_delete",
                   "neo4j_load"} but no enum validation is enforced —
                   BATCH-03 only requires structured entries, not stage
                   validation.
        exc:       The exception instance. Its class name and message are
                   recorded; ``traceback.format_exc(limit=10)`` captures
                   the active traceback when called from inside an
                   ``except`` block.
        log_path:  Override the default ``reports/ingest_failures.log``
                   (used by tests via ``tmp_path``). Parent directory is
                   auto-created.

    Returns:
        The ``Path`` written to, so callers can report it in CLI output.

    Notes:
        ``ensure_ascii=False`` so unicode messages are preserved verbatim
        in the log (matches modern JSONL conventions). The file is opened
        with ``mode="a"`` and ``encoding="utf-8"``.
    """
    path = log_path if log_path is not None else DEFAULT_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "doc_id": doc_id,
        "stage": stage,
        "error_class": type(exc).__name__,
        "message": str(exc),
        "snippet": traceback.format_exc(limit=10),
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return path
