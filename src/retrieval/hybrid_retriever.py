from typing import Dict, List, Tuple
from src.graph.store import GraphStore
from src.retrieval.graph_retriever import graph_retrieve
from src.retrieval.vector_store import SimpleVectorStore


def hybrid_retrieve(
    graph_store: GraphStore,
    vector_store: SimpleVectorStore,
    question: str,
    depth: int,
    top_k: int,
) -> Dict[str, List]:
    graph_hits: List[Tuple[str, str, str]] = graph_retrieve(graph_store, question, depth=depth)
    doc_hits: List[Dict] = vector_store.search(question, top_k=top_k)
    return {"graph_hits": graph_hits, "doc_hits": doc_hits}
