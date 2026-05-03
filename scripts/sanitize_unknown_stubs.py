"""Idempotent sanitizer for corpus JSON files.

Removes nodes with ``kind == "Unknown"`` and any edges whose endpoints reference
those (or any other) missing node ids. Safe to re-run: a second invocation on
an already-clean file reports zero removals.

Usage::

    python scripts/sanitize_unknown_stubs.py PATH [PATH ...]

If no paths are given, defaults to the glob
``data/processed/_*_corpus.json`` (excluding the ``_pre_gemini_backup/``
directory).

Background: ``src/pipeline/ingest.py`` previously synthesized
``kind="Unknown"`` stub nodes when an edge referenced a missing endpoint.
``Unknown`` is not in ``NODE_KIND`` (``src/graph/schema.py``), so corpora
written by older code paths cannot be loaded through ``EntityNode``. This
script cleans those corpora in-place without re-running LLM extraction.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path


def _default_paths() -> list[str]:
    paths: list[str] = []
    for p in sorted(glob.glob("data/processed/_*_corpus.json")):
        # Exclude any backup directory contents in case the glob expands there.
        if "_pre_gemini_backup" in p:
            continue
        paths.append(p)
    return paths


def sanitize_file(path: Path) -> dict:
    """Sanitize a single corpus JSON file in-place. Returns a stats dict."""
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    before_nodes = len(nodes)
    before_edges = len(edges)

    unknown_ids = {n["node_id"] for n in nodes if n.get("kind") == "Unknown"}
    cleaned_nodes = [n for n in nodes if n.get("kind") != "Unknown"]
    surviving_ids = {n["node_id"] for n in cleaned_nodes}

    cleaned_edges: list[dict] = []
    dropped_edges = 0
    for e in edges:
        src = e.get("source_id")
        tgt = e.get("target_id")
        if src in unknown_ids or tgt in unknown_ids:
            dropped_edges += 1
            continue
        if src not in surviving_ids or tgt not in surviving_ids:
            # Defensive: drop any other dangling edge too.
            dropped_edges += 1
            continue
        cleaned_edges.append(e)

    removed_nodes = before_nodes - len(cleaned_nodes)
    removed_edges = before_edges - len(cleaned_edges)

    if removed_nodes or removed_edges:
        data["nodes"] = cleaned_nodes
        data["edges"] = cleaned_edges
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    return {
        "path": str(path),
        "before_nodes": before_nodes,
        "after_nodes": len(cleaned_nodes),
        "before_edges": before_edges,
        "after_edges": len(cleaned_edges),
        "unknown_nodes_removed": len(unknown_ids),
        "removed_nodes": removed_nodes,
        "removed_edges": removed_edges,
        "dropped_dangling_edges": dropped_edges,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Corpus JSON paths to sanitize")
    args = parser.parse_args(argv)

    paths = args.paths or _default_paths()
    if not paths:
        print("No corpus paths provided and default glob matched nothing.", file=sys.stderr)
        return 1

    any_changes = False
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"WARN: not found, skipping: {path}", file=sys.stderr)
            continue
        stats = sanitize_file(path)
        changed = stats["removed_nodes"] or stats["removed_edges"]
        any_changes = any_changes or bool(changed)
        marker = "changed" if changed else "no changes"
        print(
            f"[{marker}] {stats['path']}: "
            f"nodes {stats['before_nodes']} -> {stats['after_nodes']} "
            f"(removed {stats['removed_nodes']}, of which Unknown={stats['unknown_nodes_removed']}); "
            f"edges {stats['before_edges']} -> {stats['after_edges']} "
            f"(dropped dangling {stats['dropped_dangling_edges']})"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
