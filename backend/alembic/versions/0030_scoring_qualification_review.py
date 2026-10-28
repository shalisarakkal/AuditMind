"""Scope-bound operational evidence reviews; scoring activation remains guarded."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("domain_evidence_qualifications", sa.Column("inventory_sha256", sa.String(64)))
    op.add_column("domain_evidence_qualifications", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_qualification_reviewer")))
    op.add_column("domain_evidence_qualifications", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.add_column("domain_evidence_qualifications", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column("domain_evidence_qualifications", sa.Column("review_note", sa.Text()))
    op.add_column("domain_evidence_qualifications", sa.Column("review_attestation", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.drop_constraint("ck_qualification_status", "domain_evidence_qualifications", type_="check")
    op.create_check_constraint("ck_qualification_status", "domain_evidence_qualifications", "status IN ('draft','approved','revoked','conflicting')")
    op.create_check_constraint("ck_qualification_expiry", "domain_evidence_qualifications", "expires_at IS NULL OR (reviewed_at IS NOT NULL AND expires_at > reviewed_at AND expires_at <= reviewed_at + interval '2160 hours')")


def downgrade():
    # Returning to the draft-only API must not strand reviewed rows that the old
    # API cannot edit. Invalidate them and their versions; never retain approval
    # after discarding the metadata required to substantiate it. Audit snapshots
    # are separate rows and remain unchanged.
    op.execute("UPDATE domain_evidence_qualifications SET status='draft', version=version+1 WHERE status IN ('approved','conflicting','revoked')")
    op.drop_constraint("ck_qualification_expiry", "domain_evidence_qualifications", type_="check")
    op.drop_constraint("ck_qualification_status", "domain_evidence_qualifications", type_="check")
    op.create_check_constraint("ck_qualification_status", "domain_evidence_qualifications", "status IN ('draft','approved','revoked')")
    op.drop_constraint("fk_qualification_reviewer", "domain_evidence_qualifications", type_="foreignkey")
    for column in ("review_attestation", "review_note", "expires_at", "reviewed_at", "reviewed_by", "inventory_sha256"):
        op.drop_column("domain_evidence_qualifications", column)
