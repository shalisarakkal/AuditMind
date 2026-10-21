"""Unit tests for embedding service and standards corpus."""

from app.data.standards_corpus import STANDARDS_DATA
from app.models.document import EMBEDDING_DIM
from app.services.embedding_service import get_embedding, get_embeddings_batch


def test_embedding_dimensions():
    text = "Access control and multi-factor authentication for administrators."
    vec = get_embedding(text)
    assert len(vec) == EMBEDDING_DIM
    assert isinstance(vec[0], float)
    # Check normalized unit length (sum of squares is ~1.0)
    norm = sum(x * x for x in vec)
    assert abs(norm - 1.0) < 1e-4


def test_embedding_deterministic():
    text = "Test deterministic embedding value"
    v1 = get_embedding(text)
    v2 = get_embedding(text)
    assert v1 == v2


def test_embedding_batch():
    texts = ["CIS-1.1 Inventory", "NIST-PR.AC-01 Access Control"]
    batch = get_embeddings_batch(texts)
    assert len(batch) == 2
    assert len(batch[0]) == EMBEDDING_DIM
    assert len(batch[1]) == EMBEDDING_DIM


def test_standards_corpus_integrity():
    assert len(STANDARDS_DATA) >= 20
    frameworks = {item["framework"] for item in STANDARDS_DATA}
    assert "CIS" in frameworks
    assert "NIST" in frameworks
    assert "ISO" in frameworks
    for item in STANDARDS_DATA:
        assert item["control_id"]
        assert item["title"]
        assert item["content"]
