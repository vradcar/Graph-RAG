"""
Evaluate query pipeline against demo queries.

Usage:
    python -m src.pipeline.evaluate
    python -m src.pipeline.evaluate --queries data/eval/queries.json --output data/eval/results.json
"""
from dotenv import load_dotenv
load_dotenv()

import argparse
import json
import os
import time
from pathlib import Path

from src.common.config import load_settings
from src.graph.store import Neo4jGraphStore
from src.llm.provider import build_instructor_client
from src.retrieval.graph_retriever import load_all_node_ids, graph_retrieve
from src.llm.generate import generate_answer


def run_eval(queries_path: str, output_path: str) -> None:
    """Run evaluation pipeline against a set of demo queries."""
    settings = load_settings()
    neo4j_uri = settings["graph"]["neo4j_uri"]
    neo4j_user = settings["graph"]["neo4j_user"]
    neo4j_password = os.getenv("NEO4J_PASSWORD", settings["graph"]["neo4j_password"])
    model = settings["llm"]["model"]
    provider = settings["llm"].get("provider", "groq")

    client = build_instructor_client(provider)

    with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as store:
        known_ids = load_all_node_ids(store)

        with Path(queries_path).open("r", encoding="utf-8") as f:
            queries = json.load(f)

        results = []
        for item in queries:
            question = item["question"]
            depth = item.get("depth", 2)

            start = time.perf_counter()
            triples = graph_retrieve(store, client, model, question, known_ids, depth=depth)
            answer = generate_answer(client, model, question, triples)
            latency = time.perf_counter() - start

            results.append({
                "question": question,
                "depth": depth,
                "answer": answer.prose,
                "evidence": [e.model_dump() for e in answer.evidence],
                "not_found": answer.not_found,
                "latency_sec": round(latency, 3),
                "expected": item.get("expected", ""),
            })

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Evaluated {len(results)} queries. Saved to {output_path}")


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Evaluate query pipeline against demo queries")
    parser.add_argument(
        "--queries",
        default=settings["evaluation"]["queries_file"],
        help="Path to queries JSON file",
    )
    parser.add_argument(
        "--output",
        default=settings["evaluation"]["output_file"],
        help="Path to write results JSON",
    )
    args = parser.parse_args()
    run_eval(args.queries, args.output)


if __name__ == "__main__":
    main()
