"""
Entity normalization and deduplication before Neo4j write.

Converts LLM-extracted node_ids and labels to canonical forms to prevent
graph fragmentation (e.g., "24VAC" vs "24 VAC" becoming two Spec nodes).
"""
import re

# SKU regex covering Honeywell HVAC product families across the v2.0 corpus.
# Includes RCHT, TH/THX/THP, RTH, HZ, THM and the C7\d{3} sensor family (T10).
# C7 prefix covers C7089, C7189 sensor part numbers (e.g. C7189R3002-2, C7089R3013).
SKU_REGEX = re.compile(r"(RCHT|TH[XP]?|RTH|HZ|THM|THP|C7)\d{3,4}[A-Z0-9\-]*")


def is_sku(raw: str) -> bool:
    """Return True if the raw string looks like a Honeywell SKU per SKU_REGEX."""
    return bool(SKU_REGEX.fullmatch(raw.strip()))


# Known label aliases → canonical form
# Extend this map as wiring table analysis reveals new synonyms
ALIAS_MAP: dict[str, str] = {
    "24 VAC": "24VAC",
    "24 V AC": "24VAC",
    "24VAC AC": "24VAC",
    "HEAT PUMP": "HEAT-PUMP",
    "HEAT ONLY": "HEAT-ONLY",
    "COOL ONLY": "COOL-ONLY",
    "UWP MOUNTING SYSTEM": "UWP",
    "C-WIRE ADAPTER": "THP9045",
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

    # --- UWP family (T6/T9 cross-doc bridge) ---
    "uwp-mounting-system": "uwp-wallplate",

    # --- THX9321R subbase family (THP9045 ↔ T9) ---
    "thx9321r5000": "thx9321r",
    "thx9321r1008": "thx9321r",
    "thx9321r-subbase": "thx9321r",

    # --- HVAC terminals (canonical slug: terminal-<letter>) ---
    "r": "terminal-r",
    "r-wire": "terminal-r",
    "r-terminal": "terminal-r",
    "24v-power-r": "terminal-r",
    "c": "terminal-c",
    "c-terminal": "terminal-c",
    "common-c": "terminal-c",
    "y": "terminal-y",
    "y-terminal": "terminal-y",
    "g": "terminal-g",
    "g-terminal": "terminal-g",
    "w": "terminal-w",
    "w-terminal": "terminal-w",
    "o-b": "terminal-o-b",
    "o-or-b": "terminal-o-b",
    "ob": "terminal-o-b",
    "k": "terminal-k",
    "aux": "terminal-aux",
    "e": "terminal-e",
    "l": "terminal-l",

    # --- HVAC system type slugs ---
    "1-heat-1-cool": "1h-1c",
    "2-heat-1-cool": "2h-1c",
    "2-heat-2-cool": "2h-2c",
    "3-heat-2-cool": "3h-2c",
    "heat-pump-1h-1c": "heat-pump-1h-1c",
    "heat-pump-2h-1c": "heat-pump-2h-1c",
    "heat-pump-3h-2c": "heat-pump-3h-2c",
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
    normalized = raw.strip().lower()
    normalized = re.sub(r"[ /_.]+", "-", normalized)  # collapse any run of separators
    normalized = normalized.strip("-")
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
