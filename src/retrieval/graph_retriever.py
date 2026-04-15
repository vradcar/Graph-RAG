"""
Graph retriever with LLM-based entity resolution and per-relation Cypher queries.

Usage:
    from src.retrieval.graph_retriever import graph_retrieve, load_all_node_ids
"""
import sys
from typing import List, Tuple

import instructor
from pydantic import BaseModel, Field

from src.graph.store import Neo4jGraphStore


class EntityResolution(BaseModel):
    """LLM output: node IDs relevant to a user question."""
    node_ids: List[str] = Field(description="Node IDs from the knowledge graph relevant to the question")


ENTITY_RESOLUTION_SYSTEM = (
    "You are a graph entity resolver for an HVAC product knowledge graph.\n"
    "Given a user question and a list of known node IDs, return the node IDs that are relevant to answering the question.\n"
    "Only return node IDs from the provided list - do not invent new ones."
)


def load_all_node_ids(store: Neo4jGraphStore) -> List[str]:
    """Load all node_ids from Neo4j. Capped at 200 to avoid prompt bloat.

    NOTE: For graphs with >200 nodes, consider a pre-filtering strategy
    (e.g., embedding similarity on node labels) before passing to the LLM.
    """
    with store._driver.session() as session:
        result = session.run(
            "MATCH (n) RETURN n.node_id AS node_id ORDER BY n.node_id LIMIT 200"
        )
        return [record["node_id"] for record in result]


def resolve_entities(
    client: instructor.Instructor,
    model: str,
    question: str,
    known_ids: List[str],
) -> List[str]:
    """Use LLM to resolve which node IDs are relevant to the question."""
    result = client.chat.completions.create(
        model=model,
        response_model=EntityResolution,
        max_retries=2,
        messages=[
            {"role": "system", "content": ENTITY_RESOLUTION_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"Known node IDs:\n{', '.join(known_ids)}"
                ),
            },
        ],
    )
    return result.node_ids


# Per-relation Cypher queries using undirected matching to catch both directions
RELATION_QUERIES = {
    "COMPATIBLE_WITH": (
        "MATCH (a {node_id: $node_id})-[r:COMPATIBLE_WITH]-(b) "
        "RETURN a.node_id AS src, 'COMPATIBLE_WITH' AS rel, b.node_id AS tgt"
    ),
    "REPLACES": (
        "MATCH (a {node_id: $node_id})-[r:REPLACES]-(b) "
        "RETURN a.node_id AS src, 'REPLACES' AS rel, b.node_id AS tgt"
    ),
    "SUPPORTS_WIRING": (
        "MATCH (a {node_id: $node_id})-[r:SUPPORTS_WIRING]-(b) "
        "RETURN a.node_id AS src, 'SUPPORTS_WIRING' AS rel, b.node_id AS tgt"
    ),
    "HAS_SPEC": (
        "MATCH (a {node_id: $node_id})-[r:HAS_SPEC]-(b) "
        "RETURN a.node_id AS src, 'HAS_SPEC' AS rel, b.node_id AS tgt"
    ),
}


def retrieve_graph_context(
    store: Neo4jGraphStore,
    node_ids: List[str],
    depth: int = 2,
) -> List[Tuple[str, str, str]]:
    """Retrieve triples via per-relation Cypher queries and BFS multi-hop."""
    seen: set = set()
    triples: List[Tuple[str, str, str]] = []

    for node_id in node_ids:
        # Per-relation targeted queries
        with store._driver.session() as session:
            for cypher in RELATION_QUERIES.values():
                result = session.run(cypher, node_id=node_id)
                for record in result:
                    triple = (record["src"], record["rel"], record["tgt"])
                    if triple not in seen:
                        seen.add(triple)
                        triples.append(triple)

        # BFS multi-hop for broader context
        bfs_triples = store.neighbors_multi_hop(node_id, depth=depth)
        for triple in bfs_triples:
            if triple not in seen:
                seen.add(triple)
                triples.append(triple)

    return triples


def graph_retrieve(
    store: Neo4jGraphStore,
    client: instructor.Instructor,
    model: str,
    question: str,
    known_ids: List[str],
    depth: int = 2,
) -> List[Tuple[str, str, str]]:
    """Main entry point: resolve entities via LLM, validate, retrieve graph context."""
    resolved = resolve_entities(client, model, question, known_ids)

    # Validate resolved IDs against the actual graph
    valid_ids = []
    for nid in resolved:
        if store.has_node(nid):
            valid_ids.append(nid)
        else:
            print(f"[graph_retriever] Filtered out unknown node_id: {nid}", file=sys.stderr)

    if not valid_ids:
        return []

    return retrieve_graph_context(store, valid_ids, depth=depth)
