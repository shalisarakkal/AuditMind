from pydantic import BaseModel

from app.core.config import AssetExistingStrategy, NessusInfoSeverity
from app.models.enums import Domain


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


class IngestionSettingsUpdate(BaseModel):
    """PATCH body. Omit a field to leave it alone, send a value to override it,
    or send null to clear the override (back to the global default).
    nessus_domain_map replaces the org's previous map override wholesale; it is
    merged over the built-in and .env maps when resolved."""

    import_partial_success: bool | None = None
    asset_existing_strategy: AssetExistingStrategy | None = None
    nessus_info_severity: NessusInfoSeverity | None = None
    nessus_domain_map: dict[str, Domain] | None = None
    nessus_default_domain: Domain | None = None
