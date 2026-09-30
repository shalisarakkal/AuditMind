from pydantic import BaseModel, Field, field_validator

from app.core.config import AssetExistingStrategy, NessusInfoSeverity
from app.models.enums import Domain
from app.services.asset_types import check_alias_targets


class IngestionSettingsRead(BaseModel):
    """The settings in effect for an org, and which of them the org overrides
    (the rest are the global .env defaults)."""

    import_partial_success: bool
    asset_existing_strategy: AssetExistingStrategy
    nessus_info_severity: NessusInfoSeverity
    nessus_domain_map: dict[str, Domain]
    nessus_default_domain: Domain
    overridden: list[str]
    # The org's own plugin-family additions (already merged into
    # nessus_domain_map); what an admin edits.
    nessus_domain_map_override: dict[str, Domain]
    # Asset type name -> category: built-in, .env, then the org's own names.
    asset_type_aliases: dict[str, str]
    asset_type_aliases_override: dict[str, str]
    archive_retention_days: int
    event_retention_days: int


class IngestionSettingsUpdate(BaseModel):
    """PATCH body. Omit a field to leave it alone, send a value to override it,
    or send null to clear the override (back to the global default).
    nessus_domain_map and asset_type_aliases replace the org's previous map
    override wholesale; they are merged over the built-in and .env maps when
    resolved."""

    import_partial_success: bool | None = None
    asset_existing_strategy: AssetExistingStrategy | None = None
    nessus_info_severity: NessusInfoSeverity | None = None
    nessus_domain_map: dict[str, Domain] | None = None
    nessus_default_domain: Domain | None = None
    asset_type_aliases: dict[str, str] | None = None
    archive_retention_days: int | None = Field(None, ge=1, le=3650)
    event_retention_days: int | None = Field(None, ge=30, le=3650)

    @field_validator("asset_type_aliases")
    @classmethod
    def _check_type_aliases(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        return None if value is None else check_alias_targets({k.strip(): v for k, v in value.items()})
