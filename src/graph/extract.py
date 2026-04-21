"""
Graph extraction module — supports both legacy JSON product records (Week 1)
and rich PDF extraction (Week 2).

Week 1 functions (unchanged):
    - load_product_records(path)
    - product_records_to_graph_items(records)

Week 2 functions (new):
    - extract_from_pdf(pdf_path, replacements_path) -> rich graph dict
    - graph_items_to_legacy_format(graph) -> legacy-shape dict compatible with
      the existing GraphStore.upsert_node / upsert_edge API.

Legacy shape (Week 1):
    {"nodes": [{"node_id", "label", "kind", ...}], "edges": [{"source_id", "target_id", "relation", ...}]}

Rich shape (Week 2):
    {"nodes": [{"id", "type", "source_page", "properties": {...}}], "edges": [{"source", "target", "type", "source_page", "properties": {...}}], "source_document": {...}}
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# =========================================================================
# WEEK 1 — Legacy JSON product records (kept for backward compatibility)
# =========================================================================

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


# =========================================================================
# WEEK 2 — PDF extraction (Honeywell T9 Installation Guide)
# =========================================================================
# Requires pdfplumber. Imported lazily so Week 1 paths don't need it at import
# time — callers that never touch PDF will never trigger the import.

def _slug(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _page_text(pdf, page_number: int) -> str:
    return pdf.pages[page_number - 1].extract_text() or ""


# Canonical wiring terminal metadata — used to look up human-readable functions
# for each terminal label pulled off page 6 of the T9 guide.
TERMINAL_FUNCTIONS: Dict[str, str] = {
    "A": "Auxiliary / L1 output",
    "C": "Common wire, 24V AC return (required)",
    "E": "Emergency heat (heat pump)",
    "G": "Fan relay",
    "K": "Combined fan / auxiliary",
    "O/B": "Heat pump reversing valve",
    "U": "Configurable universal terminal",
    "R": "24V AC power (single transformer)",
    "Rc": "24V AC cooling transformer",
    "Rh": "24V AC heating transformer",
    "W": "Heating stage 1",
    "W2": "Auxiliary / second-stage heat",
    "Y": "Cooling stage 1",
    "Y2": "Cooling stage 2",
}


# --- Page 3: compatibility + electrical spec + C-Wire Adapter + zoning ---

def _extract_compatibility_and_power(pdf) -> Tuple[List[Dict], List[Dict]]:
    text = _page_text(pdf, 3)
    nodes: List[Dict] = []
    edges: List[Dict] = []
    thermostat_id = "t9_rcht9610wf"

    compat_systems = [
        {"id": "forced_air_heating", "name": "Forced Air Heating System", "voltage_class": "low_voltage_24v"},
        {"id": "central_cooling", "name": "Central Cooling System", "voltage_class": "low_voltage_24v"},
        {"id": "heat_pump", "name": "Heat Pump System", "voltage_class": "low_voltage_24v"},
    ]
    for sys in compat_systems:
        nodes.append({
            "id": sys["id"], "type": "HVACSystemType", "source_page": 3,
            "properties": {"name": sys["name"], "voltage_class": sys["voltage_class"]},
        })
        edges.append({
            "source": thermostat_id, "target": sys["id"],
            "type": "COMPATIBLE_WITH", "source_page": 3,
        })

    incompat_systems = [
        {"id": "electric_baseboard", "name": "Electric Baseboard Heat", "voltage_class": "line_voltage",
         "reason": "Line voltage 120-240V; T9 is a 24V AC low-voltage thermostat"},
        {"id": "millivolt", "name": "Millivolt System", "voltage_class": "millivolt",
         "reason": "Millivolt systems are not supported by the T9"},
    ]
    for sys in incompat_systems:
        nodes.append({
            "id": sys["id"], "type": "HVACSystemType", "source_page": 3,
            "properties": {"name": sys["name"], "voltage_class": sys["voltage_class"]},
        })
        edges.append({
            "source": thermostat_id, "target": sys["id"],
            "type": "NOT_COMPATIBLE_WITH", "source_page": 3,
            "properties": {"reason": sys["reason"]},
        })

    # "INPUT: 24V~@60Hz, 0.2A" — the PDF uses ~@ between voltage and frequency.
    spec_match = re.search(r"INPUT:\s*(\d+)\s*V[^0-9]*?(\d+)\s*Hz[^0-9]*?([\d.]+)\s*A", text)
    if spec_match:
        voltage, frequency, current = spec_match.groups()
        log.info("Parsed electrical spec: %sV / %sHz / %sA", voltage, frequency, current)
    else:
        log.warning("Electrical spec regex did not match on page 3; using documented defaults")
        voltage, frequency, current = "24", "60", "0.2"

    nodes.append({
        "id": "t9_power", "type": "ElectricalSpec", "source_page": 3,
        "properties": {
            "voltage_v": float(voltage), "frequency_hz": float(frequency), "current_a": float(current),
        },
    })
    edges.append({
        "source": thermostat_id, "target": "t9_power",
        "type": "HAS_ELECTRICAL_SPEC", "source_page": 3,
    })

    nodes.append({
        "id": "c_wire_adapter", "type": "Adapter", "source_page": 3,
        "properties": {"name": "C-Wire Adapter", "included": True},
    })
    edges.append({
        "source": thermostat_id, "target": "c_wire_adapter",
        "type": "NEEDS_ADAPTER_IF_MISSING", "source_page": 3,
        "properties": {"condition": "No C-Wire present at thermostat"},
    })

    nodes.append({
        "id": "zoning_panel", "type": "ZoningPanel", "source_page": 7,
        "properties": {"name": "Zoning Panel Installation"},
    })
    edges.append({
        "source": "c_wire_adapter", "target": "zoning_panel",
        "type": "COMPLEX_ON", "source_page": 7,
        "properties": {"note": "Professional installer recommended on zoned systems"},
    })

    return nodes, edges


# --- Page 6: wiring terminal checklist ---

def _extract_wiring_terminals(pdf) -> Tuple[List[Dict], List[Dict]]:
    """
    Page 6 renders the wiring checklist with Wingdings-style checkbox glyphs
    (the `¨` character in extracted text). pdfplumber cannot parse this as a
    clean table, so we parse the page text directly.
    """
    thermostat_id = "t9_rcht9610wf"
    nodes: List[Dict] = []
    edges: List[Dict] = []

    text = _page_text(pdf, 6)
    raw_entries = re.findall(r"¨\s*([^¨\n*]+?)(?=\s*¨|\s*\*|\n|$)", text)

    def canonicalize(raw: str) -> Optional[str]:
        s = raw.strip()
        s = re.sub(r"\s+Required\s*$", "", s, flags=re.IGNORECASE)
        if s.startswith("A"): return "A"
        if s.startswith("W2"): return "W2"
        if s.startswith("U"): return "U"
        s = s.strip()
        if s in TERMINAL_FUNCTIONS:
            return s
        return None

    labels_found: set = set()
    for raw in raw_entries:
        label = canonicalize(raw)
        if label:
            labels_found.add(label)

    documented = set(TERMINAL_FUNCTIONS.keys())
    if len(labels_found) < 10:
        missing = documented - labels_found
        log.warning("Page 6 text parse only found %d terminals; adding %s from documented fallback",
                    len(labels_found), sorted(missing))
        labels_found |= documented
    else:
        log.info("Page 6 extracted %d wiring terminals from text", len(labels_found))

    for label in sorted(labels_found):
        term_id = f"terminal_{_slug(label)}"
        required = (label == "C")
        nodes.append({
            "id": term_id, "type": "WiringTerminal", "source_page": 6,
            "properties": {"label": label, "function": TERMINAL_FUNCTIONS.get(label, "Unspecified")},
        })
        edges.append({
            "source": thermostat_id, "target": term_id,
            "type": "REQUIRES", "source_page": 6,
            "properties": {"required": required},
        })

    return nodes, edges


# --- Page 13: room sensor ---

def _extract_room_sensor(pdf) -> Tuple[List[Dict], List[Dict]]:
    text = _page_text(pdf, 13)
    thermostat_id = "t9_rcht9610wf"

    range_match = re.search(r"(\d+)\s*-?\s*foot", text)
    count_match = re.search(r"(\d+)\s+sensors", text)
    max_range = int(range_match.group(1)) if range_match else 200
    max_count = int(count_match.group(1)) if count_match else 20

    if not range_match or not count_match:
        log.warning("Page 13 regex fallback used (range=%s, count=%s)", max_range, max_count)

    node = {
        "id": "wireless_room_sensor", "type": "RoomSensor", "source_page": 13,
        "properties": {
            "name": "Honeywell Wireless Room Sensor",
            "capabilities": ["temperature", "humidity", "occupancy"],
        },
    }
    edge = {
        "source": thermostat_id, "target": "wireless_room_sensor",
        "type": "CONNECTS_TO", "source_page": 13,
        "properties": {"max_count": max_count, "max_range_ft": max_range},
    }
    return [node], [edge]


# --- Page 16: operating ranges ---

def _extract_operating_ranges(pdf) -> Tuple[List[Dict], List[Dict]]:
    text = _page_text(pdf, 16)
    thermostat_id = "t9_rcht9610wf"
    nodes: List[Dict] = []
    edges: List[Dict] = []

    pattern = re.compile(r"(Heat|Cool):\s*(\d+)\s*°?F\s*to\s*(\d+)\s*°?F", re.IGNORECASE)
    matches = pattern.findall(text)
    if not matches:
        log.warning("Page 16 operating range regex did not match; using documented defaults")
        matches = [("Heat", "40", "90"), ("Cool", "50", "99")]

    for mode, lo, hi in matches:
        mode_l = mode.lower()
        range_id = f"t9_{mode_l}_range"
        nodes.append({
            "id": range_id, "type": "OperatingRange", "source_page": 16,
            "properties": {"mode": mode_l, "min_f": int(lo), "max_f": int(hi)},
        })
        edges.append({
            "source": thermostat_id, "target": range_id,
            "type": "HAS_OPERATING_RANGE", "source_page": 16,
        })
    return nodes, edges


# --- Root + curated replacement chains ---

def _build_thermostat_nodes(replacements_path: Optional[Path]) -> Tuple[List[Dict], List[Dict]]:
    nodes: List[Dict] = []
    edges: List[Dict] = []

    nodes.append({
        "id": "t9_rcht9610wf", "type": "Thermostat", "source_page": 1,
        "properties": {
            "name": "Honeywell Home T9 Wi-Fi Smart Thermostat",
            "model_number": "RCHT9610WF", "status": "current",
            "product_family": "T-Series", "wifi": True,
        },
    })
    nodes.append({
        "id": "uwp", "type": "Wallplate", "source_page": 2,
        "properties": {"name": "UWP Wallplate"},
    })
    edges.append({
        "source": "t9_rcht9610wf", "target": "uwp",
        "type": "MOUNTS_ON", "source_page": 10,
    })

    if replacements_path and replacements_path.exists():
        with replacements_path.open() as f:
            data = json.load(f)

        existing_ids = {n["id"] for n in nodes}
        for therm in data.get("thermostats", []):
            if therm["id"] in existing_ids:
                continue
            nodes.append({
                "id": therm["id"], "type": "Thermostat",
                "source_page": therm.get("source_page") or 0,
                "properties": {k: v for k, v in therm.items() if k not in ("id", "source_page")},
            })

        for rep in data.get("replacements", []):
            edge: Dict[str, Any] = {
                "source": rep["from"], "target": rep["to"],
                "type": "REPLACED_BY", "source_page": 0,
            }
            if "replacement_date" in rep:
                edge["properties"] = {"replacement_date": rep["replacement_date"]}
            edges.append(edge)

        log.info("Merged %d thermostat records and %d replacement edges from curated data",
                 len(data.get("thermostats", [])), len(data.get("replacements", [])))
    else:
        log.info("No replacements file provided; graph will contain T9 only")

    return nodes, edges


def _validate(graph: Dict) -> List[str]:
    errs: List[str] = []
    node_ids = {n["id"] for n in graph["nodes"]}
    for n in graph["nodes"]:
        for k in ("id", "type", "source_page"):
            if k not in n:
                errs.append(f"Node missing {k}: {n}")
    for e in graph["edges"]:
        for k in ("source", "target", "type", "source_page"):
            if k not in e:
                errs.append(f"Edge missing {k}: {e}")
        if e["source"] not in node_ids:
            errs.append(f"Edge source {e['source']} not in nodes")
        if e["target"] not in node_ids:
            errs.append(f"Edge target {e['target']} not in nodes")
    return errs


def extract_from_pdf(pdf_path: Path, replacements_path: Optional[Path] = None) -> Dict:
    """
    Extract a rich graph dict from the T9 installation guide PDF.

    Returns the Week 2 rich shape:
        {"source_document": {...}, "nodes": [...], "edges": [...]}

    Use graph_items_to_legacy_format() to convert the result into the Week 1
    shape that GraphStore accepts directly.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError(
            "pdfplumber is required for PDF extraction. "
            "Install it via: pip install pdfplumber"
        ) from exc

    log.info("Opening PDF: %s", pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        log.info("PDF loaded: %d pages", len(pdf.pages))

        all_nodes: List[Dict] = []
        all_edges: List[Dict] = []

        for fn in (
            lambda: _build_thermostat_nodes(replacements_path),
            lambda: _extract_compatibility_and_power(pdf),
            lambda: _extract_wiring_terminals(pdf),
            lambda: _extract_room_sensor(pdf),
            lambda: _extract_operating_ranges(pdf),
        ):
            n, e = fn()
            all_nodes.extend(n)
            all_edges.extend(e)

        pages = len(pdf.pages)

    graph = {
        "source_document": {
            "name": "Honeywell Home T9 Wi-Fi Thermostat Installation Guide",
            "pages": pages,
        },
        "nodes": all_nodes,
        "edges": all_edges,
    }

    errors = _validate(graph)
    if errors:
        log.error("Validation failed with %d errors:", len(errors))
        for err in errors:
            log.error("  %s", err)
        raise ValueError(f"Graph validation failed with {len(errors)} errors")

    log.info("Extracted %d nodes, %d edges from PDF", len(all_nodes), len(all_edges))
    return graph


# =========================================================================
# Adapter: rich Week 2 shape → legacy Week 1 shape
# =========================================================================
# The existing GraphStore (src/graph/store.py) expects:
#   nodes: {"node_id", "label", "kind", ... extra attributes flattened}
#   edges: {"source_id", "target_id", "relation", ... extra attributes flattened}
#
# Week 2 rich format uses:
#   nodes: {"id", "type", "source_page", "properties": {...}}
#   edges: {"source", "target", "type", "source_page", "properties": {...}}
#
# This adapter translates between them so ingest.py can emit a file that the
# existing GraphStore can load unchanged.

def graph_items_to_legacy_format(graph: Dict) -> Dict[str, List[Dict]]:
    """Convert a Week 2 rich graph dict to the Week 1 legacy shape."""
    legacy_nodes: List[Dict] = []
    legacy_edges: List[Dict] = []

    for n in graph.get("nodes", []):
        props = n.get("properties", {}) or {}
        legacy_node = {
            "node_id": n["id"],
            "label": props.get("name") or props.get("label") or n["id"],
            "kind": n["type"],
            "source_page": n.get("source_page"),
        }
        # Flatten property values into the node dict, but don't clobber the
        # structural keys we just set.
        reserved = {"node_id", "label", "kind", "source_page"}
        for k, v in props.items():
            if k not in reserved:
                legacy_node[k] = v
        legacy_nodes.append(legacy_node)

    for e in graph.get("edges", []):
        props = e.get("properties", {}) or {}
        legacy_edge = {
            "source_id": e["source"],
            "target_id": e["target"],
            "relation": e["type"],
            "source_page": e.get("source_page"),
        }
        reserved = {"source_id", "target_id", "relation", "source_page"}
        for k, v in props.items():
            if k not in reserved:
                legacy_edge[k] = v
        legacy_edges.append(legacy_edge)

    return {"nodes": legacy_nodes, "edges": legacy_edges}
