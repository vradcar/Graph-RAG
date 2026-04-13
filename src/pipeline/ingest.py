import argparse
import json
from pathlib import Path
from src.graph.extract import load_product_records, product_records_to_graph_items


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest sample records into graph-ready JSON")
    parser.add_argument("--input", required=True, help="Path to raw sample JSON file")
    parser.add_argument(
        "--output",
        default="data/processed/graph_items.json",
        help="Path for processed graph items",
    )
    args = parser.parse_args()

    records = load_product_records(args.input)
    graph_items = product_records_to_graph_items(records)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(graph_items, file, indent=2)

    print(f"Saved graph items to {output_path}")


if __name__ == "__main__":
    main()
