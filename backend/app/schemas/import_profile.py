"""Import profile settings (per family) and the import-profiles API shapes.

Each family's params model holds its rule settings, and its defaults *are*
the built-in profile's settings, so there's one source of truth.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import Domain, Severity
from app.services.asset_types import check_alias_targets


class ProfileParams(BaseModel):
    """Settings every profile has."""

    model_config = ConfigDict(extra="forbid")

    # Field -> value used when the file has no value for it (no column mapped,
    # or a blank cell), e.g. {"environment": "production"}.
    default_values: dict[str, str] = {}
    # The profile's own asset type names, layered over the org's list.
    type_aliases: dict[str, str] = {}
    # Keep the file's other columns (ones no field reads) in the asset's
    # details, e.g. a cloud export's Provider and Owner.
    keep_other_columns: bool = False

    @field_validator("default_values")
    @classmethod
    def _strip_defaults(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned = {field.strip(): text.strip() for field, text in value.items()}
        if any(len(text) > 255 for text in cleaned.values()):
            raise ValueError("default values can be at most 255 characters")
        return {field: text for field, text in cleaned.items() if text}

    @field_validator("type_aliases")
    @classmethod
    def _check_aliases(cls, value: dict[str, str]) -> dict[str, str]:
        return check_alias_targets({alias.strip(): target for alias, target in value.items()})


class GenericAssetsParams(ProfileParams):
    pass


class RuleSetting(BaseModel):
    """An event source's rule, as a profile changes it (omitted: the
    rule's own default)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    severity: Severity | None = None


class EventLogParams(ProfileParams):
    """An event log source (Phase 2f part 2): rule key -> its setting. The
    rules and their defaults are the source's (services/event_sources.py)."""

    rules: dict[str, RuleSetting] = {}


class GenericFindingsParams(ProfileParams):
    pass


class EndpointAgentParams(ProfileParams):
    default_values: dict[str, str] = {"type": "workstation", "subtype": "endpoint"}
    keep_other_columns: bool = True
    # ThreatsDetected at or above these -> an Incident Response finding.
    threats_high_at: int = Field(1, ge=1)
    threats_critical_at: int = Field(5, ge=1)
    # LastHeartbeat older than this at import time -> "agent not reporting".
    stale_after_days: int = Field(7, ge=1, le=3650)
    # ComplianceStatus value (any case) -> severity of a Compliance finding.
    compliance_severity: dict[str, Severity] = {"warning": Severity.low, "non-compliant": Severity.medium}
    # ComplianceStatus values that mean "fine": no finding, no warning.
    compliant_values: list[str] = ["compliant"]
    # Read 03/04/2026 as 3 April (day first) instead of 4 March.
    day_first_dates: bool = False

    @model_validator(mode="after")
    def _check(self) -> "EndpointAgentParams":
        if self.threats_critical_at < self.threats_high_at:
            raise ValueError("threats_critical_at must be at least threats_high_at")
        self.compliance_severity = {k.strip().lower(): v for k, v in self.compliance_severity.items() if k.strip()}
        self.compliant_values = [v.strip().lower() for v in self.compliant_values if v.strip()]
        return self


class RiskyPort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=50)
    severity: Severity


