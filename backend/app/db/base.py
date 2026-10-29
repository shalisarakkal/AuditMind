from app.db.base_class import Base
from app.models.organization import Organization
from app.models.organization_logo import OrganizationLogo
from app.models.scoring_qualification import OrganizationScoringSettings, DomainEvidenceQualification
from app.models.evidence_evaluation import OrganizationEvidenceRevision, EvidenceEvaluation
from app.models.user import User
from app.models.membership import OrgMembership
from app.models.asset import Asset
from app.models.scan import Scan
from app.models.finding import Finding
from app.models.finding_history import FindingHistory
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
