import re
from typing import List, Tuple
from src.graph.store import GraphStore


def extract_candidate_entities(question: str) -> List[str]:
    # Matches hyphen-separated uppercase tokens (WALL-PLATE-A, REDLINK-GATEWAY, T6-PRO)
    # and plain uppercase+digit codes (TH1110D, SMK100).
    return re.findall(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+|[A-Z]{2,}\d+[A-Z0-9]*", question)


def graph_retrieve(graph_store: GraphStore, question: str, depth: int = 1) -> List[Tuple[str, str, str]]:
    entities = extract_candidate_entities(question)
    context = []

    for entity in entities:
        if graph_store.has_node(entity):
            context.extend(graph_store.neighbors_multi_hop(entity, depth=depth))

    return context
