import pytest
import sys
from types import SimpleNamespace
from unittest.mock import Mock

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


def test_empty_embedding_batch_does_not_initialize_a_provider(monkeypatch):
    from app.services import knowledge_embeddings as service
    model = Mock(side_effect=AssertionError('Model must not initialize'))
    monkeypatch.setattr(service, 'local_model', model)
    assert service.embed(SimpleNamespace(provider='local'), []) == []
    model.assert_not_called()


def test_unknown_embedding_provider_fails_without_fallback():
    from app.services.knowledge_embeddings import embed
    with pytest.raises(ValueError, match='Unsupported embedding provider'):
        embed(SimpleNamespace(provider='unknown'), ['policy'])


@pytest.mark.parametrize('too_long', [False, True])
def test_local_embedding_token_budget_and_normalization(monkeypatch, too_long):
    from app.services import knowledge_embeddings as service
    model = SimpleNamespace(tokenizer=SimpleNamespace(encode=lambda text: list(range(6 if too_long else 2))),
        max_seq_length=5, encode=Mock(return_value=[[3, 4]]))
    monkeypatch.setattr(service, 'local_model', lambda *a: model)
    profile = SimpleNamespace(provider='local', model='synthetic', revision='pinned', dimensions=2)
    if too_long:
        with pytest.raises(ValueError, match='token limit'):
            service.embed(profile, ['policy'])
        model.encode.assert_not_called()
    else:
        assert service.embed(profile, ['policy']) == [[.6, .8]]
        model.encode.assert_called_once_with(['policy'], batch_size=4, normalize_embeddings=True, show_progress_bar=False)


def test_local_model_constructor_enforces_offline_trust_boundary(monkeypatch):
    from app.services import knowledge_embeddings as service
    constructor = Mock(return_value=object())
    monkeypatch.setitem(sys.modules, 'sentence_transformers', SimpleNamespace(SentenceTransformer=constructor))
    monkeypatch.setenv('AUDITMIND_MODEL_CACHE', 'synthetic-offline-cache')
    service.local_model.cache_clear()
    try:
        model = service.local_model('synthetic', 'immutable-revision')
        assert service.local_model('synthetic', 'immutable-revision') is model
        constructor.assert_called_once_with('synthetic', revision='immutable-revision', device='cpu',
            trust_remote_code=False, local_files_only=True, cache_folder='synthetic-offline-cache')
    finally:
        service.local_model.cache_clear()


@pytest.mark.parametrize('provider, module, key', [('openai', 'openai', 'OPENAI_API_KEY'), ('voyage', 'voyageai', 'VOYAGE_API_KEY')])
def test_external_embedding_missing_credentials_fails_closed(monkeypatch, provider, module, key):
    from app.services.knowledge_embeddings import embed
    monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(sys.modules, module, SimpleNamespace())
    if provider == 'openai':
        monkeypatch.setitem(sys.modules, module, SimpleNamespace(OpenAI=Mock()))
    with pytest.raises(ValueError, match='credentials are not configured'):
        embed(SimpleNamespace(provider=provider), ['policy'])


def test_openai_embedding_orders_and_validates_mocked_vectors(monkeypatch):
    from app.services.knowledge_embeddings import embed
    create = Mock(return_value=SimpleNamespace(data=[SimpleNamespace(index=1, embedding=[0, 1]),
        SimpleNamespace(index=0, embedding=[3, 4])]))
    constructor = Mock(return_value=SimpleNamespace(embeddings=SimpleNamespace(create=create)))
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=constructor))
    monkeypatch.setenv('OPENAI_API_KEY', 'mock-only')
    profile = SimpleNamespace(provider='openai', model='synthetic', dimensions=2)
    assert embed(profile, ['a', 'b']) == [[.6, .8], [0, 1]]
    constructor.assert_called_once_with(api_key='mock-only', timeout=60, max_retries=2)
    create.assert_called_once_with(model='synthetic', input=['a', 'b'], dimensions=2)


@pytest.mark.parametrize('query', [True, False])
def test_voyage_embedding_uses_explicit_input_type_without_truncation(monkeypatch, query):
    from app.services.knowledge_embeddings import embed
    call = Mock(return_value=SimpleNamespace(embeddings=[[3, 4]]))
    constructor = Mock(return_value=SimpleNamespace(embed=call))
    monkeypatch.setitem(sys.modules, 'voyageai', SimpleNamespace(Client=constructor))
    monkeypatch.setenv('VOYAGE_API_KEY', 'mock-only')
    assert embed(SimpleNamespace(provider='voyage', model='synthetic', dimensions=2), ['policy'], query=query) == [[.6, .8]]
    constructor.assert_called_once_with(api_key='mock-only', timeout=60, max_retries=2)
    call.assert_called_once_with(['policy'], model='synthetic', input_type='query' if query else 'document', truncation=False)
