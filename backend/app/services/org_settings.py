"""Effective ingestion settings for an org: the org's override where it has
one, else the global .env default.

Only overridden keys are stored (organizations.ingestion_overrides), so a
changed .env default still applies to every org that hasn't overridden it.
"""

from dataclasses import dataclass

from app.core.config import AssetExistingStrategy, NessusInfoSeverity, settings
from app.models.enums import Domain
from app.models.organization import Organization
from app.services.nessus_parser import DEFAULT_NESSUS_DOMAIN_MAP

OVERRIDABLE_KEYS = (
    "import_partial_success",
    "asset_existing_strategy",
    "nessus_info_severity",
    "nessus_domain_map",
    "nessus_default_domain",
)


@dataclass(frozen=True)
class IngestionSettings:
    import_partial_success: bool
    asset_existing_strategy: AssetExistingStrategy
    nessus_info_severity: NessusInfoSeverity
    # Plugin family -> domain. Built-in map, then .env additions, then the
    # org's own additions (later entries win).
    nessus_domain_map: dict[str, Domain]
    nessus_default_domain: Domain
    overridden: frozenset[str]


def resolve_ingestion_settings(org: Organization) -> IngestionSettings:
    overrides = org.ingestion_overrides or {}

    domain_map = {
        **DEFAULT_NESSUS_DOMAIN_MAP,
        **settings.NESSUS_DOMAIN_MAP,
        **{family: Domain(domain) for family, domain in overrides.get("nessus_domain_map", {}).items()},
    }
    return IngestionSettings(
        import_partial_success=overrides.get("import_partial_success", settings.IMPORT_PARTIAL_SUCCESS),
        asset_existing_strategy=overrides.get("asset_existing_strategy", settings.ASSET_EXISTING_STRATEGY),
        nessus_info_severity=overrides.get("nessus_info_severity", settings.NESSUS_INFO_SEVERITY),
        nessus_domain_map=domain_map,
        nessus_default_domain=Domain(overrides.get("nessus_default_domain", settings.NESSUS_DEFAULT_DOMAIN)),
        overridden=frozenset(key for key in overrides if key in OVERRIDABLE_KEYS),
    )


def apply_overrides(org: Organization, changes: dict) -> None:
    """Apply a PATCH: a value sets that override, None clears it (back to the
    global default). Keys not in `changes` are left alone. The nessus_domain_map
    override is replaced wholesale, not merged with the previous one."""
    overrides = dict(org.ingestion_overrides or {})
    for key, value in changes.items():
        if value is None:
            overrides.pop(key, None)
        else:
            overrides[key] = value
    org.ingestion_overrides = overrides
