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
from src.ingest.normalizer import normalize_and_deduplicate
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
    print("Extracting entities with Groq LLM...")
    try:
        client = build_client()
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
        for edge in all_edges:
            store.upsert_edge(
                source_id=edge["source_id"],
                target_id=edge["target_id"],
                relation=edge["relation"],
            )
            edges_written += 1

        print(f"  Written: {nodes_written} nodes, {edges_written} edges")

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
