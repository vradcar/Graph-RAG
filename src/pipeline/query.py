"""
Query CLI: natural language question -> Neo4j graph traversal -> LLM answer.

Usage:
    python -m src.pipeline.query --question "What accessories are compatible with the T9?"
"""
from dotenv import load_dotenv
load_dotenv()  # MUST be first — loads .env before any os.getenv() calls

import argparse
import os
import sys

from src.common.config import load_settings
from src.graph.store import Neo4jGraphStore
from src.llm.provider import build_instructor_client
from src.retrieval.graph_retriever import graph_retrieve, load_all_node_ids
from src.llm.generate import generate_answer, format_answer, QueryAnswer


def run_query(question: str, depth: int = 2, provider: str | None = None, model: str | None = None) -> str:
    """Run a query against the Neo4j knowledge graph and return a formatted answer."""
    answer = run_query_structured(question, depth, provider=provider, model=model)
    return format_answer(answer)


def run_query_structured(question: str, depth: int = 2, provider: str | None = None, model: str | None = None) -> QueryAnswer:
    """Run a query and return the raw QueryAnswer object."""
    settings = load_settings()
    neo4j_uri = settings["graph"]["neo4j_uri"]
    neo4j_user = settings["graph"]["neo4j_user"]
    neo4j_password = os.getenv("NEO4J_PASSWORD", settings["graph"]["neo4j_password"])
    model = model or settings["llm"]["model"]
    provider = provider or settings["llm"].get("provider", "groq")

    try:
        client = build_instructor_client(provider)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as store:
        known_ids = load_all_node_ids(store)
        print(f"Loaded {len(known_ids)} node IDs from Neo4j", file=sys.stderr)

        triples = graph_retrieve(store, client, model, question, known_ids, depth=depth)
        answer = generate_answer(client, model, question, triples)

    return answer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the Neo4j knowledge graph with natural language"
    )
    parser.add_argument("--question", required=True, help="Natural language question")
    parser.add_argument("--depth", type=int, default=2, help="Graph traversal depth")
    parser.add_argument("--provider", choices=["groq", "openai"], default=None,
                        help="LLM provider override (default: from settings.yaml)")
    parser.add_argument("--model", default=None,
                        help="Model name override (default: from settings.yaml)")
    args = parser.parse_args()

    result = run_query(args.question, depth=args.depth, provider=args.provider, model=args.model)
    print(result)


if __name__ == "__main__":
    main()
