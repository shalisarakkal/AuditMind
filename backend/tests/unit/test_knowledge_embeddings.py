import pytest

from app.services.knowledge_embeddings import chunk_text, validate_vectors


def test_chunks_cover_unicode_without_losing_text():
    text = "# Policy\n" + "身份验证 requires authentication.\n" * 300
    chunks = chunk_text(text)
    covered = set()
    for start, end, content in chunks:
        assert content == text[start:end]
        assert len(content.encode("utf-8")) <= 2400
        covered.update(range(start, end))
    assert covered == set(range(len(text)))


def test_empty_document_rejected():
    with pytest.raises(ValueError, match="no text"):
        chunk_text(" \n ")


@pytest.mark.parametrize("vectors,count,dimensions", [
    ([[1, 2]], 2, 2), ([[1, 2]], 1, 3), ([[0, 0]], 1, 2),
    ([[float('nan'), 1]], 1, 2), ([[float('inf'), 1]], 1, 2),
])
def test_invalid_vectors_rejected(vectors, count, dimensions):
    with pytest.raises(ValueError):
        validate_vectors(vectors, count, dimensions)


def test_vectors_normalized():
    assert validate_vectors([[3, 4]], 1, 2) == [[0.6, 0.8]]
