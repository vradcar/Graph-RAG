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
import os
import sys
import textwrap
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


def _run_mode(question: str, mode: str, depth: int) -> str:
    """Run a single query in the given mode and return a formatted answer string."""
    from src.pipeline.query import run_query
    try:
        return run_query(question, depth=depth, mode=mode)
    except SystemExit:
        return "[ERROR] NEO4J_PASSWORD not set. Set it in .env and retry."
    except Exception as exc:
        return f"[ERROR] {exc}"


def _print_divider(char: str = "=", width: int = 76) -> None:
    print(char * width)


def _wrap(text: str, indent: int = 4) -> str:
    prefix = " " * indent
    return textwrap.fill(text, width=76, initial_indent=prefix, subsequent_indent=prefix)


def run_showcase(queries, modes: list[str], depth: int) -> None:
    print()
    _print_divider("#")
    print("#  Honeywell T9 GraphRAG — Demo Showcase                              #")
    print("#  Comparing retrieval modes: graph vs vector                         #")
    _print_divider("#")

    for entry in queries:
        print()
        _print_divider()
        print(f"Query #{entry['id']}: {entry['question']}")
        _print_divider()
        print()
        print("  WHY GRAPH WINS HERE:")
        print(_wrap(entry["graph_advantage"]))
        print()

        for mode in modes:
            print(f"  --- {mode.upper()} MODE ---")
            answer_text = _run_mode(entry["question"], mode=mode, depth=depth)
            for line in answer_text.splitlines():
                print(f"    {line}")
            print()

    _print_divider()
    print("Showcase complete.")
    _print_divider()


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

    run_showcase(queries, modes=modes, depth=args.depth)


if __name__ == "__main__":
    main()
