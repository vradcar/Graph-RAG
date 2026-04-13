from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class EntityNode:
    node_id: str
    label: str
    kind: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RelationEdge:
    source_id: str
    target_id: str
    relation: str
    properties: Dict[str, Any] = field(default_factory=dict)
