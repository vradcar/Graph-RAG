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

# node_id aliases → canonical node_id
# Merges duplicate entities that the LLM extracts with different IDs
NODE_ID_ALIASES: dict[str, str] = {
    "t9-wi-fi-thermostat": "rcht9610wf",
    "t9-thermostat": "rcht9610wf",
    "t9-smart-thermostat": "rcht9610wf",
    "t9": "rcht9610wf",
    "uwp-wall-plate": "uwp-wallplate",
    "uwp": "uwp-wallplate",
    "wall-plate": "uwp-wallplate",
    "wallplate": "uwp-wallplate",
    "wireless-sensor": "wireless-room-sensor",
}

# Nodes to exclude entirely — LLM hallucinates compatibility with these
# but the T9 manual explicitly says they are NOT supported
EXCLUDED_NODES: set[str] = {
    "line-voltage",
    "electric-baseboard",
    "electric-baseboard-120-240v",
    "millivolt",
    "millivolt-systems",
    "millivolt-system",
}

# node_id → correct kind override
# Fixes LLM misclassifications (e.g., c-wire extracted as Accessory but is a wiring requirement)
KIND_OVERRIDES: dict[str, str] = {
    "c-wire": "WiringConfig",
    "c-wire-common-wire": "WiringConfig",
}


def normalize_node_id(raw: str) -> str:
    """
    Convert raw string to a stable, lowercase, hyphenated node_id,
    then apply NODE_ID_ALIASES to merge known duplicates.

    Examples:
        "RCHT9510WF" → "rcht9510wf"
        "T9 Wi-Fi Thermostat" → "rcht9610wf"  (via alias)
        "2 Wire Heat Only" → "2-wire-heat-only"
    """
    normalized = (
        raw.strip()
        .lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("_", "-")
        .replace("--", "-")
    )
    return NODE_ID_ALIASES.get(normalized, normalized)


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
    node_id = normalize_node_id(node["node_id"])
    kind = KIND_OVERRIDES.get(node_id, node["kind"])
    return {
        **node,
        "node_id": node_id,
        "label": normalize_label(node["label"]),
        "kind": kind,
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
    """Normalize all nodes, remove excluded nodes, then deduplicate."""
    normalized = [normalize_node(n) for n in nodes]
    filtered = [n for n in normalized if n["node_id"] not in EXCLUDED_NODES]
    excluded_count = len(normalized) - len(filtered)
    if excluded_count:
        print(f"  Excluded {excluded_count} incompatible system nodes")
    return deduplicate_nodes(filtered)
