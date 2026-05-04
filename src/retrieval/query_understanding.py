"""LLM-based query understanding for unseen queries.

Used by the query pipeline when the fast-path regex/keyword retrieval finds
nothing. Returns candidate entity IDs, an intent classification, and free-text
search terms for the vector fallback.
"""
from typing import List, Literal, Optional

import instructor
from pydantic import BaseModel, Field


KNOWN_RELATIONS = [
    "REPLACED_BY",
    "REPLACES",
    "COMPATIBLE_WITH",
    "REQUIRES",
    "CONNECTS_TO",
    "HAS_ELECTRICAL_SPEC",
    "HAS_OPERATING_RANGE",
    "MOUNTS_ON",
    "NEEDS_ADAPTER_IF_MISSING",
    "PART_OF",
    "SUPPORTS",
]


class QueryUnderstanding(BaseModel):
    """Structured query understanding output."""
    entities: List[str] = Field(
        default_factory=list,
        description="Candidate product/accessory/spec IDs mentioned or implied by the question (e.g. T9, TH1110D, WALL-PLATE-A).",
    )
    intent: Literal["replacement", "compatibility", "spec", "general"] = Field(
        default="general",
        description="Best-fit intent for the question.",
    )
    search_terms: List[str] = Field(
        default_factory=list,
        description="Free-text keywords useful for vector search (e.g. 'heat pump', 'two-stage', 'wiring').",
    )


UNDERSTANDING_SYSTEM_PROMPT = (
    "You are a query understanding assistant for a Honeywell HVAC product knowledge graph.\n"
    "Given a user question, extract:\n"
    "- entities: any product SKUs, accessory codes, or component IDs the question refers to "
    "(use canonical forms like T9, TH1110D, WALL-PLATE-A, REDLINK-GATEWAY).\n"
    "- intent: one of replacement | compatibility | spec | general.\n"
    "- search_terms: 2-6 short keyword phrases that capture the topic of the question, "
    "useful for keyword-based vector search.\n"
    f"Known graph relations include: {', '.join(KNOWN_RELATIONS)}.\n"
    "If no specific entity is implied, return an empty entities list — do not invent IDs."
)


def understand_query(
    client: Optional[instructor.Instructor],
    model: str,
    question: str,
) -> QueryUnderstanding:
    """Run LLM query understanding. Returns an empty stub on failure."""
    if client is None:
        return QueryUnderstanding(entities=[], intent="general", search_terms=[])

    try:
        return client.chat.completions.create(
            model=model,
            response_model=QueryUnderstanding,
            max_retries=2,
            messages=[
                {"role": "system", "content": UNDERSTANDING_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        )
    except Exception as e:
        import sys
        print(f"[query_understanding] LLM call failed: {e}", file=sys.stderr)
        return QueryUnderstanding(entities=[], intent="general", search_terms=[])
