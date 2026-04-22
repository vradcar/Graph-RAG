"""
Cypher-based graph query module — Week 2 (Member 2's piece).

Provides multi-hop traversal against a loaded Neo4j graph with a configurable
depth parameter. Supports the Week 2 deliverable: single-hop (depth=1) vs
multi-hop (depth=2+) comparison on the same query.

Usage as a library:
    from src.graph.neo4j_query import Neo4jQueryEngine

    with Neo4jQueryEngine() as engine:
        result = engine.traverse_from(
            entity_id="t9_rcht9610wf",
            depth=2,
            relation_filter=None,  # or e.g. ["REPLACED_BY"] to follow only certain edges
        )
        print(result["paths"])

Usage from the command line:
    # 1-hop traversal from the T9 thermostat
    python -m src.graph.neo4j_query --entity t9_rcht9610wf --depth 1

    # 2-hop traversal
    python -m src.graph.neo4j_query --entity t9_rcht9610wf --depth 2

    # Filter to only follow REPLACED_BY edges
    python -m src.graph.neo4j_query --entity rth6580wf_legacy --depth 1 \\
        --relations REPLACED_BY

Depth semantics:
    depth=1 → only direct neighbors of the start entity
    depth=2 → neighbors plus their neighbors (T9 → Adapter → ZoningPanel)
    depth=N → up to N hops out
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("neo4j_query")


# -------------------------------------------------------------------------
# Result types
# -------------------------------------------------------------------------

@dataclass
class TraversalPath:
    """A single path through the graph: [(source_id, relation, target_id), ...]."""
    hops: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def length(self) -> int:
        return len(self.hops)

    def render(self) -> str:
        """Pretty-print the path as `A -[REL]-> B -[REL]-> C`."""
        if not self.hops:
            return "(empty path)"
        parts = [self.hops[0]["source"]]
        for hop in self.hops:
            parts.append(f"-[{hop['relation']}]->")
            parts.append(hop["target"])
        return " ".join(parts)


# -------------------------------------------------------------------------
# Engine
# -------------------------------------------------------------------------

class Neo4jQueryEngine:
    """Wraps a Neo4j driver and exposes traversal queries used by GraphRAG."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        load_dotenv()
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD")
        if not self.password:
            raise SystemExit("NEO4J_PASSWORD not set in .env")
        self._driver: Optional[Driver] = None

    # Context manager — `with Neo4jQueryEngine() as engine: ...`
    def __enter__(self):
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._driver:
            self._driver.close()
            self._driver = None

    @property
    def driver(self) -> Driver:
        if self._driver is None:
            raise RuntimeError("Driver not initialised. Use as a context manager.")
        return self._driver

    # ---------------------------------------------------------------------
    # Single-hop and multi-hop traversal
    # ---------------------------------------------------------------------

    def traverse_from(
        self,
        entity_id: str,
        depth: int = 1,
        relation_filter: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Walk outward from entity_id up to `depth` hops and return all paths.

        Args:
            entity_id: Starting node's `id` property (e.g. "t9_rcht9610wf").
            depth: Maximum hop count. depth=1 = direct neighbors only.
            relation_filter: If provided, only follow edges of these types.

        Returns:
            {
              "start": <start node properties>,
              "depth": <int>,
              "paths": [TraversalPath, ...],
              "node_count": <unique nodes reached>,
              "hop_count": <total relationships traversed>,
            }
        """
        if depth < 1:
            raise ValueError("depth must be at least 1")

        # Build the relationship pattern. Cypher syntax:
        #   -[*1..N]->          → any relationship type, up to N hops
        #   -[:REL1|REL2*1..N]-> → only specific relationship types
        if relation_filter:
            # Sanitise — relationship types can only be alphanumeric + underscore
            safe = [re_safe(r) for r in relation_filter]
            rel_clause = f"[:{('|'.join(safe))}*1..{depth}]"
        else:
            rel_clause = f"[*1..{depth}]"

        cypher = (
            f"MATCH (start {{id: $entity_id}}) "
            f"OPTIONAL MATCH path = (start)-{rel_clause}->(end) "
            f"RETURN start, path"
        )

        # Use .run() + iteration (not .data()) so the driver returns the
        # rich Path object instead of converting it to a plain list of dicts.
        with self.driver.session() as sess:
            result = sess.run(cypher, entity_id=entity_id)
            records = list(result)

        if not records:
            return {
                "start": None,
                "depth": depth,
                "paths": [],
                "node_count": 0,
                "hop_count": 0,
                "error": f"No node found with id={entity_id!r}",
            }

        # All records share the same `start` node; read it from the first row.
        start_node = dict(records[0]["start"])

        paths: List[TraversalPath] = []
        unique_nodes = {entity_id}
        total_hops = 0

        for record in records:
            path_obj = record.get("path")
            if path_obj is None:
                # Either start node has no outgoing edges, or none match the filter
                continue

            hops: List[Dict[str, Any]] = []
            for rel in path_obj.relationships:
                hop = {
                    "source": rel.start_node["id"],
                    "relation": rel.type,
                    "target": rel.end_node["id"],
                    "properties": dict(rel),
                    "target_props": dict(rel.end_node),
                    "target_label": list(rel.end_node.labels)[0] if rel.end_node.labels else None,
                }
                hops.append(hop)
                unique_nodes.add(hop["target"])
                total_hops += 1

            paths.append(TraversalPath(hops=hops))

        return {
            "start": start_node,
            "depth": depth,
            "paths": paths,
            "node_count": len(unique_nodes),
            "hop_count": total_hops,
        }

    # ---------------------------------------------------------------------
    # Convenience: get a single node's full payload
    # ---------------------------------------------------------------------

    def get_node(self, entity_id: str) -> Optional[Dict[str, Any]]:
        cypher = "MATCH (n {id: $entity_id}) RETURN n, labels(n) AS labels"
        with self.driver.session() as sess:
            row = sess.run(cypher, entity_id=entity_id).single()
        if row is None:
            return None
        return {
            "label": (row["labels"] or [None])[0],
            "properties": dict(row["n"]),
        }

    # ---------------------------------------------------------------------
    # Convenience: list all entity IDs (useful for the demo script)
    # ---------------------------------------------------------------------

    def list_entities(self, label: Optional[str] = None) -> List[Dict[str, str]]:
        if label:
            safe_label = re_safe(label)
            cypher = f"MATCH (n:{safe_label}) RETURN n.id AS id, labels(n)[0] AS label ORDER BY id"
        else:
            cypher = "MATCH (n) RETURN n.id AS id, labels(n)[0] AS label ORDER BY label, id"
        with self.driver.session() as sess:
            return sess.run(cypher).data()


def re_safe(s: str) -> str:
    """Sanitise a label or relationship type for inline Cypher injection."""
    return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in s)


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def _print_human(result: Dict[str, Any]) -> None:
    """Render the traversal result as a human-readable summary."""
    if result.get("error"):
        print(f"Error: {result['error']}")
        return

    start = result["start"]
    print()
    print(f"=== Traversal from {start.get('id')} (depth={result['depth']}) ===")
    print(f"Start node: {start.get('name', start.get('id'))}")
    print(f"Reached {result['node_count']} unique nodes via {result['hop_count']} relationship traversals")
    print(f"Total paths returned: {len(result['paths'])}")

    if not result["paths"]:
        print("\n(no outgoing paths from this node)")
        return

    # Group paths by length so single-hop vs multi-hop is easy to read.
    by_length: Dict[int, List[TraversalPath]] = {}
    for p in result["paths"]:
        by_length.setdefault(p.length, []).append(p)

    for length in sorted(by_length):
        print(f"\n--- {length}-hop paths ({len(by_length[length])}) ---")
        for p in by_length[length]:
            print(f"  {p.render()}")
            # If the final hop has interesting edge properties, surface them
            last = p.hops[-1]
            if last.get("properties"):
                interesting = {k: v for k, v in last["properties"].items() if v not in (None, "", [])}
                if interesting:
                    print(f"    edge props: {interesting}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cypher multi-hop traversal demo")
    parser.add_argument("--entity", required=True, help="Starting entity id (e.g. t9_rcht9610wf)")
    parser.add_argument("--depth", type=int, default=1, help="Max traversal depth (>=1)")
    parser.add_argument(
        "--relations",
        nargs="+",
        default=None,
        help="Optional list of relationship types to follow (e.g. --relations REPLACED_BY COMPATIBLE_WITH)",
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of human summary")
    args = parser.parse_args()

    with Neo4jQueryEngine() as engine:
        result = engine.traverse_from(
            entity_id=args.entity,
            depth=args.depth,
            relation_filter=args.relations,
        )

    if args.json:
        # TraversalPath is a dataclass; convert to dict for JSON
        json_safe = {
            **result,
            "paths": [{"length": p.length, "hops": p.hops} for p in result["paths"]],
        }
        print(json.dumps(json_safe, indent=2, default=str))
    else:
        _print_human(result)


if __name__ == "__main__":
    main()
