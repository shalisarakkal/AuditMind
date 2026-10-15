import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    auditor = "auditor"
    viewer = "viewer"


class Domain(str, enum.Enum):
    identity_access = "identity_access"
    network_config = "network_config"
    vulnerability_management = "vulnerability_management"
    backup_recovery = "backup_recovery"
    monitoring_detection = "monitoring_detection"
    incident_response = "incident_response"
    compliance_alignment = "compliance_alignment"


class Severity(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class RiskTier(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ScanStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ReportStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    generated = "generated"
    failed = "failed"



class ArchiveItemType(str, enum.Enum):
    upload = "upload"
    asset = "asset"
    finding = "finding"


class ArchiveState(str, enum.Enum):
    archiving = "archiving"
    archived = "archived"
    restoring = "restoring"
    restored = "restored"
    purging = "purging"
    purged = "purged"


class ArchiveProgress(str, enum.Enum):
    """An item's archive that hasn't finished: a job is working on it now, or
    one stopped part-way (archive it again to finish)."""

    running = "running"
    stopped = "stopped"


class ArchiveAction(str, enum.Enum):
    archive = "archive"
    restore = "restore"
    purge = "purge"


class Criticality(str, enum.Enum):
    """How much an Activity event matters (PLAN.md, Phase 2d part 3)."""

    info = "info"
    warning = "warning"
    critical = "critical"
