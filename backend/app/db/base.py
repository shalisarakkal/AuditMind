from app.db.base_class import Base
from app.models.dashboard_snapshot import DashboardSnapshot  # noqa: F401
from app.models.list_revision import OrganizationListRevision, OrganizationWorkflowRevision  # noqa: F401
from app.models.organization import Organization
from app.models.organization_logo import OrganizationLogo
from app.models.scoring_qualification import OrganizationScoringSettings, DomainEvidenceQualification
from app.models.evidence_evaluation import OrganizationEvidenceRevision, EvidenceEvaluation
from app.models.user import User
from app.models.membership import OrgMembership
from app.models.asset import Asset
from app.models.scan import Scan
from app.models.finding import Finding
from app.models.finding_verification import OrganizationRiskPolicy, FindingVerification
from app.models.finding_history import FindingHistory
from app.models.finding_observation import FindingObservation
from app.models.finding_identity_binding import IdentityTool, ObservationIdentityBinding
from app.models.finding_canonical import FindingCanonicalDecision
from app.models.finding_consolidation import (FindingConsolidation, FindingConsolidationDecision,
    FindingConsolidationMember, FindingConsolidationDependency, OrganizationConsolidationRevision, OrganizationConsolidationSettings)
from app.models.finding_absence_review import (
    FindingAbsenceReviewBatch, FindingAbsenceReviewDecision, FindingAbsenceReviewItem,
)
from app.models.finding_suppression import (FindingSuppression, FindingSuppressionDecision,
    OrganizationSuppressionRevision, FindingSuppressionReappearance)
from app.models.scan_snapshot import ScanSnapshotDeclaration
from app.models.risk_score import RiskScore
from app.models.report import Report
from app.models.ai_usage import AIUsage
from app.models.document import Document
from app.models.knowledge import (
    KnowledgeDocument, KnowledgeVersion, EmbeddingProfile, KnowledgeIndex,
    KnowledgeChunk, KnowledgeConsent, ReportEvidenceUse,
)
from app.models.import_profile import ImportProfile
from app.models.archive import ArchiveBatch, ArchiveJob, AssetScan
from app.models.event import Event, WorkerStatus
from app.models.session import PasswordHistory, PlatformSetting, UserSession
from app.models.import_staging import ImportStagingChunk, ImportStagingState
from app.models.worker_dispatch import WorkerDispatch
from app.db.evidence_revision import register

register(Base.metadata)
from app.db.list_revision import register as register_lists
register_lists(Base.metadata)
from app.db.workflow_revision import register as register_workflows
register_workflows(Base.metadata)
from app.db.status_scoring_revision import register as register_status_scoring
register_status_scoring(Base.metadata)

from app.db.consolidation_proof import register as register_consolidation_proof
register_consolidation_proof(Base.metadata)

__all__ = [
    "WorkerDispatch",
    "OrganizationEvidenceRevision",
    "EvidenceEvaluation",
    "OrganizationScoringSettings",
    "DomainEvidenceQualification",
    "ImportStagingChunk",
    "ImportStagingState",
    "Base",
    "Organization",
    "User",
    "OrgMembership",
    "Asset",
    "Scan",
    "Finding",
    "FindingHistory",
    "FindingObservation",
    "IdentityTool",
    "ObservationIdentityBinding",
    "FindingCanonicalDecision",
    "FindingConsolidation",
    "FindingConsolidationDecision",
    "FindingConsolidationMember",
    "FindingConsolidationDependency",
    "OrganizationConsolidationRevision",
    "OrganizationConsolidationSettings",
    "FindingAbsenceReviewBatch",
    "FindingAbsenceReviewItem",
    "FindingAbsenceReviewDecision",
    "FindingSuppression",
    "FindingSuppressionDecision",
    "OrganizationSuppressionRevision",
    "FindingSuppressionReappearance",
    "ScanSnapshotDeclaration",
    "RiskScore",
    "Report",
    "Document",
    "ImportProfile",
    "ArchiveBatch",
    "ArchiveJob",
    "AssetScan",
    "Event",
    "WorkerStatus",
    "UserSession",
    "PasswordHistory",
    "PlatformSetting",
]
