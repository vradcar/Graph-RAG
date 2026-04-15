"""
Ingest CLI: PDF → Neo4j knowledge graph.

Pipeline order (must not be reordered):
  1. load_dotenv() — before any os.getenv() calls
  2. setup_constraints() — before any MERGE writes
  3. extract_page_content() — parse PDF
  4. extract_from_page() — LLM entity extraction per page
  5. normalize_and_deduplicate() — canonical ids, remove dups
  6. upsert_node() / upsert_edge() — MERGE into Neo4j

Usage:
    python -m src.pipeline.ingest --input data/raw/t9-thermostat.pdf
    python -m src.pipeline.ingest --input data/raw/t9-thermostat.pdf --dry-run
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # MUST be first — loads .env before any os.getenv() calls

from src.common.config import load_settings
from src.graph.store import Neo4jGraphStore
from src.ingest.entity_extractor import build_client, extract_from_page
from src.ingest.normalizer import normalize_and_deduplicate, normalize_node_id
from src.ingest.pdf_parser import extract_page_content


def run_ingest(pdf_path: str, dry_run: bool = False) -> dict:
    """
    Core ingest logic. Separated from main() for testability.

    Returns:
        dict with keys: pages_processed, nodes_written, edges_written, node_counts
    """
    settings = load_settings()
    neo4j_uri = settings["graph"]["neo4j_uri"]
    neo4j_user = settings["graph"]["neo4j_user"]
    neo4j_password = os.getenv("NEO4J_PASSWORD", settings["graph"]["neo4j_password"])
    model = settings["llm"]["model"]

    # Step 1: Parse PDF
    print(f"Parsing PDF: {pdf_path}")
    pages = extract_page_content(pdf_path)
    print(f"  → {len(pages)} pages extracted")

    # Step 2: LLM extraction
    provider = settings["llm"].get("provider", "groq")
    print(f"Extracting entities with {provider} LLM (model: {model})...")
    try:
        client = build_client(provider=provider)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    all_nodes: list[dict] = []
    all_edges: list[dict] = []

    for page in pages:
        result = extract_from_page(client, model, page)
        all_nodes.extend([n.model_dump() for n in result.nodes])
        all_edges.extend([e.model_dump() for e in result.edges])
        if result.nodes or result.edges:
            print(
                f"  Page {page['page_num']}: "
                f"{len(result.nodes)} nodes, {len(result.edges)} edges"
            )

    # Step 3: Normalize and deduplicate
    nodes = normalize_and_deduplicate(all_nodes)
    # Normalize edge source/target IDs to match normalized node IDs
    for edge in all_edges:
        edge["source_id"] = normalize_node_id(edge["source_id"])
        edge["target_id"] = normalize_node_id(edge["target_id"])
    # Filter edges: source must be a Product node (drop LLM hallucinations like Accessory→Accessory)
    node_kinds = {n["node_id"]: n["kind"] for n in nodes}
    valid_edges = []
    for edge in all_edges:
        src_kind = node_kinds.get(edge["source_id"])
        if src_kind == "Product":
            valid_edges.append(edge)
        else:
            print(f"  Dropped invalid edge: {edge['source_id']} ({src_kind}) -[{edge['relation']}]-> {edge['target_id']}")
    all_edges = valid_edges
    print(f"After deduplication: {len(nodes)} unique nodes, {len(all_edges)} edges")

    if dry_run:
        print("[DRY RUN] Skipping Neo4j writes.")
        return {
            "pages_processed": len(pages),
            "nodes_written": 0,
            "edges_written": 0,
            "node_counts": {},
        }

    # Step 4: Write to Neo4j
    print(f"Connecting to Neo4j at {neo4j_uri}...")
    with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as store:
        # Constraints MUST be created before first MERGE
        store.setup_constraints()
        print("  Constraints created/verified.")

        nodes_written = 0
        for node in nodes:
            store.upsert_node(
                node_id=node["node_id"],
                kind=node["kind"],
                label=node["label"],
                **node.get("properties", {}),
            )
            nodes_written += 1

        edges_written = 0
        edges_skipped = 0
        for edge in all_edges:
            created = store.upsert_edge(
                source_id=edge["source_id"],
                target_id=edge["target_id"],
                relation=edge["relation"],
            )
            if created:
                edges_written += 1
            else:
                edges_skipped += 1
                print(
                    f"  WARNING: Edge skipped — {edge['source_id']} -[{edge['relation']}]-> {edge['target_id']} "
                    f"(source or target node_id not found)"
                )

        print(f"  Written: {nodes_written} nodes, {edges_written} edges"
              + (f" ({edges_skipped} skipped — missing nodes)" if edges_skipped else ""))

        # Step 5: Link orphaned nodes to the primary product
        # Nodes extracted on different pages often lack edges back to the product.
        # Auto-generate edges based on node kind:
        #   Spec → HAS_SPEC, WiringConfig → SUPPORTS_WIRING,
        #   HVACSystemType/Accessory → COMPATIBLE_WITH
        node_ids_with_incoming = set()
        for edge in all_edges:
            node_ids_with_incoming.add(edge["target_id"])
        for edge in all_edges:
            node_ids_with_incoming.add(edge["source_id"])

        # Find the primary product (most connected, or first Product node)
        product_nodes = [n for n in nodes if n["kind"] == "Product"]
        if product_nodes:
            primary_product = product_nodes[0]["node_id"]

            kind_to_relation = {
                "Spec": "HAS_SPEC",
                "WiringConfig": "SUPPORTS_WIRING",
                "HVACSystemType": "COMPATIBLE_WITH",
                "Accessory": "COMPATIBLE_WITH",
            }

            inferred = 0
            for node in nodes:
                if node["node_id"] == primary_product:
                    continue
                if node["kind"] == "Product":
                    continue
                relation = kind_to_relation.get(node["kind"])
                if not relation:
                    continue
                # Check if this node already has any edge connecting it
                if node["node_id"] in node_ids_with_incoming:
                    continue
                created = store.upsert_edge(
                    source_id=primary_product,
                    target_id=node["node_id"],
                    relation=relation,
                )
                if created:
                    inferred += 1
                    edges_written += 1

            if inferred:
                print(f"  Inferred: {inferred} edges linking orphaned nodes to {primary_product}")

        # Post-ingest validation: check for REPLACES edges with missing targets
        with store._driver.session() as session:
            result = session.run(
                "MATCH (p:Product)-[:REPLACES]->(q) "
                "WHERE NOT (q:Product) RETURN q.node_id AS missing_id"
            )
            dangling = [r["missing_id"] for r in result]
            if dangling:
                print(
                    f"WARNING: {len(dangling)} REPLACES targets are not Product nodes: {dangling}",
                    file=sys.stderr,
                )

        # Count nodes by label for summary
        with store._driver.session() as session:
            result = session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS cnt"
            )
            node_counts = {r["label"]: r["cnt"] for r in result}

    print("Node counts in Neo4j:")
    for label, cnt in node_counts.items():
        print(f"  {label}: {cnt}")

    return {
        "pages_processed": len(pages),
        "nodes_written": nodes_written,
        "edges_written": edges_written,
        "node_counts": node_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest T9 thermostat PDF into Neo4j knowledge graph"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the PDF file (e.g., data/raw/t9-thermostat.pdf)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and extract without writing to Neo4j",
    )
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    run_ingest(args.input, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
