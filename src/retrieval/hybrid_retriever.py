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


def rank_hybrid_results(
    graph_hits: List[Tuple[str, str, str]],
    doc_hits: List[Dict],
) -> List[Tuple[str, str, str]]:
    """
    Merge graph and vector hits into a ranked triple list.

    Ranking priority:
      1. Triples present in BOTH graph and vector results (highest confidence)
      2. Graph-only triples (structured relationship, no vector match)
      3. Vector-only triples (text match, no graph path)

    Duplicate triples are removed; first-seen ordering is preserved within each tier.
    """
    graph_set = set(graph_hits)

    vector_triples: List[Tuple[str, str, str]] = []
    for doc in doc_hits:
        if doc.get("source") and doc.get("relation") and doc.get("target"):
            vector_triples.append((doc["source"], doc["relation"], doc["target"]))
    vector_set = set(vector_triples)

    both = [t for t in graph_hits if t in vector_set]
    graph_only = [t for t in graph_hits if t not in vector_set]
    vector_only = [t for t in vector_triples if t not in graph_set]

    # Deduplicate while preserving order within each tier
    seen: set = set()
    ranked: List[Tuple[str, str, str]] = []
    for triple in both + graph_only + vector_only:
        if triple not in seen:
            seen.add(triple)
            ranked.append(triple)
    return ranked
