"""Configuration identity captured from the installed parser and actual settings."""
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path


def _installed_parser_revision():
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256(b"scan-config-v1\0")
    runtime = {"python": platform.python_version(), **{name: version(name) for name in ("pydantic", "ijson", "defusedxml")}}
    digest.update(json.dumps(runtime, sort_keys=True).encode() + b"\0")
    for name in ("import_configuration.py", "ingestion_service.py", "import_profiles.py", "import_matching.py", "import_readers.py",
            "nessus_parser.py", "event_sources.py", "asset_types.py", "org_settings.py", "finding_observations.py",
            "../models/enums.py", "../schemas/import_profile.py"):
        digest.update(name.encode() + b"\0")
        digest.update((root / name).read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


# Source deployments restart processes after changes. Capture once at import,
# never reread mutable source files in the middle of a running import.
PARSER_REVISION = _installed_parser_revision()


def configuration_identity(settings_fingerprint: str) -> str:
    return hashlib.sha256(f"scan-config-v1:{PARSER_REVISION}:{settings_fingerprint}".encode()).hexdigest()
