"""
Entity normalization and deduplication before Neo4j write.

Converts LLM-extracted node_ids and labels to canonical forms to prevent
graph fragmentation (e.g., "24VAC" vs "24 VAC" becoming two Spec nodes).
"""

# Known label aliases → canonical form
# Extend this map as wiring table analysis reveals new synonyms
ALIAS_MAP: dict[str, str] = {
    "24 VAC": "24VAC",
    "24 V AC": "24VAC",
    "24VAC AC": "24VAC",
    "HEAT PUMP": "HEAT-PUMP",
    "HEAT ONLY": "HEAT-ONLY",
    "COOL ONLY": "COOL-ONLY",
}


def normalize_node_id(raw: str) -> str:
    """
    Convert raw string to a stable, lowercase, hyphenated node_id.

    Examples:
        "RCHT9510WF" → "rcht9510wf"
        "2 Wire Heat Only" → "2-wire-heat-only"
        "Heat Pump" → "heat-pump"
    """
    return (
        raw.strip()
        .lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("_", "-")
        .replace("--", "-")
    )


def normalize_label(raw: str) -> str:
    """
    Apply alias map to label string and return canonical form.

    Examples:
        "24 VAC" → "24VAC"
        "conventional" → "conventional" (unchanged if not in alias map)
    """
    normalized = raw.strip().upper().replace("  ", " ")
    return ALIAS_MAP.get(normalized, raw.strip())


def normalize_node(node: dict) -> dict:
    """
    Return a copy of a node dict with normalized node_id and label.

    Input dict shape: {"node_id": str, "label": str, "kind": str, "properties": dict}
    """
    return {
        **node,
        "node_id": normalize_node_id(node["node_id"]),
        "label": normalize_label(node["label"]),
    }


def deduplicate_nodes(nodes: list[dict]) -> list[dict]:
    """
    Remove duplicate nodes by node_id, keeping the first occurrence.

    Args:
        nodes: list of node dicts (after normalization)

    Returns:
        Deduplicated list with stable ordering (first-seen wins)
    """
    seen: dict[str, dict] = {}
    for node in nodes:
        node_id = node["node_id"]
        if node_id not in seen:
            seen[node_id] = node
    return list(seen.values())


def normalize_and_deduplicate(nodes: list[dict]) -> list[dict]:
    """Normalize all nodes then deduplicate. Convenience function for ingest.py."""
    normalized = [normalize_node(n) for n in nodes]
    return deduplicate_nodes(normalized)
