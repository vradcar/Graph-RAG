import json
from pathlib import Path
from typing import Dict, List


def load_product_records(path: str) -> List[Dict]:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def product_records_to_graph_items(records: List[Dict]) -> Dict[str, List[Dict]]:
    nodes = []
    edges = []

    for item in records:
        product_id = item["product_id"]
        nodes.append(
            {
                "node_id": product_id,
                "label": item.get("name", product_id),
                "kind": "Product",
                "status": item.get("status", "active"),
                "system_type": item.get("system_type", "unknown"),
            }
        )

        for accessory in item.get("compatible_accessories", []):
            nodes.append(
                {
                    "node_id": accessory,
                    "label": accessory,
                    "kind": "Accessory",
                }
            )
            edges.append(
                {
                    "source_id": product_id,
                    "target_id": accessory,
                    "relation": "COMPATIBLE_WITH",
                }
            )

        replacement = item.get("replacement_for")
        if replacement:
            edges.append(
                {
                    "source_id": product_id,
                    "target_id": replacement,
                    "relation": "REPLACES",
                }
            )

    return {"nodes": nodes, "edges": edges}
