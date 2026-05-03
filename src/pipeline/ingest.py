"""
Ingestion entry point.

Auto-detects the input type based on file extension:
  - *.pdf  → Week 2 path: pdfplumber-based rich extraction + legacy conversion
  - *.json → Week 1 path: legacy product records (unchanged)

Both paths produce the same legacy output shape:
    {"nodes": [{"node_id", "label", "kind", ...}],
     "edges": [{"source_id", "target_id", "relation", ...}]}

This means the existing GraphStore in src/graph/store.py loads either file
without modification. Week 2 adds richer properties (source_page, reasons,
conditions, etc.) as extra fields on the legacy-shaped nodes and edges.

Usage:
  # Week 1 (legacy):
  python -m src.pipeline.ingest --input data/raw/products_sample.json

  # Week 2 (PDF):
  python -m src.pipeline.ingest \
      --input data/raw/t9-thermostat.pdf \
      --replacements data/raw/replacements.json
"""

import argparse
import json
import logging
import os
from pathlib import Path

from src.graph.extract import (
    extract_from_pdf,
    graph_items_to_legacy_format,
    load_product_records,
    product_records_to_graph_items,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest source data into graph-ready JSON")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to source file (.pdf for Week 2 PDF extraction, .json for legacy records)",
    )
    parser.add_argument(
        "--replacements",
        default=None,
        help="Optional path to curated replacements JSON (PDF mode only)",
    )
    parser.add_argument(
        "--output",
        default="data/processed/graph_items.json",
        help="Path for processed graph items",
    )
    parser.add_argument(
        "--rich-output",
        default=None,
        help="Optional path to also write the Week 2 rich-format graph (PDF mode only)",
    )
    parser.add_argument(
        "--doc-id",
        default=None,
        help="Manifest doc-id key (PDF mode). Loads the entry's `pages` filter if set.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable INFO-level logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
    )

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    suffix = input_path.suffix.lower()

    if suffix == ".pdf":
        replacements_path = Path(args.replacements) if args.replacements else None
        if replacements_path and not replacements_path.exists():
            raise SystemExit(f"Replacements file not found: {replacements_path}")

        pages_filter = None
        if args.doc_id:
            from src.ingest.manifest import get_doc
            doc = get_doc(args.doc_id)
            pages_filter = tuple(doc["pages"]) if doc.get("pages") else None

        # Use the hardened LLM pipeline when --doc-id is provided and an API key is set.
        # Falls back to the legacy T9-specific pdfplumber extractors otherwise.
        use_llm = bool(args.doc_id and (os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")))

        if use_llm:
            from src.ingest.pdf_parser import extract_page_content
            from src.ingest.entity_extractor import build_client, extract_from_page
            from src.ingest.normalizer import normalize_and_deduplicate, normalize_node_id

            provider = "groq" if os.getenv("GROQ_API_KEY") else "openai"
            model = os.getenv(
                "LLM_MODEL",
                "llama-3.1-70b-versatile" if provider == "groq" else "gpt-4o-mini",
            )
            client = build_client(provider)
            raw_pages = extract_page_content(str(input_path), pages=pages_filter)
            all_nodes: list = []
            all_edges: list = []
            for page in raw_pages:
                result = extract_from_page(client, model, page, doc_id=args.doc_id)
                all_nodes.extend(n.model_dump() for n in result.nodes)
                all_edges.extend(e.model_dump() for e in result.edges)
            norm_nodes = normalize_and_deduplicate(all_nodes)
            seen: set = set()
            norm_edges: list = []
            for e in all_edges:
                src = normalize_node_id(e["source_id"])
                tgt = normalize_node_id(e["target_id"])
                key = (src, tgt, e["relation"])
                if key not in seen:
                    seen.add(key)
                    norm_edges.append({**e, "source_id": src, "target_id": tgt})
            graph_items = {"nodes": norm_nodes, "edges": norm_edges}
            log.info(
                "LLM path: %d nodes, %d edges extracted from %s (doc_id=%s)",
                len(norm_nodes), len(norm_edges), input_path.name, args.doc_id,
            )
        else:
            rich_graph = extract_from_pdf(input_path, replacements_path, pages=pages_filter)
            graph_items = graph_items_to_legacy_format(rich_graph)

        # Optionally save the rich Week 2 format alongside the legacy output.
        if args.rich_output:
            rich_path = Path(args.rich_output)
            rich_path.parent.mkdir(parents=True, exist_ok=True)
            with rich_path.open("w", encoding="utf-8") as f:
                json.dump(rich_graph, f, indent=2)
            print(f"Saved rich graph to {rich_path}")

        # Replacements manifest → Neo4j as REPLACES edges (INGEST-04).
        # Runs only when --replacements is provided and Neo4j is reachable.
        if args.replacements:
            replacements_path_r = Path(args.replacements)
            if replacements_path_r.exists():
                try:
                    import os
                    from neo4j import GraphDatabase
                    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
                    user_n = os.getenv("NEO4J_USER", "neo4j")
                    pwd = os.getenv("NEO4J_PASSWORD", "neo4j")
                    from src.graph.extract import ingest_replacements
                    with GraphDatabase.driver(uri, auth=(user_n, pwd)) as driver:
                        counts = ingest_replacements(replacements_path_r, driver)
                    print(f"Ingested replacements: {counts}")
                except Exception as exc:
                    # Do not fail the pipeline if Neo4j is unreachable — replacements
                    # ingest is best-effort relative to the JSON output above.
                    print(f"WARN: replacements Neo4j ingest skipped: {exc}")

    elif suffix == ".json":
        records = load_product_records(str(input_path))
        graph_items = product_records_to_graph_items(records)

    else:
        raise SystemExit(
            f"Unsupported input type: {suffix}. Expected .pdf or .json."
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(graph_items, file, indent=2)

    print(f"Saved graph items to {output_path} (doc_id={args.doc_id or '<none>'}, "
          f"{len(graph_items['nodes'])} nodes, {len(graph_items['edges'])} edges)")


if __name__ == "__main__":
    main()
