"""Explicitly download and verify the pinned local embedding model."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.knowledge_embeddings import LOCAL_MODEL, LOCAL_REVISION, validate_vectors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Allow downloading public model files (no document upload)")
    args = parser.parse_args()
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("DO_NOT_TRACK", "1")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(LOCAL_MODEL, revision=LOCAL_REVISION, device="cpu",
        trust_remote_code=False, local_files_only=not args.download, cache_folder=os.environ.get("AUDITMIND_MODEL_CACHE"))
    texts = ["Require multi-factor authentication for administrators.",
             "Protect privileged accounts with an additional authentication factor.",
             "Restore backups to verify recovery objectives."]
    vectors = validate_vectors(model.encode(texts, normalize_embeddings=True, show_progress_bar=False), 3, 1024)
    similarity = lambda a, b: sum(x * y for x, y in zip(a, b))
    assert similarity(vectors[0], vectors[1]) > similarity(vectors[0], vectors[2]), "Local semantic smoke test failed"
    print(f"Ready: {LOCAL_MODEL}@{LOCAL_REVISION}; 1024 dimensions; semantic smoke test passed")


if __name__ == "__main__":
    main()
