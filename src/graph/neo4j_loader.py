"""
Neo4j loader — provenance-aware (Phase 1 Plan 02).

Reads the graph items JSON produced by ``src/pipeline/ingest.py`` and writes
the nodes and edges into a running Neo4j instance.

Idempotent: every node is MERGEd by ``node_id``; every edge is MERGEd by
``(source_id, target_id, relation, source_doc)`` so the same fact extracted
from two PDFs creates two parallel evidence edges rather than overwriting one.

Connection details come from the .env file:
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=...

Usage:
    # Load a specific file with a doc-id slug (required)
    python -m src.graph.neo4j_loader --doc-id t9_install_guide --input data/processed/graph_items.json

    # Wipe the database first (use carefully)
    python -m src.graph.neo4j_loader --reset --doc-id t9_install_guide --input data/processed/graph_items.json

    # Quick verification: print node/edge counts after load
    python -m src.graph.neo4j_loader --doc-id t9_install_guide --verify

Audit query (should always return 0 after a clean ingest):
    MATCH ()-[r]->() WHERE type(r) <> 'MENTIONED_IN' AND r.source_doc IS NULL RETURN count(r)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver

from src.graph.provenance import merge_document, merge_node_with_provenance, merge_edge_with_provenance
from src.graph.schema import VALID_KINDS, VALID_RELATIONS
from src.graph.utils import clean_props as _clean_props

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
    Ensure each node label has a unique node_id constraint.
    Constraints make MERGE fast (constraint = index) and prevent duplicates.
    Includes :Document uniqueness on doc_id (SCHEMA-01).
    """
    labels = [
        "Thermostat", "HVACSystemType", "WiringTerminal", "RoomSensor",
        "Adapter", "ElectricalSpec", "OperatingRange", "ZoningPanel",
        "Wallplate", "Product", "Accessory", "WiringConfig", "Spec",
        # "Document" removed — Document uniqueness is on doc_id, not node_id (see below)
    ]
    with driver.session() as sess:
        for label in labels:
            cypher = (
                f"CREATE CONSTRAINT constraint_{label.lower()}_node_id "
                f"IF NOT EXISTS FOR (n:{label}) REQUIRE n.node_id IS UNIQUE"
            )
            sess.run(cypher)
        # Unique constraint on Document.doc_id (separate key for document identity)
        sess.run(
            "CREATE CONSTRAINT constraint_document_doc_id "
            "IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE"
        )
    log.info("Created/verified unique-id constraints on %d labels + Document.doc_id", len(labels))




def upsert_document(driver: Driver, doc_metadata: Dict[str, Any]) -> None:
    """Upsert the :Document node for this ingest run.

    Must be called BEFORE load_nodes() so that MENTIONED_IN MATCH finds the
    :Document node (D-07 / Pitfall 5 in RESEARCH.md).
    """
    with driver.session() as sess:
        sess.execute_write(lambda tx: merge_document(tx, doc_metadata))
    log.info("Upserted :Document {doc_id: %s}", doc_metadata.get("doc_id"))


def load_nodes(driver: Driver, nodes: List[Dict[str, Any]], doc_id: str) -> int:
    """
    Load nodes via provenance-aware helper. Each node's ``kind`` becomes the
    Neo4j label; ``node_id`` is the MERGE key.

    ``doc_id`` is REQUIRED — passed to merge_node_with_provenance so every
    node accumulates source_docs[] and gets a MENTIONED_IN edge (D-06).
    """
    loaded = 0
    for n in nodes:
        node_id = n.get("node_id") or n.get("id")
        kind = n.get("kind") or n.get("type") or "Entity"
        if not node_id:
            log.warning("Skipping node with no id: %s", n)
            continue

        # Validate kind; warn but don't crash on unknown kinds (Phase 2 tightens this).
        if kind not in VALID_KINDS:
            log.warning("Unknown node kind '%s' for node %s — loading anyway", kind, node_id)

        # Build a normalised node dict for the provenance helper.
        structural = {"node_id", "id", "kind", "type"}
        extra_props = _clean_props({k: v for k, v in n.items() if k not in structural})
        node_dict = {
            "node_id": node_id,
            "label": n.get("label", node_id),
            "kind": kind,
            "properties": extra_props,
        }

        with driver.session() as sess:
            sess.execute_write(
                lambda tx, nd=node_dict: merge_node_with_provenance(tx, nd, doc_id)
            )
        loaded += 1

    log.info("Loaded %d nodes", loaded)
    return loaded


