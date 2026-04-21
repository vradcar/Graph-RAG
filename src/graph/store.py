from collections import deque
from typing import Dict, List, Tuple
import networkx as nx


class GraphStore:
    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def upsert_node(self, node_id: str, **attributes) -> None:
        self.graph.add_node(node_id, **attributes)

    def upsert_edge(self, source_id: str, target_id: str, relation: str, **attributes) -> None:
        self.graph.add_edge(source_id, target_id, key=relation, relation=relation, **attributes)

    def neighbors_multi_hop(self, start_node: str, depth: int = 1) -> List[Tuple[str, str, str]]:
        if start_node not in self.graph:
            return []

        visited = {start_node}
        queue = deque([(start_node, 0)])
        paths = []

        seen_edges = set()

        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue

            for _, target, edge_data in self.graph.out_edges(current, data=True):
                relation = edge_data.get("relation", "RELATED_TO")
                edge_key = (current, relation, target)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    paths.append(edge_key)
                if target not in visited:
                    visited.add(target)
                    queue.append((target, current_depth + 1))

            for source, _, edge_data in self.graph.in_edges(current, data=True):
                relation = edge_data.get("relation", "RELATED_TO")
                edge_key = (source, relation, current)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    paths.append(edge_key)
                if source not in visited:
                    visited.add(source)
                    queue.append((source, current_depth + 1))

        return paths

    def node_payload(self, node_id: str) -> Dict:
        return self.graph.nodes.get(node_id, {})

    def has_node(self, node_id: str) -> bool:
        return node_id in self.graph
