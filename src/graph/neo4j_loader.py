"""
Neo4j loader — Week 2 (Member 2's piece).

Reads the graph items JSON produced by `src/pipeline/ingest.py` and writes
the nodes and edges into a running Neo4j instance.

Idempotent: uses MERGE on every node and edge keyed by id, so re-running
the loader does not duplicate anything.

Connection details come from the .env file:
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=...

Usage:
    # Default: load the standard graph_items.json
    python -m src.graph.neo4j_loader

    # Load a specific file
    python -m src.graph.neo4j_loader --input data/processed/graph_items.json

    # Wipe the database first (use carefully)
    python -m src.graph.neo4j_loader --reset

    # Quick verification: print node/edge counts after load
    python -m src.graph.neo4j_loader --verify
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("neo4j_loader")


def get_driver() -> Driver:
    """Build a Neo4j driver from .env credentials."""
    load_dotenv()
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        raise SystemExit("NEO4J_PASSWORD not set in .env")
    return GraphDatabase.driver(uri, auth=(user, password))


def reset_database(driver: Driver) -> None:
    """Delete all nodes and relationships. Destructive — confirm before calling."""
    log.warning("Wiping all nodes and relationships from the database...")
    with driver.session() as sess:
        sess.run("MATCH (n) DETACH DELETE n")
    log.info("Database wiped clean")


def create_constraints(driver: Driver) -> None:
    """
    Ensure each node label has a unique-id constraint.
    Constraints make MERGE fast (constraint = index) and prevent duplicates.
    """
    labels = [
        "Thermostat", "HVACSystemType", "WiringTerminal", "RoomSensor",
        "Adapter", "ElectricalSpec", "OperatingRange", "ZoningPanel",
        "Wallplate", "Product", "Accessory",
    ]
    with driver.session() as sess:
        for label in labels:
            cypher = (
                f"CREATE CONSTRAINT constraint_{label.lower()}_id "
                f"IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
            )
            sess.run(cypher)
    log.info("Created/verified unique-id constraints on %d labels", len(labels))


def _clean_props(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Neo4j properties cannot be nested dicts or None. Lists of primitives are
    fine. Convert anything Neo4j won't accept into a JSON string so the data
    survives the round trip.
    """
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) for x in v):
            out[k] = v
        else:
            out[k] = json.dumps(v)
    return out


def load_nodes(driver: Driver, nodes: List[Dict[str, Any]]) -> int:
    """
    Load nodes using MERGE on `id`. Each node's `kind` becomes the Neo4j label.

    The legacy JSON shape (Week 1) uses `node_id` and `kind`. This loader
    supports that shape directly so the same JSON works for everything.
    """
    loaded = 0
    with driver.session() as sess:
        for n in nodes:
            node_id = n.get("node_id") or n.get("id")
            label = n.get("kind") or n.get("type") or "Entity"
            if not node_id:
                log.warning("Skipping node with no id: %s", n)
                continue

            # Build the property map: drop the structural fields, keep the rest.
            structural = {"node_id", "id", "kind", "type"}
            props = _clean_props({k: v for k, v in n.items() if k not in structural})
            props["id"] = node_id

            # Sanitise label — Neo4j labels can't have spaces or special chars.
            safe_label = "".join(ch for ch in label if ch.isalnum()) or "Entity"

            cypher = f"MERGE (n:{safe_label} {{id: $id}}) SET n += $props"
            sess.run(cypher, id=node_id, props=props)
            loaded += 1
    log.info("Loaded %d nodes", loaded)
    return loaded


def load_edges(driver: Driver, edges: List[Dict[str, Any]]) -> int:
    """
    Load edges using MERGE on (source, type, target). Relationship type comes
    from the `relation` field (legacy) or `type` field (rich).
    """
    loaded = 0
    skipped = 0
    with driver.session() as sess:
        for e in edges:
            source_id = e.get("source_id") or e.get("source")
            target_id = e.get("target_id") or e.get("target")
            relation = e.get("relation") or e.get("type")
            if not all([source_id, target_id, relation]):
                log.warning("Skipping edge with missing fields: %s", e)
                skipped += 1
                continue

            structural = {"source_id", "source", "target_id", "target", "relation", "type"}
            props = _clean_props({k: v for k, v in e.items() if k not in structural})

            # Sanitise relationship type — Neo4j requires uppercase, no spaces.
            safe_rel = "".join(ch if ch.isalnum() else "_" for ch in relation).upper()

            # Two separate MATCH clauses (rather than comma-separated) avoids
            # Neo4j's cartesian-product warning. Each MATCH uses the unique
            # `id` index from the constraint we created earlier.
            cypher = (
                "MATCH (a {id: $source_id}) "
                "MATCH (b {id: $target_id}) "
                f"MERGE (a)-[r:{safe_rel}]->(b) "
                "SET r += $props"
            )
            result = sess.run(
                cypher, source_id=source_id, target_id=target_id, props=props
            )
            summary = result.consume()
            if summary.counters.relationships_created == 0 and summary.counters.properties_set == 0:
                # Both source and target need to exist for MATCH to find them.
                # If either is missing, MERGE silently does nothing.
                check = sess.run(
                    "MATCH (a {id: $sid}) MATCH (b {id: $tid}) RETURN count(a) + count(b) as n",
                    sid=source_id, tid=target_id,
                ).single()
                if check is None or check["n"] < 2:
                    log.warning("Edge skipped (missing endpoint): %s -[%s]-> %s",
                                source_id, safe_rel, target_id)
                    skipped += 1
                    continue
            loaded += 1
    log.info("Loaded %d edges (%d skipped)", loaded, skipped)
    return loaded


def verify(driver: Driver) -> None:
    """Print quick database stats so you can confirm the load worked."""
    with driver.session() as sess:
        node_count = sess.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        edge_count = sess.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]

        labels = sess.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c ORDER BY c DESC"
        ).data()
        rel_types = sess.run(
            "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS c ORDER BY c DESC"
        ).data()

    print()
    print(f"=== Database stats ===")
    print(f"Total nodes: {node_count}")
    print(f"Total edges: {edge_count}")
    print()
    print("Nodes by label:")
    for row in labels:
        print(f"  {row['label']:20s} {row['c']}")
    print()
    print("Edges by type:")
    for row in rel_types:
        print(f"  {row['rel']:30s} {row['c']}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load graph items JSON into Neo4j")
    parser.add_argument(
        "--input",
        default="data/processed/graph_items.json",
        help="Path to graph items JSON",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe the database before loading (destructive)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Print node/edge counts after loading",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    with input_path.open() as f:
        graph = json.load(f)

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    log.info("Loaded %s — %d nodes, %d edges", input_path, len(nodes), len(edges))

    driver = get_driver()
    try:
        if args.reset:
            reset_database(driver)
        create_constraints(driver)
        load_nodes(driver, nodes)
        load_edges(driver, edges)
        if args.verify:
            verify(driver)
    finally:
        driver.close()

    print(f"\nLoad complete. Open http://localhost:7474 to inspect the graph.")


if __name__ == "__main__":
    main()
