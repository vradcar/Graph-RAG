"""
LLM-based entity extractor using Groq + instructor + Pydantic.

Enforces closed-world enum for node kinds and relation types at the Pydantic type
level — instructor retries if the LLM returns an invalid value.

NODE_KIND and ALLOWED_RELATIONS are imported from src.graph.schema (single source of truth).
NEVER redefine them here.
"""
from typing import List

import instructor
from pydantic import BaseModel, Field

from src.graph.schema import NODE_KIND, ALLOWED_RELATIONS
from src.llm.provider import build_instructor_client


# ---------------------------------------------------------------------------
# Pydantic extraction models
# ---------------------------------------------------------------------------

class ExtractedNode(BaseModel):
    node_id: str = Field(
        description=(
            "Stable, unique identifier for this entity. Use the product model number for "
            "Product nodes (e.g. 'RCHT9510WF'), lowercase-hyphenated slugs for others "
            "(e.g. '2-wire-heat-only', 'heat-pump'). Must be consistent across pages."
        )
    )
    label: str = Field(description="Human-readable name (e.g. 'T9 Smart Thermostat')")
    kind: NODE_KIND = Field(description="Node type: Product | Accessory | WiringConfig | HVACSystemType | Spec")
    properties: dict = Field(
        default_factory=dict,
        description=(
            "Additional properties. For Product: include 'status' (active/discontinued), "
            "'description'. For Spec: include 'value' and 'unit'. For WiringConfig: include "
            "'wire_count' if known."
        )
    )


class ExtractedEdge(BaseModel):
    source_id: str = Field(description="node_id of the source node")
    target_id: str = Field(description="node_id of the target node")
    relation: ALLOWED_RELATIONS = Field(
        description=(
            "Relationship type. Must be one of: COMPATIBLE_WITH, REPLACES, "
            "SUPPORTS_WIRING, HAS_SPEC. No other values are allowed."
        )
    )


class ExtractionResult(BaseModel):
    nodes: List[ExtractedNode] = Field(default_factory=list)
    edges: List[ExtractedEdge] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# System prompt — embedded in the extractor, not in the pipeline
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You are a product knowledge graph extractor.

Extract entities and relationships from HVAC thermostat documentation.

Node kinds (use EXACTLY these values):
- Product: thermostats, sensors, devices with model numbers
- Accessory: add-on hardware that works with a product
- WiringConfig: wiring configurations (e.g., "2-wire", "4-wire heat/cool")
- HVACSystemType: HVAC system types (e.g., "heat pump", "conventional", "heat only")
- Spec: specifications like voltage, dimensions, temperature range

Relationship types (use EXACTLY these values — no synonyms allowed):
- COMPATIBLE_WITH: product works with accessory or HVAC system type
- REPLACES: one product replaces an older product
- SUPPORTS_WIRING: product supports a wiring configuration
- HAS_SPEC: product has a specification

Rules:
1. Use the product model number (e.g., RCHT9510WF) as the node_id for Product nodes
2. Use lowercase-hyphenated slugs for non-product nodes (e.g., "2-wire-heat-only")
3. If a model number appears as compatible or replaced, create a Product node for it
4. Only extract relationships explicitly stated in the text — do not infer
5. If no entities are found on this page, return empty lists
"""


# ---------------------------------------------------------------------------
# Client factory and extraction function
# ---------------------------------------------------------------------------

def build_client(provider: str = "groq") -> instructor.Instructor:
    """
    Build an instructor-wrapped LLM client.

    Delegates to src.llm.provider.build_instructor_client for all provider logic.
    Defaults to "groq" for backward compatibility.

    Args:
        provider: LLM provider name — "groq" or "openai".

    Raises:
        ValueError: If the required API key is not set or provider is unknown.
    """
    return build_instructor_client(provider)


def extract_from_page(
    client: instructor.Instructor,
    model: str,
    page: dict,
) -> ExtractionResult:
    """
    Extract entities and relationships from a single page dict.

    Args:
        client: instructor-wrapped Groq client from build_client()
        model: Groq model name (e.g., "llama-3.1-8b-instant")
        page: page dict with keys page_num, prose, tables

    Returns:
        ExtractionResult with nodes and edges lists
    """
    from src.ingest.pdf_parser import format_page_for_llm
    content = format_page_for_llm(page)
    if not content.strip():
        return ExtractionResult()

    return client.chat.completions.create(
        model=model,
        response_model=ExtractionResult,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        max_retries=2,
    )
