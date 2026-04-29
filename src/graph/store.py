from collections import deque
from typing import Dict, List, Tuple

import networkx as nx
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

# Import VALID_KINDS for constraint creation loop
# Note: plan 01 adds VALID_KINDS to schema.py. If plan 01 ran first, this import works.
# If running this plan standalone (before plan 01), VALID_KINDS falls back to the inline set.
try:
    from src.graph.schema import VALID_KINDS
except ImportError:
    VALID_KINDS = {"Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec"}


class Neo4jGraphStore:
    """Neo4j-backed graph store. All writes use MERGE keyed on node_id."""

    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        try:
            self._driver.verify_connectivity()
        except ServiceUnavailable as e:
            raise RuntimeError(
                f"Neo4j not reachable at {uri}. "
                "Start with: docker run -p 7474:7474 -p 7687:7687 "
                "-e NEO4J_AUTH=neo4j/password neo4j:5"
            ) from e
        self._id_keys = self._load_id_keys()

    def _load_id_keys(self) -> List[str]:
        with self._driver.session() as session:
            keys = session.run(
                "CALL db.propertyKeys() YIELD propertyKey RETURN collect(propertyKey) AS keys"
            ).single()
        if not keys:
            return []
        present = set(keys["keys"] or [])
        return [k for k in ("node_id", "id") if k in present]

    def _where_id_clause(self, alias: str, param_name: str) -> str:
        if not self._id_keys:
            return "false"
        return " OR ".join([f"{alias}.{k} = ${param_name}" for k in self._id_keys])

    def _return_id_expr(self, alias: str) -> str:
        if not self._id_keys:
            return "null"
        if len(self._id_keys) == 1:
            return f"{alias}.{self._id_keys[0]}"
        return f"coalesce({alias}.node_id, {alias}.id)"

    def setup_constraints(self) -> None:
        """Create uniqueness constraints on node_id per label. Idempotent via IF NOT EXISTS."""
        with self._driver.session() as session:
            for label in VALID_KINDS:
                session.run(
                    f"CREATE CONSTRAINT {label.lower()}_node_id IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.node_id IS UNIQUE"
                )

    def upsert_node(self, node_id: str, kind: str, **attributes) -> None:
        """MERGE a node by node_id. kind must be a valid label (validated by EntityNode)."""
        props = {k: v for k, v in attributes.items() if k not in ("node_id", "kind")}

        def _tx(tx):
            # kind appears in f-string (validated Literal); node_id always parameterized
            tx.run(
                f"MERGE (n:{kind} {{node_id: $node_id}}) SET n += $props",
                node_id=node_id,
                props=props,
            )

        with self._driver.session() as session:
            session.execute_write(_tx)

    def upsert_edge(self, source_id: str, target_id: str, relation: str, **attributes) -> bool:
        """MERGE an edge between two nodes by node_id. relation must be a valid type.

        Returns:
            True if the edge was created/matched, False if source or target node was missing.
        """
        props = {k: v for k, v in attributes.items() if k not in ("source_id", "target_id", "relation")}

        def _tx(tx):
            result = tx.run(
                f"MATCH (a {{{self._id_keys[0] if self._id_keys else 'id'}: $src}}), "
                f"(b {{{self._id_keys[0] if self._id_keys else 'id'}: $tgt}}) "
                f"MERGE (a)-[r:{relation}]->(b) SET r += $props "
                f"RETURN {self._return_id_expr('a')} AS src",
                src=source_id,
                tgt=target_id,
                props=props,
            )
            return result.single() is not None

        with self._driver.session() as session:
            return session.execute_write(_tx)

    def neighbors_multi_hop(self, start_node: str, depth: int = 1) -> List[Tuple[str, str, str]]:
        """Return (source_id, relation, target_id) tuples within `depth` hops."""

        if not self._id_keys:
            return []

        def _tx(tx):
            result = tx.run(
                f"MATCH (start) WHERE {self._where_id_clause('start', 'start_node')} "
                f"MATCH path = (start)-[*1..{int(depth)}]-(neighbor) "
                "UNWIND relationships(path) AS rel "
                f"RETURN {self._return_id_expr('startNode(rel)')} AS src, "
                "type(rel) AS rel_type, "
                f"{self._return_id_expr('endNode(rel)')} AS tgt",
                start_node=start_node,
            )
            return [(r["src"], r["rel_type"], r["tgt"]) for r in result]

        with self._driver.session() as session:
            return session.execute_read(_tx)

    def node_payload(self, node_id: str) -> Dict:
        """Return all properties of the node with the given node_id, or {}."""

        if not self._id_keys:
            return {}

        def _tx(tx):
            result = tx.run(
                f"MATCH (n) WHERE {self._where_id_clause('n', 'node_id')} "
                "RETURN properties(n) AS props LIMIT 1",
                node_id=node_id,
            )
            record = result.single()
            return dict(record["props"]) if record else {}

        with self._driver.session() as session:
            return session.execute_read(_tx)

    def has_node(self, node_id: str) -> bool:
        """Return True if a node with the given node_id exists."""

        if not self._id_keys:
            return False

        def _tx(tx):
            result = tx.run(
                f"MATCH (n) WHERE {self._where_id_clause('n', 'node_id')} "
                "RETURN count(n) AS cnt",
                node_id=node_id,
            )
            return result.single()["cnt"] > 0

        with self._driver.session() as session:
            return session.execute_read(_tx)

    def run_cypher(self, query: str, **params) -> List[Dict]:
        """Execute a read-only Cypher query and return results as a list of dicts."""
        with self._driver.session() as session:
            result = session.run(query, **params)
            return [record.data() for record in result]

    def close(self) -> None:
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ---------------------------------------------------------------------------
# Original networkx-backed store — kept for unit tests that run without Neo4j
# ---------------------------------------------------------------------------

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
