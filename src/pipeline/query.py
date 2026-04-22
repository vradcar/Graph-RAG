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
from src.retrieval.graph_retriever import graph_retrieve
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
        # Keep the pipeline usable for demos by falling back to deterministic
        # answer generation in src.llm.generate when provider setup fails.
        print(f"WARNING: {e}", file=sys.stderr)
        print("WARNING: Falling back to deterministic non-LLM answer mode", file=sys.stderr)

    with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as store:
        triples = graph_retrieve(store, question, depth=depth)
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
