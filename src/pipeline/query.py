import argparse
import json
from pathlib import Path

from src.graph.store import GraphStore
from src.llm.generate import generate_answer
from src.retrieval.graph_retriever import graph_retrieve
from src.retrieval.hybrid_retriever import hybrid_retrieve
from src.retrieval.vector_store import SimpleVectorStore


def load_graph_items(path: str = "data/processed/graph_items.json") -> dict:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def build_graph(graph_items: dict) -> GraphStore:
    store = GraphStore()

    for node in graph_items.get("nodes", []):
        node_id = node.pop("node_id")
        store.upsert_node(node_id, **node)

    for edge in graph_items.get("edges", []):
        store.upsert_edge(
            edge["source_id"],
            edge["target_id"],
            edge.get("relation", "RELATED_TO"),
        )

    return store


def load_sample_docs(path: str = "data/raw/doc_chunks.json") -> list:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run query against graph/vector/hybrid retrieval")
    parser.add_argument("--question", required=True, help="User question")
    parser.add_argument("--depth", type=int, default=1, help="Graph traversal depth")
    parser.add_argument("--mode", choices=["graph", "vector", "hybrid"], default="graph")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    graph_items = load_graph_items()
    graph_store = build_graph(graph_items)

    vector_store = SimpleVectorStore()
    vector_store.add_documents(load_sample_docs())

    if args.mode == "graph":
        graph_hits = graph_retrieve(graph_store, args.question, depth=args.depth)
        doc_hits = []
    elif args.mode == "vector":
        graph_hits = []
        doc_hits = vector_store.search(args.question, top_k=args.top_k)
    else:
        results = hybrid_retrieve(graph_store, vector_store, args.question, args.depth, args.top_k)
        graph_hits, doc_hits = results["graph_hits"], results["doc_hits"]

    answer = generate_answer(args.question, graph_hits, doc_hits)
    print(answer)


if __name__ == "__main__":
    main()
