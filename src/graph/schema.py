from dataclasses import dataclass, field
from typing import Dict, Any, Literal, get_args

NODE_KIND = Literal["Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec"]
ALLOWED_RELATIONS = Literal[
    "COMPATIBLE_WITH", "REPLACES", "SUPPORTS_WIRING", "HAS_SPEC"
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
