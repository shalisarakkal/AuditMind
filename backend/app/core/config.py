from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
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
    # Where larger files wait for the background worker (deleted once
    # imported). Relative paths are from the backend folder.
    UPLOAD_DIR: str = "uploads"

    # --- Background worker (python -m app.worker). ---
    # A job the worker runs with no check-in for this long was cut off (the
    # worker stopped): an import is started again once, an archive job
    # carries on.
    WORKER_STALE_SECONDS: int = Field(120, ge=30)
    # How often the worker looks for new jobs when it has none.
    WORKER_POLL_SECONDS: float = Field(2.0, gt=0)
    # The daily auto-purge's jobs wait until no upload or job someone started
    # is waiting; after this long they take their turn by age like any other
    # job, so a busy queue can't put them off for ever.
    AUTO_PURGE_MAX_WAIT_MINUTES: int = Field(60, ge=0)

    # --- Archiving. ---
    # Archive, restore and purge jobs up to this many rows run during the
    # request; larger ones run in the background, shown in the import tracker.
    ARCHIVE_SYNC_MAX_ROWS: int = 20_000
    # True: the background worker purges archived items past their retention,
    # and Activity events past theirs, once a day (and shortly after it
    # starts). False: run scripts/purge_expired.py from Task Scheduler or
    # cron instead.
    ARCHIVE_AUTO_PURGE: bool = True

    # --- Activity (the event log). ---
    # An org with more events than this (a flood of failed logins, say) has
    # its oldest Info events deleted, then its oldest failed sign-ins, and its
    # admins warned in Activity; other Warning events and Critical ones are
    # always kept for the full retention.
    EVENT_SAFETY_NET_ROWS: int = Field(1_000_000, ge=1000)

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
    # Days an archived item is kept before it's purged for good. Each org can
    # override it (Settings page).
    ARCHIVE_RETENTION_DAYS: int = Field(180, ge=1)
    # Days Activity events are kept. Each org can override it (Settings page).
    EVENT_RETENTION_DAYS: int = Field(365, ge=1)

    @field_validator("ASSET_TYPE_ALIASES")
    @classmethod
    def _check_type_aliases(cls, value: dict[str, str]) -> dict[str, str]:
        return check_alias_targets(value)

    @property
    def upload_dir(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        return path if path.is_absolute() else Path(__file__).resolve().parents[2] / path

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
