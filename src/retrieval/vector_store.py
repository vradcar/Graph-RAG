import re
from typing import Dict, List


def _tokenize(text: str) -> set:
    return set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


class SimpleVectorStore:
    def __init__(self):
        self.docs: List[Dict] = []

    def add_documents(self, docs: List[Dict]) -> None:
        self.docs.extend(docs)

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        q_tokens = _tokenize(query)
        scored = []

        for doc in self.docs:
            d_tokens = _tokenize(doc.get("text", ""))
            overlap = len(q_tokens & d_tokens)
            if overlap > 0:
                scored.append((overlap, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:top_k]]