class NetworkScanParams(ProfileParams):
    keep_other_columns: bool = True
    # RiskScore (0-10) at or above these -> critical / high / medium; below
    # medium -> low.
    risk_critical_at: float = Field(9.0, ge=0, le=10)
    risk_high_at: float = Field(7.0, ge=0, le=10)
    risk_medium_at: float = Field(4.0, ge=0, le=10)
    # Vulnerabilities values (any case) that mean "nothing found": no finding.
    no_vulnerability_values: list[str] = ["none", "n/a", "na", "null", "-", "no"]
    # Vulnerabilities value (any case) -> domain; others -> Vulnerability Mgmt.
    vulnerability_domains: dict[str, Domain] = {
        "TLS1.0": Domain.network_config,
        "Weak Ciphers": Domain.network_config,
    }
    # Open ports that each raise a Network & Config finding.
    risky_ports: dict[str, RiskyPort] = {
        "23": RiskyPort(label="Telnet", severity=Severity.high),
        "21": RiskyPort(label="FTP", severity=Severity.medium),
        "445": RiskyPort(label="SMB", severity=Severity.medium),
        "3389": RiskyPort(label="RDP", severity=Severity.medium),
        "135": RiskyPort(label="RPC", severity=Severity.medium),
        "161": RiskyPort(label="SNMP", severity=Severity.medium),
    }

    @field_validator("risky_ports")
    @classmethod
    def _check_ports(cls, value: dict[str, RiskyPort]) -> dict[str, RiskyPort]:
        ports = {}
        for port, spec in value.items():
            if not port.strip().isdigit() or not 1 <= int(port) <= 65535:
                raise ValueError(f"{port!r} is not a port number (1-65535)")
            ports[str(int(port))] = spec
        return ports

    @model_validator(mode="after")
    def _check(self) -> "NetworkScanParams":
        if not self.risk_critical_at >= self.risk_high_at >= self.risk_medium_at:
            raise ValueError("risk bands must go critical >= high >= medium")
        self.no_vulnerability_values = [v.strip().lower() for v in self.no_vulnerability_values if v.strip()]
        return self


class CloudInventoryParams(ProfileParams):
    keep_other_columns: bool = True


class DirectoryParams(ProfileParams):
    keep_other_columns: bool = True
    # Account status (any case) that raises an Identity & Access finding.
    disabled_values: list[str] = ["disabled", "inactive", "locked", "false"]
    disabled_severity: Severity = Severity.low
    # Statuses that need no finding; any other status gets a warning.
    ok_values: list[str] = ["active", "enabled", "true", "pending"]
    # No login for longer than this at import time -> a stale-account finding.
    stale_login_days: int = Field(90, ge=1, le=3650)
    stale_severity: Severity = Severity.medium
    day_first_dates: bool = False

    @model_validator(mode="after")
    def _check(self) -> "DirectoryParams":
        self.disabled_values = [v.strip().lower() for v in self.disabled_values if v.strip()]
        self.ok_values = [v.strip().lower() for v in self.ok_values if v.strip()]
        if set(self.disabled_values) & set(self.ok_values):
            raise ValueError("a status can't be both disabled and fine")
        return self


# --- API ----------------------------------------------------------------------


class ProfileField(BaseModel):
    name: str
    label: str
    # Stored in the asset's details rather than a column of its own.
    detail: bool = False


class EventRuleRead(BaseModel):
    """One of an event source's rules, with its defaults."""

    key: str
    title: str
    domain: Domain
    severity: Severity
    # Fewer matching events than this: no finding.
    min_events: int


class ImportProfileRead(BaseModel):
    """A built-in profile (key = its family) or one of the org's own copies
    (key = its id)."""

    key: str
    name: str
    family: str
    family_label: str
    builtin: bool
    creates_assets: bool
    creates_findings: bool
    # The fields this family reads, for the column mapping editor.
    fields: list[ProfileField]
    # An event log: its events are summed up by rules into findings (no
    # assets, and no host column needed); the rules, for the editor.
    events: bool = False
    rules: list[EventRuleRead] = []
    # Field -> column header in the file.
    column_map: dict[str, str]
    params: dict
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ImportProfileCreate(BaseModel):
    """Copy a profile (built-in or the org's own) under a new name, optionally
    with changed column names or settings. Omitted parts are copied as is."""

    name: str = Field(min_length=1, max_length=100)
    copy_from: str
    column_map: dict[str, str] | None = None
    params: dict | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name can't be blank")
        return value.strip()


class ImportProfileUpdate(BaseModel):
    """Omit a part to leave it alone. column_map and params replace the
    previous ones wholesale."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    column_map: dict[str, str] | None = None
    params: dict | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("name can't be blank")
        return value.strip() if value else value

