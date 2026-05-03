"""
Query CLI: natural language question -> Neo4j graph traversal -> LLM answer.

Usage:
    python -m src.pipeline.query --question "What accessories are compatible with the T9?"
    python -m src.pipeline.query --question "..." --mode vector
    python -m src.pipeline.query --question "..." --mode hybrid
"""
from dotenv import load_dotenv
load_dotenv()  # MUST be first — loads .env before any os.getenv() calls

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Tuple

from src.common.config import load_settings
from src.graph.store import Neo4jGraphStore
from src.llm.provider import build_instructor_client
from src.retrieval.graph_retriever import graph_retrieve
from src.retrieval.vector_store import SimpleVectorStore
from src.llm.generate import generate_answer, format_answer, QueryAnswer


def _load_vector_triples(question: str, top_k: int = 10) -> List[Tuple[str, str, str]]:
    """
    Build a SimpleVectorStore from data/processed/graph_items.json and search it.
    Returns triples (source, relation, target) for the top-k matching docs.
    Falls back to [] if the processed file does not exist yet.
    """
    graph_items_path = Path("data/processed/graph_items.json")
    if not graph_items_path.exists():
        return []

    with open(graph_items_path) as f:
        items = json.load(f)

    store = SimpleVectorStore()
    for edge in items.get("edges", []):
        src = edge.get("source_id") or edge.get("source", "")
        rel = edge.get("relation") or edge.get("type", "")
        tgt = edge.get("target_id") or edge.get("target", "")
        # Replace underscores with spaces so "COMPATIBLE_WITH" tokenises as
        # two words and overlaps with natural-language question tokens.
        text = f"{src} {rel} {tgt}".replace("_", " ")
        store.add_documents([{"text": text, "source": src, "relation": rel, "target": tgt}])
    for node in items.get("nodes", []):
        nid = node.get("node_id") or node.get("id", "")
        label = node.get("label", nid)
        kind = node.get("kind") or node.get("type", "Entity")
        text = f"{kind} {label} {nid}".replace("_", " ")
        store.add_documents([{"text": text, "source": nid, "relation": "IS_A", "target": kind}])

    hits = store.search(question, top_k=top_k)
    return [
        (h["source"], h["relation"], h["target"])
        for h in hits
        if h.get("source") and h.get("relation") and h.get("target")
    ]


def run_query(
    question: str,
    depth: int = 2,
    provider: str | None = None,
    model: str | None = None,
    mode: str = "graph",
) -> str:
    """Run a query against the knowledge graph and return a formatted string answer."""
    answer = run_query_structured(question, depth, provider=provider, model=model, mode=mode)
    return format_answer(answer)


def run_query_structured(
    question: str,
    depth: int = 2,
    provider: str | None = None,
    model: str | None = None,
    mode: str = "graph",
) -> QueryAnswer:
    """
    Run a query and return the raw QueryAnswer object.

    mode:
        "graph"  — Neo4j BFS traversal only (default, most relationship-aware)
        "vector" — keyword similarity over processed graph items
        "hybrid" — graph triples + vector triples merged, graph hits ranked first
    """
    settings = load_settings()
    neo4j_uri = settings["graph"]["neo4j_uri"]
    neo4j_user = settings["graph"]["neo4j_user"]
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    if not neo4j_password:
        print("ERROR: NEO4J_PASSWORD environment variable is required", file=sys.stderr)
        sys.exit(1)
    model = model or settings["llm"]["model"]
    provider = provider or settings["llm"].get("provider", "groq")

    client = None
    try:
        client = build_instructor_client(provider)
    except ValueError as e:
        print(f"WARNING: {e}", file=sys.stderr)
        print("WARNING: Falling back to deterministic non-LLM answer mode", file=sys.stderr)

    if mode == "vector":
        triples = _load_vector_triples(question)
        if not triples:
            return QueryAnswer(
                prose="",
                evidence=[],
                not_found=True,
                suggestion=(
                    "No processed graph data found for vector search. "
                    "Run the ingestion pipeline first: python -m src.pipeline.ingest"
                ),
            )
        return generate_answer(client, model, question, triples)

    if mode == "hybrid":
        graph_triples: List[Tuple[str, str, str]] = []
        try:
            with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as store:
                graph_triples = graph_retrieve(store, question, depth=depth)
        except Exception as e:
            print(f"WARNING: Graph retrieval failed in hybrid mode: {e}", file=sys.stderr)
        vector_triples = _load_vector_triples(question)
        seen: set = set()
        merged: List[Tuple[str, str, str]] = []
        for triple in graph_triples + vector_triples:
            if triple not in seen:
                seen.add(triple)
                merged.append(triple)
        return generate_answer(client, model, question, merged)

    # graph mode (default)
    with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as store:
        triples = graph_retrieve(store, question, depth=depth)
        return generate_answer(client, model, question, triples)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the Neo4j knowledge graph with natural language"
    )
    parser.add_argument("--question", required=True, help="Natural language question")
    parser.add_argument("--depth", type=int, default=2, help="Graph traversal depth")
    parser.add_argument(
        "--mode",
        choices=["graph", "vector", "hybrid"],
        default="graph",
        help="Retrieval mode: graph (default), vector, or hybrid",
    )
    parser.add_argument("--provider", choices=["groq", "openai"], default=None,
                        help="LLM provider override (default: from settings.yaml)")
    parser.add_argument("--model", default=None,
                        help="Model name override (default: from settings.yaml)")
    args = parser.parse_args()

    result = run_query(
        args.question,
        depth=args.depth,
        provider=args.provider,
        model=args.model,
        mode=args.mode,
    )
    print(result)


if __name__ == "__main__":
    main()
