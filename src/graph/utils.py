"""
Shared graph utilities.

Lightweight helpers shared across provenance.py and neo4j_loader.py.
Import via: from src.graph.utils import clean_props
"""

from __future__ import annotations

import json
from typing import Any, Dict


def clean_props(d: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten dict to Neo4j-safe scalar / primitive-list values.

    Neo4j properties cannot be nested dicts or None. Lists of primitives are
    fine. Converts anything Neo4j won't accept into a JSON string so the data
    survives the round trip.
    """
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) for x in v):
            out[k] = v
        else:
            out[k] = json.dumps(v)
    return out
