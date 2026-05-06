"""
Demo showcase: 8 queries run in graph mode vs vector mode side-by-side.

Each query was chosen to highlight a case where graph traversal produces
richer, relationship-aware answers than plain vector similarity search.

Usage:
    python -m scripts.demo_showcase                    # all 8 queries
    python -m scripts.demo_showcase --mode graph       # graph only
    python -m scripts.demo_showcase --mode vector      # vector only
    python -m scripts.demo_showcase --query 3          # run query #3 only
    python -m scripts.demo_showcase --depth 2          # traversal depth (graph/hybrid)

Prerequisites:
    - Neo4j running at bolt://localhost:7687
    - NEO4J_PASSWORD set in .env
    - data/raw/t9-thermostat.pdf ingested:  python -m src.pipeline.ingest
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 8 showcase queries — each annotated with WHY graph beats vector here

SHOWCASE_QUERIES = [
    {
        "id": 1,
        "question": "What accessories are compatible with the T9?",
        "graph_advantage": (
            "Graph follows COMPATIBLE_WITH edges from the T9 node directly, "
            "returning the exact accessory set with no false positives. "
            "Vector finds 'compatible' mentions in text chunks but can mix in "
            "accessories from unrelated products."
        ),
    },
    {
        "id": 2,
        "question": "What wiring configurations does the T9 support?",
        "graph_advantage": (
            "Graph traverses HAS_WIRING_CONFIG / CONNECTS_TO relationships and "
            "returns structured wiring nodes (2-wire, 4-wire, C-wire, etc.). "
            "Vector returns paragraphs that mention wiring — harder to extract "
            "a clean list from."
        ),
    },
    {
        "id": 3,
        "question": "What are the T9 specifications?",
        "graph_advantage": (
            "Both modes work here, but graph exposes HAS_ELECTRICAL_SPEC edges "
            "as structured triples. Vector retrieves the spec table as raw text."
        ),
    },
    {
        "id": 4,
        "question": "What is the modern replacement for the RTH6580WF?",
        "graph_advantage": (
            "Graph follows the REPLACED_BY chain (RTH6580WF → T9) and at depth=2 "
            "also surfaces what the T9 supports — the full migration picture. "
            "Vector has no way to traverse a replacement chain; it can only find "
            "documents that happen to mention both products together."
        ),
    },
    {
        "id": 5,
        "question": "Does the T9 need a C-wire for heat-only systems?",
        "graph_advantage": (
            "Multi-hop: T9 → REQUIRES → C-Wire → NEEDED_FOR → heat-only. "
            "Vector may return relevant paragraphs but cannot confirm the "
            "causal chain without traversing intermediate nodes."
        ),
    },
    {
        "id": 6,
        "question": "What HVAC system types work with the T9?",
        "graph_advantage": (
            "Graph finds COMPATIBLE_WITH edges pointing at HVACSystemType nodes "
            "(conventional, heat pump, dual fuel). Vector returns prose with the "
            "same info, but without the node type distinction."
        ),
    },
    {
        "id": 7,
        "question": "What are the T9 electrical specifications?",
        "graph_advantage": (
            "Graph returns HAS_ELECTRICAL_SPEC triples — voltage, current draw, "
            "frequency — as structured data. Vector returns the spec table as a "
            "text string that requires further parsing."
        ),
    },
    {
        "id": 8,
        "question": "List all discontinued thermostats and their replacements.",
        "graph_advantage": (
            "Graph can exhaustively traverse all REPLACED_BY edges to build the "
            "complete discontinued → replacement mapping. Vector can only surface "
            "documents that happen to mention specific model pairs — it cannot "
            "guarantee completeness."
        ),
    },
]


def _format_graph_hits(triples: list[tuple[str, str, str]]) -> str:
    if not triples:
        return "(no graph evidence)"
    lines = [f"- {src} --[{rel}]--> {tgt}" for src, rel, tgt in triples]
    return "\n".join(lines)


def _format_vector_hits(hits: list[dict]) -> str:
    if not hits:
        return "(no vector hits)"
    lines = []
    for hit in hits:
        doc_id = hit.get("id") or hit.get("node_id") or "(unknown)"
        text = hit.get("text", "")
        lines.append(f"- {doc_id}: {text}")
    return "\n".join(lines)


def _run_mode(question: str, mode: str, depth: int, vector_store, graph_store) -> str:
    """Run a single query in the given mode and return a formatted answer string."""
    from src.retrieval.graph_retriever import graph_retrieve

    try:
        if mode == "graph":
            triples = graph_retrieve(graph_store, question, depth=depth)
            return _format_graph_hits(list(triples))
        if mode == "vector":
            hits = vector_store.search(question, top_k=5)
            return _format_vector_hits(hits)
        return "[ERROR] Unsupported mode"
    except SystemExit:
        return "[ERROR] NEO4J_PASSWORD not set. Set it in .env and retry."
    except Exception as exc:
        return f"[ERROR] {exc}"


def _print_divider(char: str = "=", width: int = 76) -> str:
    return char * width


def _wrap(text: str, indent: int = 4) -> str:
    prefix = " " * indent
    return textwrap.fill(text, width=76, initial_indent=prefix, subsequent_indent=prefix)


def run_showcase(queries, modes: list[str], depth: int, output_path: str | None = None) -> None:
    lines: list[str] = []

    def emit(line: str = "") -> None:
        print(line)
        lines.append(line)

    emit()
    emit(_print_divider("#"))
    emit("#  Honeywell T9 GraphRAG — Demo Showcase                              #")
    emit("#  Comparing retrieval modes: graph vs vector                         #")
    emit(_print_divider("#"))

    from src.common.config import load_settings
    from src.graph.store import Neo4jGraphStore
    from src.retrieval.vector_store import SimpleVectorStore

    settings = load_settings()
    neo4j_uri = os.getenv("NEO4J_URI") or settings["graph"]["neo4j_uri"]
    neo4j_user = os.getenv("NEO4J_USER") or settings["graph"]["neo4j_user"]
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    if not neo4j_password:
        raise SystemExit("NEO4J_PASSWORD not set")

    docs_path = Path("data/raw/doc_chunks.json")
    with docs_path.open("r", encoding="utf-8") as f:
        doc_chunks = json.load(f)
    vector_store = SimpleVectorStore()
    vector_store.add_documents(doc_chunks)

    with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as graph_store:
        for entry in queries:
            emit()
            emit(_print_divider())
            emit(f"Query #{entry['id']}: {entry['question']}")
            emit(_print_divider())
            emit()
            emit("  WHY GRAPH WINS HERE:")
            emit(_wrap(entry["graph_advantage"]))
            emit()

            for mode in modes:
                emit(f"  --- {mode.upper()} MODE ---")
                answer_text = _run_mode(
                    entry["question"],
                    mode=mode,
                    depth=depth,
                    vector_store=vector_store,
                    graph_store=graph_store,
                )
                for line in answer_text.splitlines():
                    emit(f"    {line}")
                emit()

    emit(_print_divider())
    emit("Showcase complete.")
    emit(_print_divider())

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the T3 demo showcase: 8 queries in graph vs vector mode"
    )
    parser.add_argument(
        "--mode",
        choices=["graph", "vector", "hybrid", "both"],
        default="both",
        help="Which mode(s) to run. 'both' runs graph then vector side-by-side.",
    )
    parser.add_argument(
        "--query",
        type=int,
        default=None,
        help="Run only query #N (1-8). Omit to run all 8.",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Graph traversal depth (default 2).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write a text transcript of the showcase output",
    )
    args = parser.parse_args()

    if args.mode == "both":
        modes = ["graph", "vector"]
    else:
        modes = [args.mode]

    queries = SHOWCASE_QUERIES
    if args.query is not None:
        queries = [q for q in SHOWCASE_QUERIES if q["id"] == args.query]
        if not queries:
            print(f"No query with id={args.query}. Valid range: 1-8.", file=sys.stderr)
            sys.exit(1)

    run_showcase(queries, modes=modes, depth=args.depth, output_path=args.output)


if __name__ == "__main__":
    main()
