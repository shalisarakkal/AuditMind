from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models.enums import Domain
from app.services.asset_types import check_alias_targets

AssetExistingStrategy = Literal["update", "skip", "duplicate"]
ExactDuplicateFilePolicy = Literal["ask", "skip", "reimport"]
NessusInfoSeverity = Literal["skip", "low"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "AuditMind AI"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = "postgresql+psycopg://auditmind:auditmind@localhost:5432/auditmind"
    TEST_DATABASE_URL: str | None = None

    # Required: the server and worker refuse the default or a short one
    # (check_secret_key below).
    SECRET_KEY: str = "change-me-to-a-random-secret"
    # The sign-in token the app holds in memory; it's renewed through the
    # session cookie, so a short life costs nothing. How long someone stays
    # signed in is the security settings' idle and longest sign-in.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(15, ge=1, le=60)
    ALGORITHM: str = "HS256"

    # --- Sign-in sessions. ---
    # The session cookie is sent over HTTPS only. False for local development
    # over http (backend/.env.example).
    COOKIE_SECURE: bool = True
    # Sign-in attempts allowed from one address a minute, over all accounts.
    # Behind a proxy, run uvicorn with --forwarded-allow-ips=<the proxy's
    # address> so each person's own address is counted (127.0.0.1, the
    # frontend's own proxy in development, is trusted by default).
    LOGIN_RATE_LIMIT_PER_MINUTE: int = Field(20, ge=1)
    # Days a temporary password (set by an admin) can be used to sign in.
    TEMP_PASSWORD_DAYS: int = Field(7, ge=1)
    # A session's last activity is saved at most this often (seconds).
    SESSION_TOUCH_SECONDS: int = Field(60, ge=1)
    # Anyone may sign up, creating an org of their own. Off: only the
    # Sysadmin creates orgs (with their first admin), and admins add people.
    PUBLIC_SIGNUP: bool = False
    # The security settings themselves (idle time, longest sign-in, lockout,
    # password rule) aren't here: the platform defaults are in the database,
    # set by the Sysadmin, over built-in values (services/security_policy.py).

    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-5"
    REPORT_AI_PROVIDER: Literal["anthropic", "openrouter"] = "anthropic"
    OPENROUTER_INFERENCE_ENABLED: bool = False
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = Field("", max_length=160)
    # Explicit operator-approved price ceilings, USD per million tokens.
    OPENROUTER_INPUT_USD_PER_MILLION: float | None = Field(None, gt=0, allow_inf_nan=False)
    OPENROUTER_OUTPUT_USD_PER_MILLION: float | None = Field(None, gt=0, allow_inf_nan=False)
    # Exposes a local-only rule-based report workflow for UI/download testing.
    RULE_BASED_TEST_REPORTS_ENABLED: bool = False
    # How long one Claude attempt may take (seconds); application retries
    # transient failures within its budget, with SDK retries disabled.
    CLAUDE_TIMEOUT_SECONDS: float = Field(60.0, gt=0)
    CLAUDE_MAX_RETRIES: int = Field(3, ge=1, le=5)
    CLAUDE_ORG_CALLS_PER_HOUR: int = Field(100, ge=1)
    CLAUDE_ORG_MAX_COST_PER_HOUR_USD: float = Field(50.0, gt=0)
    # Minimum per-attempt reservation. Confirmed SDK token usage replaces
    # reservations with estimated cost; unknown outcomes keep their reservation.
    CLAUDE_ATTEMPT_RESERVE_USD: float = Field(1.0, gt=0)
    # Finished reports only; active jobs are never removed by housekeeping.
    REPORT_RETENTION_DAYS: int = Field(365, ge=1)
    REPORT_AI_MAX_INPUT_BYTES: int = Field(65536, ge=16384, le=262144)
    REPORT_EVIDENCE_V3_ENABLED: bool = False
    REPORT_EVIDENCE_QUALIFICATIONS_FILE: str = ''
    REPORT_AI_FINDING_TEXT_BYTES: int = Field(2048, ge=128, le=8192)

    # --- Embeddings & RAG Knowledge Base ---
    OPENAI_API_KEY: str = ""
    VOYAGE_API_KEY: str = ""
    # "local_deterministic", "openai", or "voyage"
    EMBEDDING_PROVIDER: str = "local_deterministic"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Where people open the app: sign-in and session renewal are refused

    # from pages anywhere else (and CORS allows these to call the API).
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- File imports (asset import, findings upload). Global only. ---
    # Files up to this size are processed during the request; larger ones run
    # in the background and are tracked through their scan record.
    IMPORT_SYNC_MAX_BYTES: int = 10 * 1024 * 1024
    # Files over this size are rejected outright (413).
    IMPORT_MAX_BYTES: int = 1024 * 1024 * 1024
    # Where larger files wait for the background worker (deleted once
    # imported). Relative paths are from the backend folder.
    UPLOAD_DIR: str = "uploads"
    # A large upload that failed for a reason other than its content (cut
    # off too often, an unexpected error) keeps its file this many days, so it
    # can be retried without uploading it again; then the worker deletes it.
    UPLOAD_KEEP_FAILED_DAYS: int = Field(7, ge=0)

    # --- Background worker (python -m app.worker). ---
    # A job the worker runs with no check-in for this long was cut off (the
    # worker stopped): it carries on from where it got to (an import from
    # its last staged chunk), up to 3 times.
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
    EXACT_DUPLICATE_FILE_POLICY: ExactDuplicateFilePolicy = "ask"
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

DEFAULT_SECRET_KEY = "change-me-to-a-random-secret"
SECRET_KEY_MIN_LENGTH = 32


def check_secret_key(key: str) -> None:
    """Refuse to run with the built-in key, or one short enough to guess: it
    signs every login token, so anyone who knows it could forge one. Checked
    when the web server and the background worker start."""
    if key == DEFAULT_SECRET_KEY or len(key) < SECRET_KEY_MIN_LENGTH:
        raise RuntimeError(
            f"SECRET_KEY is the built-in default or shorter than {SECRET_KEY_MIN_LENGTH} characters. "
            "Set a long random one in backend/.env, e.g. from: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))" '
            "(a new key signs everyone out)"
        )
