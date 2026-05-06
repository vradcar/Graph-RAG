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
from typing import List, Optional, Tuple

from src.common.config import load_settings
from src.graph.store import Neo4jGraphStore
from src.llm.provider import build_instructor_client
from src.retrieval.graph_retriever import graph_retrieve, resolve_entities_against_graph
from src.retrieval.query_understanding import understand_query
from src.retrieval.vector_store import SimpleVectorStore
from src.llm.generate import generate_answer, format_answer, QueryAnswer


# Module-level cache so the vector store is built once per process
# (Streamlit reruns the app script on every interaction).
_VECTOR_STORE: Optional[SimpleVectorStore] = None


def _build_vector_store_from_neo4j(graph_store: Neo4jGraphStore) -> Optional[SimpleVectorStore]:
    """Build a bag-of-words vector store from all nodes in the graph."""
    try:
        rows = graph_store.run_cypher(
            "MATCH (n) WHERE n.node_id IS NOT NULL OR n.id IS NOT NULL "
            "RETURN coalesce(n.node_id, n.id) AS node_id, "
            "labels(n) AS labels, "
            "properties(n) AS props "
            "LIMIT 10000"
        )
    except Exception as e:
        print(f"[query] Could not build vector corpus from Neo4j: {e}", file=sys.stderr)
        return None

    docs = []
    for row in rows:
        node_id = row.get("node_id")
        if not node_id:
            continue
        text_parts: List[str] = [node_id]
        labels = row.get("labels") or []
        text_parts.extend(str(label) for label in labels)
        for k, v in (row.get("props") or {}).items():
            if k in ("node_id", "id"):
                continue
            if isinstance(v, str):
                text_parts.append(v)
            elif isinstance(v, list):
                text_parts.extend(str(item) for item in v if isinstance(item, str))
        docs.append({"node_id": node_id, "text": " ".join(p for p in text_parts if p)})

    if not docs:
        return None

    store = SimpleVectorStore()
    store.add_documents(docs)
    return store


def _get_vector_store(graph_store: Neo4jGraphStore) -> Optional[SimpleVectorStore]:
    """Lazy-build the vector store from Neo4j on first call (cached after that)."""
    global _VECTOR_STORE
    if _VECTOR_STORE is not None:
        return _VECTOR_STORE
    _VECTOR_STORE = _build_vector_store_from_neo4j(graph_store)
    return _VECTOR_STORE


def _vector_fallback(
    question: str,
    graph_store: Neo4jGraphStore,
    depth: int,
    extra_terms: List[str],
) -> List[Tuple[str, str, str]]:
    """Vector-search graph nodes, then pull their neighbors as triples."""
    vstore = _get_vector_store(graph_store)
    if vstore is None:
        return []

    # Augment the query with LLM-suggested search terms for better recall.
    query_text = question
    if extra_terms:
        query_text = question + " " + " ".join(extra_terms)

    hits = vstore.search(query_text, top_k=5)
    if not hits:
        return []

    triples: List[Tuple[str, str, str]] = []
    seen = set()
    # Use a smaller traversal depth for the fallback to keep context focused.
    fallback_depth = max(1, min(depth, 1))
    for hit in hits:
        node_id = hit.get("node_id")
        if not node_id or not graph_store.has_node(node_id):
            continue
        for triple in graph_store.neighbors_multi_hop(node_id, depth=fallback_depth):
            if triple not in seen:
                seen.add(triple)
                triples.append(triple)
    return triples


def run_query(question: str, depth: int = 2, provider: str | None = None, model: str | None = None) -> str:
    """Run a query against the Neo4j knowledge graph and return a formatted answer."""
    answer = run_query_structured(question, depth, provider=provider, model=model)
    return format_answer(answer)


def run_query_structured(question: str, depth: int = 2, provider: str | None = None, model: str | None = None) -> QueryAnswer:
    """Run a query and return the raw QueryAnswer object.

    Pipeline (when an entirely new and unseen query comes in):
      1. Fast path — regex/keyword graph retrieval.
      2. LLM query understanding — extract entities + intent, resolve against
         graph node IDs, traverse from each.
      3. Vector fallback — bag-of-words search over the node corpus, then
         pull 1-hop neighbors of each hit.
      4. LLM answer generation over the assembled triples.
    """
    settings = load_settings()
    # Env vars take precedence over settings.yaml so that Streamlit Community
    # Cloud secrets (and docker-compose overrides) work without editing the file.
    neo4j_uri = os.getenv("NEO4J_URI") or settings["graph"]["neo4j_uri"]
    neo4j_user = os.getenv("NEO4J_USER") or settings["graph"]["neo4j_user"]
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
        stage = "none"

        # Stage 1: regex/keyword fast path
        triples = list(graph_retrieve(store, question, depth=depth))
        if triples:
            stage = "fast_path"

        # Stage 2: LLM query understanding (only if fast path was empty)
        extra_terms: List[str] = []
        if not triples:
            parsed = understand_query(client, model, question)
            extra_terms = parsed.search_terms
            resolved_ids = resolve_entities_against_graph(store, parsed.entities)
            seen = set()
            for entity_id in resolved_ids:
                for triple in store.neighbors_multi_hop(entity_id, depth=depth):
                    if triple not in seen:
                        seen.add(triple)
                        triples.append(triple)
            if triples:
                stage = "llm_understanding"

        # Stage 3: vector fallback
        if not triples:
            triples = _vector_fallback(question, store, depth=depth, extra_terms=extra_terms)
            if triples:
                stage = "vector_fallback"

        # Stage 4: LLM answer generation
        answer = generate_answer(client, model, question, triples)
        answer.pipeline_stage = stage

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
