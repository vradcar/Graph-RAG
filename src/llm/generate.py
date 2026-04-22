"""
LLM answer generation with structured output via instructor.

Usage:
    from src.llm.generate import generate_answer, format_answer, QueryAnswer
"""
from collections import Counter
from typing import List, Optional

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


def _normalize_triples(triples: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Deduplicate triples while preserving first-seen order."""
    seen = set()
    normalized = []
    for triple in triples:
        if triple not in seen:
            seen.add(triple)
            normalized.append(triple)
    return normalized


def _fallback_answer(question: str, triples: list[tuple[str, str, str]]) -> QueryAnswer:
    """Deterministic fallback answer when LLM call is unavailable."""
    triples = _normalize_triples(triples)
    if not triples:
        return QueryAnswer(
            prose="",
            evidence=[],
            not_found=True,
            suggestion="Try asking about T9 compatibility, replacement paths, or wiring requirements.",
        )

    rel_counts = Counter(rel for _, rel, _ in triples)

    q = question.lower()
    asks_replacement = any(t in q for t in ["replacement", "replace", "replaced"])
    asks_discontinued = any(t in q for t in ["discontinued", "legacy", "old part", "older part"])
    has_replacements = rel_counts.get("REPLACED_BY", 0) > 0 or rel_counts.get("REPLACES", 0) > 0

    if asks_replacement and (asks_discontinued or has_replacements):
        pairs = [(s, t) for s, r, t in triples if r in {"REPLACED_BY", "REPLACES"}]
        pair_lines = []
        for s, t in pairs[:4]:
            pair_lines.append(f"{s} -> {t}")
        pair_text = "; ".join(pair_lines) if pair_lines else "No explicit replacement pairs found"

        downstream = [
            (s, r, t)
            for s, r, t in triples
            if r in {"COMPATIBLE_WITH", "REQUIRES", "CONNECTS_TO", "HAS_ELECTRICAL_SPEC", "NEEDS_ADAPTER_IF_MISSING"}
        ]

        prose = (
            f"Replacement mapping found: {pair_text}. "
            f"Retrieved {len(downstream)} downstream context edges (compatibility, wiring, accessories, and electrical constraints) "
            f"to support migration planning beyond a 1-to-1 part swap."
        )
        evidence = [EvidenceTriple(source=s, relation=r, target=t) for s, r, t in triples[:18]]
        return QueryAnswer(prose=prose, evidence=evidence, not_found=False, suggestion="")

    top_relations = ", ".join([f"{rel} ({count})" for rel, count in rel_counts.most_common(3)])
    preview = "; ".join([f"{s} --[{r}]--> {t}" for s, r, t in triples[:4]])

    prose = (
        f"Retrieved {len(triples)} graph relationships relevant to the question. "
        f"Most common relation types: {top_relations}. "
        f"Example evidence: {preview}."
    )

    evidence = [EvidenceTriple(source=s, relation=r, target=t) for s, r, t in triples[:12]]
    return QueryAnswer(prose=prose, evidence=evidence, not_found=False, suggestion="")


def generate_answer(
    client: Optional[instructor.Instructor],
    model: str,
    question: str,
    triples: list[tuple[str, str, str]],
) -> QueryAnswer:
    """Generate a structured answer from graph triples using the LLM."""
    triples = _normalize_triples(triples)
    if not triples:
        return _fallback_answer(question, triples)

    q = question.lower()
    if any(t in q for t in ["replacement", "replace", "replaced", "discontinued", "legacy"]):
        # For replacement-style questions, prefer deterministic summaries so
        # we always expose enough evidence for single-hop vs multi-hop demos.
        return _fallback_answer(question, triples)

    if client is None:
        return _fallback_answer(question, triples)

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
        return _fallback_answer(question, triples)


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
