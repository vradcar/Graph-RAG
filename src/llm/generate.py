from typing import Dict, List


def generate_answer(question: str, graph_context: List[tuple], doc_context: List[Dict]) -> str:
    lines = [f"Question: {question}"]

    if graph_context:
        lines.append("Graph evidence:")
        for source, relation, target in graph_context[:12]:
            lines.append(f"- {source} --[{relation}]--> {target}")

    if doc_context:
        lines.append("Document evidence:")
        for hit in doc_context[:5]:
            lines.append(f"- {hit.get('id')}: {hit.get('text')}")

    lines.append("Draft answer: Replace this function with your LLM provider call.")
    return "\n".join(lines)
