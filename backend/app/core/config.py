from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models.enums import Domain
from app.services.asset_types import check_alias_targets

AssetExistingStrategy = Literal["update", "skip", "duplicate"]
NessusInfoSeverity = Literal["skip", "low"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "AuditMind AI"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = "postgresql+psycopg://auditmind:auditmind@localhost:5432/auditmind"
    TEST_DATABASE_URL: str | None = None

    SECRET_KEY: str = "change-me-to-a-random-secret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    ALGORITHM: str = "HS256"

    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-5"

    CORS_ORIGINS: str = "http://localhost:3000"

    # --- File imports (asset import, findings upload). Global only. ---
    # Files up to this size are processed during the request; larger ones run
    # in the background and are tracked through their scan record.
    IMPORT_SYNC_MAX_BYTES: int = 10 * 1024 * 1024
    # Files over this size are rejected outright (413).
    IMPORT_MAX_BYTES: int = 100 * 1024 * 1024

    # --- Ingestion behaviour. Global defaults; each org can override them
    # (see app/services/org_settings.py). ---
    # True: import the valid rows and report the bad ones.
    # False: any bad row rejects the whole file.
    IMPORT_PARTIAL_SUCCESS: bool = True
    # What to do when an imported asset matches an existing one (by hostname,
    # else IP): update its non-empty fields, skip it, or insert a duplicate.
    ASSET_EXISTING_STRATEGY: AssetExistingStrategy = "update"
    # Nessus severity 0 ("Info") items: skip them, or record them as low.
    NESSUS_INFO_SEVERITY: NessusInfoSeverity = "skip"
    # Extra Nessus plugin-family -> domain mappings, merged over the built-in
    # map. In .env as JSON, e.g. NESSUS_DOMAIN_MAP={"Web Servers": "network_config"}
    NESSUS_DOMAIN_MAP: dict[str, Domain] = {}
    # Domain for plugin families with no mapping.
    NESSUS_DEFAULT_DOMAIN: Domain = Domain.vulnerability_management
    # Extra asset type names -> category, merged over the built-in list (see
    # app/services/asset_types.py). In .env as JSON,
    # e.g. ASSET_TYPE_ALIASES={"hypervisor": "server"}
    ASSET_TYPE_ALIASES: dict[str, str] = {}

    @field_validator("ASSET_TYPE_ALIASES")
    @classmethod
    def _check_type_aliases(cls, value: dict[str, str]) -> dict[str, str]:
        return check_alias_targets(value)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
