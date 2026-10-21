"""Versioned knowledge library and model-specific indexes.

Revision ID: 0020
Revises: 0019
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from pgvector.sqlalchemy import Vector

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def ident():
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True)


def timestamp(name):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def upgrade():
    op.create_table("knowledge_documents", ident(),
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("framework", sa.String(50)), timestamp("created_at"))
    op.create_index("ix_knowledge_documents_org_id", "knowledge_documents", ["org_id"])
    op.create_table("knowledge_versions", ident(),
        sa.Column("document_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False), sa.Column("edition", sa.String(100), nullable=False),
        sa.Column("source", sa.String(1000), nullable=False), sa.Column("content_kind", sa.String(30), nullable=False),
        sa.Column("rights", sa.String(2000), nullable=False), sa.Column("content", sa.Text),
        sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("current", sa.Boolean, nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True)), sa.Column("purged_at", sa.DateTime(timezone=True)),
        timestamp("created_at"), sa.UniqueConstraint("document_id", "number"))
    op.create_index("ix_knowledge_versions_document_id", "knowledge_versions", ["document_id"])
    op.create_table("embedding_profiles", ident(),
        sa.Column("provider", sa.String(30), nullable=False), sa.Column("model", sa.String(255), nullable=False),
        sa.Column("revision", sa.String(100), nullable=False), sa.Column("dimensions", sa.Integer, nullable=False),
        timestamp("created_at"), sa.UniqueConstraint("provider", "model", "revision", "dimensions"))
    op.create_table("knowledge_indexes", ident(),
        sa.Column("version_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", pg.UUID(as_uuid=True), sa.ForeignKey("embedding_profiles.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("publish_version", sa.Boolean, nullable=False),
        sa.Column("error_message", sa.String(1000)), sa.Column("retry_count", sa.Integer, nullable=False),
        sa.Column("started_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        timestamp("created_at"), sa.Column("run_started_at", sa.DateTime(timezone=True)), sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("version_id", "profile_id"))
    for name in ("version_id", "profile_id", "status"):
        op.create_index(f"ix_knowledge_indexes_{name}", "knowledge_indexes", [name])
    op.create_table("knowledge_chunks", ident(),
        sa.Column("index_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False), sa.Column("start_offset", sa.Integer, nullable=False),
        sa.Column("end_offset", sa.Integer, nullable=False), sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("embedding", Vector(), nullable=False),
        sa.UniqueConstraint("index_id", "ordinal"))
    op.create_index("ix_knowledge_chunks_index_id", "knowledge_chunks", ["index_id"])
    op.create_table("knowledge_consents",
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("purpose", sa.String(30), primary_key=True), sa.Column("target", sa.String(500), nullable=False),
        sa.Column("granted", sa.Boolean, nullable=False),
        sa.Column("actor_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")), timestamp("updated_at"))
    op.create_table("report_evidence_uses",
        sa.Column("report_id", pg.UUID(as_uuid=True), sa.ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_versions.id"), primary_key=True))


def downgrade():
    for table in ("report_evidence_uses", "knowledge_consents", "knowledge_chunks", "knowledge_indexes",
                  "embedding_profiles", "knowledge_versions", "knowledge_documents"):
        op.drop_table(table)
