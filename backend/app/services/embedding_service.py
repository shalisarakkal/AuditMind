"""Embedding service generating 1536-dimensional vectors for pgvector RAG.
Supports local deterministic vector generation (for offline tests/dev)
as well as cloud providers (OpenAI, Voyage AI).
"""

import hashlib
import math
from typing import Sequence

from app.core.config import settings
from app.models.document import EMBEDDING_DIM


def _deterministic_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Generates a reproducible, unit-normalized float vector of dimension `dim`
    derived from text tokens and n-grams. Used in dev/test to allow real pgvector
    cosine similarity operations without requiring paid external API calls.
    """
    if not text:
        return [0.0] * dim

    words = text.lower().split()
    vector = [0.0] * dim

    for i, word in enumerate(words):
        # Hash individual words and pairs
        h1 = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        idx1 = h1 % dim
        vector[idx1] += 1.0 / (1.0 + i * 0.05)

        if i + 1 < len(words):
            pair = f"{word}_{words[i+1]}"
            h2 = int(hashlib.sha256(pair.encode("utf-8")).hexdigest(), 16)
            idx2 = h2 % dim
            vector[idx2] += 0.5

    # Compute Euclidean norm
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0.0:
        return [v / norm for v in vector]
    return [0.0] * dim


def get_embedding(text: str) -> list[float]:
    """Generates a 1536-dimensional embedding vector for a single text."""
    provider = (settings.EMBEDDING_PROVIDER or "local_deterministic").lower()

    if provider == "openai" and settings.OPENAI_API_KEY:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            resp = client.embeddings.create(input=text, model=settings.EMBEDDING_MODEL)
            return resp.data[0].embedding
        except Exception:
            # Fall back gracefully to deterministic embedding
            return _deterministic_embedding(text)

    if provider == "voyage" and settings.VOYAGE_API_KEY:
        try:
            import voyageai

            vo = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
            result = vo.embed([text], model="voyage-3")
            return result.embeddings[0]
        except Exception:
            return _deterministic_embedding(text)

    return _deterministic_embedding(text)


def get_embeddings_batch(texts: Sequence[str]) -> list[list[float]]:
    """Generates embeddings for a batch of texts."""
    return [get_embedding(t) for t in texts]
