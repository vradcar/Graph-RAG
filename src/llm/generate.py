"""
LLM answer generation with structured output via instructor.

Usage:
    from src.llm.generate import generate_answer, format_answer, QueryAnswer
"""
from typing import List

import instructor
from pydantic import BaseModel, Field


class EvidenceTriple(BaseModel):
    """A single graph triple used as evidence."""
    source: str
    relation: str
    target: str


class QueryAnswer(BaseModel):
    """Structured answer from the LLM."""
    prose: str = Field(description="Structured prose answer to the user's question")
    evidence: List[EvidenceTriple] = Field(description="Graph triples used to construct the answer")
    not_found: bool = Field(default=False, description="True if no relevant graph data was found")
    suggestion: str = Field(default="", description="If not_found=True, suggest a related question")


ANSWER_SYSTEM_PROMPT = (
    "You are an HVAC product knowledge assistant.\n"
    "Answer the user's question using ONLY the graph evidence provided.\n"
    "Return structured output with:\n"
    "- prose: a clear answer in 2-4 sentences\n"
    "- evidence: the specific triples that support your answer\n"
    "- not_found: true if the evidence does not contain relevant information\n"
    "- suggestion: if not_found, suggest a related question the user could ask\n"
    "Do not add information not present in the graph evidence."
)


def format_triples(triples: list[tuple[str, str, str]]) -> str:
    """Format triples as human-readable lines."""
    return "\n".join(f"- {src} --[{rel}]--> {tgt}" for src, rel, tgt in triples)


def generate_answer(
    client: instructor.Instructor,
    model: str,
    question: str,
    triples: list[tuple[str, str, str]],
) -> QueryAnswer:
    """Generate a structured answer from graph triples using the LLM."""
    if not triples:
        return QueryAnswer(
            prose="",
            evidence=[],
            not_found=True,
            suggestion="Try asking about T9 thermostat compatibility, wiring configurations, specifications, or replacements.",
        )

    try:
        return client.chat.completions.create(
            model=model,
            response_model=QueryAnswer,
            max_retries=2,
            messages=[
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nGraph evidence:\n{format_triples(triples)}",
                },
            ],
        )
    except Exception as e:
        import sys
        print(f"[generate] LLM answer generation failed: {e}", file=sys.stderr)
        return QueryAnswer(
            prose="",
            evidence=[],
            not_found=True,
            suggestion="LLM call failed. Please try again later.",
        )


def format_answer(answer: QueryAnswer) -> str:
    """Format a QueryAnswer as human-readable text."""
    if answer.not_found:
        lines = ["No relevant information found in the knowledge graph."]
        if answer.suggestion:
            lines.append(f"\nSuggestion: {answer.suggestion}")
        return "\n".join(lines)

    lines = [answer.prose, "", "Graph Evidence:"]
    for triple in answer.evidence:
        lines.append(f"  - {triple.source} --[{triple.relation}]--> {triple.target}")
    return "\n".join(lines)
