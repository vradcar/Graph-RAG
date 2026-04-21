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

        rich_graph = extract_from_pdf(input_path, replacements_path)
        graph_items = graph_items_to_legacy_format(rich_graph)

        # Optionally save the rich Week 2 format alongside the legacy output.
        if args.rich_output:
            rich_path = Path(args.rich_output)
            rich_path.parent.mkdir(parents=True, exist_ok=True)
            with rich_path.open("w", encoding="utf-8") as f:
                json.dump(rich_graph, f, indent=2)
            print(f"Saved rich graph to {rich_path}")

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

    print(
        f"Saved graph items to {output_path} "
        f"({len(graph_items['nodes'])} nodes, {len(graph_items['edges'])} edges)"
    )


if __name__ == "__main__":
    main()
