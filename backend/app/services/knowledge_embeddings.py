"""Explicit embedding profiles; provider failure never changes the vector space."""

import math
import os
from functools import lru_cache

from app.models.knowledge import EmbeddingProfile

LOCAL_MODEL = "BAAI/bge-m3"
LOCAL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"


@lru_cache(maxsize=2)
def local_model(model: str, revision: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        model, revision=revision, device="cpu", trust_remote_code=False,
        local_files_only=True, cache_folder=os.environ.get("AUDITMIND_MODEL_CACHE"),
    )


def validate_vectors(vectors, count: int, dimensions: int) -> list[list[float]]:
    if len(vectors) != count:
        raise ValueError("Embedding provider returned an incorrect number of vectors")
    result = []
    for vector in vectors:
        values = [float(value) for value in vector]
        if len(values) != dimensions or not all(math.isfinite(value) for value in values):
            raise ValueError("Embedding dimension or numeric value is invalid")
        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0:
            raise ValueError("Embedding provider returned a zero vector")
        result.append([value / norm for value in values])
    return result


def embed(profile: EmbeddingProfile, texts: list[str], *, query: bool = False) -> list[list[float]]:
    if not texts:
        return []
    if profile.provider == "local":
        model = local_model(profile.model, profile.revision)
        if any(len(model.tokenizer.encode(text)) > model.max_seq_length for text in texts):
            raise ValueError("Text exceeds the local model token limit; rechunk before embedding")
        vectors = model.encode(texts, batch_size=4, normalize_embeddings=True, show_progress_bar=False)
    elif profile.provider == "openai":
        from openai import OpenAI

        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OpenAI embedding credentials are not configured")
        client = OpenAI(api_key=key, timeout=60, max_retries=2)
        response = client.embeddings.create(model=profile.model, input=texts, dimensions=profile.dimensions)
        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
    elif profile.provider == "voyage":
        import voyageai

        key = os.environ.get("VOYAGE_API_KEY")
        if not key:
            raise ValueError("Voyage embedding credentials are not configured")
        client = voyageai.Client(api_key=key, timeout=60, max_retries=2)
        response = client.embed(texts, model=profile.model, input_type="query" if query else "document", truncation=False)
        vectors = response.embeddings
    else:
        raise ValueError("Unsupported embedding provider")
    return validate_vectors(vectors, len(texts), profile.dimensions)


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[tuple[int, int, str]]:
    """Bound UTF-8 bytes as well as characters, safely below supported token windows."""
    if not text.strip():
        raise ValueError("Document contains no text")
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        while len(text[start:end].encode("utf-8")) > 2400:
            end -= 1
        if end < len(text):
            boundary = text.rfind("\n", start + (end - start) // 2, end)
            if boundary > start:
                end = boundary + 1
        content = text[start:end]
        if content.strip():
            chunks.append((start, end, content))
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks
