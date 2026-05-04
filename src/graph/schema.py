from dataclasses import dataclass, field
from typing import Dict, Any, Literal, Optional, get_args

NODE_KIND = Literal[
    "Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec", "Document",
    "Thermostat", "Wallplate", "Adapter", "ZoningPanel",
    "WiringTerminal", "RoomSensor", "OperatingRange", "ElectricalSpec",
]
ALLOWED_RELATIONS = Literal[
    "COMPATIBLE_WITH", "REPLACES", "REPLACED_BY", "SUPPORTS_WIRING", "HAS_SPEC",
    "MENTIONED_IN", "NOT_COMPATIBLE_WITH", "HAS_ELECTRICAL_SPEC",
    "NEEDS_ADAPTER_IF_MISSING", "COMPLEX_ON", "REQUIRES", "CONNECTS_TO",
    "HAS_OPERATING_RANGE", "MOUNTS_ON",
]
VALID_KINDS: set[str] = set(get_args(NODE_KIND))
VALID_RELATIONS: set[str] = set(get_args(ALLOWED_RELATIONS))


@dataclass
class EntityNode:
    node_id: str
    label: str
    kind: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in VALID_KINDS:
            raise ValueError(
                f"Invalid node kind '{self.kind}'. Must be one of {VALID_KINDS}"
            )


@dataclass
class RelationEdge:
    source_id: str
    target_id: str
    relation: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.relation not in VALID_RELATIONS:
            raise ValueError(
                f"Invalid relation '{self.relation}'. Must be one of {VALID_RELATIONS}"
            )


@dataclass
class Document:
    doc_id: str
    title: str
    sku: Optional[str] = None
    source_url: Optional[str] = None
    ingested_at: Optional[str] = None  # ISO-8601; DB stores as datetime()
