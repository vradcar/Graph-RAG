from typing import Dict, List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-MiniLM-L6-v2"
_MIN_SIMILARITY = 0.25  # cosine similarity floor below which a hit is treated as irrelevant

_model: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    """Lazy singleton — the model is ~80MB and loading it is the expensive part."""
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


class SimpleVectorStore:
    """Semantic search over doc/node text using sentence-transformer embeddings."""

    def __init__(self):
        self.docs: List[Dict] = []
        self._embeddings: Optional[np.ndarray] = None

    def add_documents(self, docs: List[Dict]) -> None:
        self.docs.extend(docs)
        self._embeddings = None  # invalidate cache; rebuilt lazily on next search

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        if not self.docs:
            return []

        if self._embeddings is None:
            texts = [doc.get("text", "") for doc in self.docs]
            self._embeddings = _get_model().encode(texts, normalize_embeddings=True)

        query_embedding = _get_model().encode([query], normalize_embeddings=True)[0]
        scores = self._embeddings @ query_embedding  # cosine similarity (both sides normalized)

        ranked = np.argsort(-scores)[:top_k]
        return [self.docs[i] for i in ranked if scores[i] >= _MIN_SIMILARITY]
