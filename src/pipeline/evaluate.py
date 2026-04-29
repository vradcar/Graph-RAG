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
import sys
import time
from pathlib import Path

from src.common.config import load_settings
from src.graph.store import Neo4jGraphStore
from src.llm.provider import build_instructor_client
from src.retrieval.graph_retriever import graph_retrieve
from src.retrieval.vector_store import SimpleVectorStore
from src.retrieval.hybrid_retriever import hybrid_retrieve
from src.llm.generate import generate_answer


def run_eval(queries_path: str, output_path: str, provider: str | None = None, model: str | None = None) -> None:
    """Run evaluation pipeline against a set of demo queries."""
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

    # Load document chunks for vector/hybrid retrieval
    docs_path = Path("data/raw/doc_chunks.json")
    with docs_path.open("r", encoding="utf-8") as f:
        doc_chunks = json.load(f)

    vector_store = SimpleVectorStore()
    vector_store.add_documents(doc_chunks)

    with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as store:
        with Path(queries_path).open("r", encoding="utf-8") as f:
            queries = json.load(f)

        results = []
        for item in queries:
            question = item["question"]
            depth = item.get("depth", 2)

            # Graph-only
            g_start = time.perf_counter()
            graph_hits = graph_retrieve(store, question, depth=depth)
            graph_latency = time.perf_counter() - g_start

            # Vector-only
            v_start = time.perf_counter()
            vector_hits = vector_store.search(question, top_k=settings["retrieval"]["top_k_chunks"])
            vector_latency = time.perf_counter() - v_start

            # Hybrid (graph + vector) — measure combined time
            h_start = time.perf_counter()
            hybrid_hits = hybrid_retrieve(
                store,
                vector_store,
                question,
                depth=depth,
                top_k=settings["retrieval"]["top_k_chunks"],
            )
            hybrid_latency = time.perf_counter() - h_start

            # Optional answer generation using graph evidence (kept for report context)
            answer = generate_answer(client, model, question, graph_hits)

            results.append({
                "question": question,
                "depth": depth,
                "expected": item.get("expected", ""),
                "graph": {
                    "hit_count": len(graph_hits),
                    "latency_sec": round(graph_latency, 3),
                    "evidence": [e.model_dump() for e in answer.evidence],
                },
                "vector": {
                    "hit_count": len(vector_hits),
                    "latency_sec": round(vector_latency, 3),
                    "doc_ids": [d.get("id") for d in vector_hits],
                },
                "hybrid": {
                    "graph_hit_count": len(hybrid_hits.get("graph_hits", [])),
                    "doc_hit_count": len(hybrid_hits.get("doc_hits", [])),
                    "latency_sec": round(hybrid_latency, 3),
                    "doc_ids": [d.get("id") for d in hybrid_hits.get("doc_hits", [])],
                },
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
    parser.add_argument("--provider", choices=["groq", "openai"], default=None,
                        help="LLM provider override (default: from settings.yaml)")
    parser.add_argument("--model", default=None,
                        help="Model name override (default: from settings.yaml)")
    args = parser.parse_args()
    run_eval(args.queries, args.output, provider=args.provider, model=args.model)


if __name__ == "__main__":
    main()