def load_edges(driver: Driver, edges: List[Dict[str, Any]], doc_id: str) -> int:
    """
    Load edges via provenance-aware helper. Relationship type comes from the
    ``relation`` field (or ``type``). ``source_doc`` is keyed inside the MERGE
    map so re-extracting the same fact from a different PDF creates a parallel
    evidence edge rather than overwriting (SCHEMA-04).

    ``doc_id`` is REQUIRED (D-06).
    """
    loaded = 0
    skipped = 0
    for e in edges:
        source_id = e.get("source_id") or e.get("source")
        target_id = e.get("target_id") or e.get("target")
        relation = e.get("relation") or e.get("type")
        if not all([source_id, target_id, relation]):
            log.warning("Skipping edge with missing fields: %s", e)
            skipped += 1
            continue

        # Validate relation; warn but don't crash on unknown types (Phase 2 tightens).
        if relation not in VALID_RELATIONS:
            log.warning("Unknown relation '%s' — loading anyway", relation)

        structural = {"source_id", "source", "target_id", "target", "relation", "type"}
        extra_props = _clean_props({k: v for k, v in e.items() if k not in structural})
        edge_dict = {
            "source_id": source_id,
            "target_id": target_id,
            "relation": relation,
            "properties": extra_props,
        }

        with driver.session() as sess:
            sess.execute_write(
                lambda tx, ed=edge_dict: merge_edge_with_provenance(tx, ed, doc_id)
            )
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

        # Audit: no business edge should have source_doc IS NULL
        null_edges = sess.run(
            "MATCH ()-[r]->() WHERE type(r) <> 'MENTIONED_IN' AND r.source_doc IS NULL "
            "RETURN count(r) AS c"
        ).single()["c"]

    print()
    print("=== Database stats ===")
    print(f"Total nodes: {node_count}")
    print(f"Total edges: {edge_count}")
    print(f"Edges with source_doc IS NULL (should be 0): {null_edges}")
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
    parser = argparse.ArgumentParser(description="Load graph items JSON into Neo4j (provenance-aware)")
    parser.add_argument(
        "--doc-id",
        required=True,
        help="Manifest slug identifying the source PDF (e.g., 't9_install_guide'). "
             "Required — determines source_doc on every written edge and accumulates "
             "source_docs[] on every written node.",
    )
    parser.add_argument(
        "--doc-title",
        default=None,
        help="Human-readable title for the :Document node. Defaults to --doc-id if omitted.",
    )
    parser.add_argument(
        "--doc-sku",
        default=None,
        help="Product SKU associated with this document (optional).",
    )
    parser.add_argument(
        "--doc-source-url",
        default=None,
        help="Source URL for the document (optional).",
    )
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

    driver = get_driver()
    try:
        if args.reset:
            reset_database(driver)
        create_constraints(driver)

        if not args.verify or input_path.exists():
            # Load data — only require the file when we're actually going to load.
            if not input_path.exists():
                raise SystemExit(f"Input not found: {input_path}")

            with input_path.open() as f:
                graph = json.load(f)

            nodes = graph.get("nodes", [])
            edges = graph.get("edges", [])
            log.info("Loaded %s — %d nodes, %d edges", input_path, len(nodes), len(edges))

            doc_metadata = {
                "doc_id": args.doc_id,
                "title": args.doc_title or args.doc_id,
                "sku": args.doc_sku,
                "source_url": args.doc_source_url,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }

            # D-07: Document upsert MUST run in its own committed transaction BEFORE entity loop.
            upsert_document(driver, doc_metadata)
            load_nodes(driver, nodes, args.doc_id)
            load_edges(driver, edges, args.doc_id)
            print(f"\nLoad complete. Open http://localhost:7474 to inspect the graph.")

        if args.verify:
            verify(driver)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
