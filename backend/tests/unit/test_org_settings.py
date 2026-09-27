from app.core.config import settings
from app.models.enums import Domain
from app.models.organization import Organization
from app.services.nessus_parser import DEFAULT_NESSUS_DOMAIN_MAP
from app.services.org_settings import apply_overrides, resolve_ingestion_settings


def _org(**overrides) -> Organization:
    return Organization(name="Acme", ingestion_overrides=overrides)


def test_no_overrides_uses_global_defaults():
    effective = resolve_ingestion_settings(_org())
    assert effective.import_partial_success is settings.IMPORT_PARTIAL_SUCCESS
    assert effective.asset_existing_strategy == settings.ASSET_EXISTING_STRATEGY
    assert effective.nessus_info_severity == settings.NESSUS_INFO_SEVERITY
    assert effective.nessus_default_domain == settings.NESSUS_DEFAULT_DOMAIN
    assert effective.nessus_domain_map == DEFAULT_NESSUS_DOMAIN_MAP
    assert effective.overridden == frozenset()


def test_org_override_wins_and_is_reported():
    effective = resolve_ingestion_settings(
        _org(import_partial_success=False, asset_existing_strategy="skip", nessus_default_domain="compliance_alignment")
    )
    assert effective.import_partial_success is False
    assert effective.asset_existing_strategy == "skip"
    assert effective.nessus_default_domain == Domain.compliance_alignment
    assert effective.nessus_info_severity == settings.NESSUS_INFO_SEVERITY
    assert effective.overridden == {"import_partial_success", "asset_existing_strategy", "nessus_default_domain"}


def test_changed_env_default_applies_to_orgs_without_override(monkeypatch):
    monkeypatch.setattr(settings, "ASSET_EXISTING_STRATEGY", "duplicate")
    assert resolve_ingestion_settings(_org()).asset_existing_strategy == "duplicate"
    assert resolve_ingestion_settings(_org(asset_existing_strategy="skip")).asset_existing_strategy == "skip"


def test_domain_maps_layer_builtin_then_env_then_org(monkeypatch):
    monkeypatch.setattr(
        settings, "NESSUS_DOMAIN_MAP", {"Web Servers": Domain.network_config, "Firewalls": Domain.monitoring_detection}
    )
    effective = resolve_ingestion_settings(_org(nessus_domain_map={"Web Servers": "incident_response"}))
    domain_map = effective.nessus_domain_map
    assert domain_map["Web Servers"] == Domain.incident_response  # org beats .env
    assert domain_map["Firewalls"] == Domain.monitoring_detection  # .env beats built-in
    assert domain_map["Windows : User management"] == Domain.identity_access  # built-in kept


def test_unknown_stored_keys_are_not_reported_as_overridden():
    assert resolve_ingestion_settings(_org(legacy_key=1)).overridden == frozenset()


def test_apply_overrides_sets_clears_and_replaces():
    org = _org(asset_existing_strategy="skip", nessus_domain_map={"A": "network_config"})
    before = org.ingestion_overrides

    apply_overrides(org, {"asset_existing_strategy": None, "nessus_info_severity": "low", "nessus_domain_map": {"B": "backup_recovery"}})

    assert org.ingestion_overrides == {"nessus_info_severity": "low", "nessus_domain_map": {"B": "backup_recovery"}}
    assert org.ingestion_overrides is not before  # reassigned, so SQLAlchemy tracks the change
    assert before == {"asset_existing_strategy": "skip", "nessus_domain_map": {"A": "network_config"}}


def test_clearing_a_key_that_is_not_set_is_harmless():
    org = _org()
    apply_overrides(org, {"import_partial_success": None})
    assert org.ingestion_overrides == {}
