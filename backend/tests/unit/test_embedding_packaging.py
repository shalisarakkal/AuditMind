"""Static deployment contracts; these do not substitute for a Docker smoke test."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys

from app.services import knowledge_embeddings


def test_local_model_is_offline_pinned_and_uses_explicit_cache(monkeypatch):
    factory = Mock()
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=factory))
    monkeypatch.setenv("AUDITMIND_MODEL_CACHE", "/readonly-models")
    knowledge_embeddings.local_model.cache_clear()
    try:
        knowledge_embeddings.local_model(knowledge_embeddings.LOCAL_MODEL, knowledge_embeddings.LOCAL_REVISION)
        factory.assert_called_once_with(knowledge_embeddings.LOCAL_MODEL,
            revision=knowledge_embeddings.LOCAL_REVISION, device="cpu", trust_remote_code=False,
            local_files_only=True, cache_folder="/readonly-models")
    finally:
        knowledge_embeddings.local_model.cache_clear()


def test_image_excludes_secrets_and_separates_migrations_from_startup():
    backend = Path(__file__).resolve().parents[2]
    dockerfile = (backend / "Dockerfile").read_text()
    ignored = (backend / ".dockerignore").read_text().splitlines()
    assert {".env", ".env.*", ".venv", "uploads"} <= set(ignored)
    assert "USER auditmind" in dockerfile
    assert "INSTALL_EMBEDDINGS" in dockerfile and "HF_HUB_OFFLINE=1" in dockerfile
    assert "alembic upgrade" not in dockerfile
    deployment = (backend.parent / "infra/compose.embeddings.yml").read_text()
    assert 'command: ["python", "-m", "app.worker"]' in deployment
    assert deployment.count(":/models:ro") == 2
