import argparse
import json
import time
from pathlib import Path

from src.pipeline.query import build_graph, load_graph_items, load_sample_docs
from src.retrieval.graph_retriever import graph_retrieve
from src.retrieval.hybrid_retriever import hybrid_retrieve
from src.retrieval.vector_store import SimpleVectorStore


def run_eval(queries_path: str, output_path: str) -> None:
    graph_items = load_graph_items()
    graph_store = build_graph(graph_items)

    vector_store = SimpleVectorStore()
    vector_store.add_documents(load_sample_docs())

    with Path(queries_path).open("r", encoding="utf-8") as file:
        queries = json.load(file)

    results = []
    for item in queries:
        question = item["question"]
        depth = item.get("depth", 2)

        start = time.perf_counter()
        graph_hits = graph_retrieve(graph_store, question, depth=depth)
        graph_time = time.perf_counter() - start

        start = time.perf_counter()
        vector_hits = vector_store.search(question, top_k=5)
        vector_time = time.perf_counter() - start

        start = time.perf_counter()
        hybrid_hits = hybrid_retrieve(graph_store, vector_store, question, depth=depth, top_k=5)
        hybrid_time = time.perf_counter() - start

        results.append(
            {
                "question": question,
                "depth": depth,
                "graph": {"hit_count": len(graph_hits), "latency_sec": graph_time},
                "vector": {"hit_count": len(vector_hits), "latency_sec": vector_time},
                "hybrid": {
                    "graph_hit_count": len(hybrid_hits["graph_hits"]),
                    "doc_hit_count": len(hybrid_hits["doc_hits"]),
                    "latency_sec": hybrid_time,
                },
                "expected": item.get("expected"),
            }
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2)

    print(f"Saved evaluation results to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate graph, vector, and hybrid retrieval")
    parser.add_argument("--queries", default="data/eval/queries.json")
    parser.add_argument("--output", default="data/eval/results.json")
    args = parser.parse_args()
    run_eval(args.queries, args.output)


if __name__ == "__main__":
    main()
