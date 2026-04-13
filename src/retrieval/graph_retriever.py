import re
from typing import List, Tuple
from src.graph.store import GraphStore


def extract_candidate_entities(question: str) -> List[str]:
    return re.findall(r"[A-Z]{2,}\d+[A-Z0-9]*|[A-Z]{2,}-\d+", question)


def graph_retrieve(graph_store: GraphStore, question: str, depth: int = 1) -> List[Tuple[str, str, str]]:
    entities = extract_candidate_entities(question)
    context = []

    for entity in entities:
        if graph_store.has_node(entity):
            context.extend(graph_store.neighbors_multi_hop(entity, depth=depth))

    return context
