"""Persist reviewed absence candidates without changing finding state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("finding_absence_review_batches",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_key", sa.String(64), nullable=False),
        sa.Column("baseline_scan_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("current_scan_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_version", sa.Integer(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("context", pg.JSONB(), nullable=False),
        sa.Column("actor_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "batch_key", name="uq_finding_absence_review_batch_key"))
    op.create_index("ix_finding_absence_review_batches_org_created",
        "finding_absence_review_batches", ["org_id", "created_at", "id"])

    op.create_table("finding_absence_review_items",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", pg.UUID(as_uuid=True), sa.ForeignKey("finding_absence_review_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_observation_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("batch_id", "finding_id", name="uq_finding_absence_review_candidate"))
    op.create_index("ix_finding_absence_review_items_org_batch",
        "finding_absence_review_items", ["org_id", "batch_id", "id"])
    op.create_index("ix_finding_absence_review_items_org_created",
        "finding_absence_review_items", ["org_id", "created_at", "id"])

    op.create_table("finding_absence_review_decisions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("finding_absence_review_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("actor_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("item_id", "version", name="uq_finding_absence_review_decision_version"),
        sa.CheckConstraint("version > 0", name="ck_finding_absence_review_decision_version"),
        sa.CheckConstraint("state IN ('kept_active','reopened')", name="ck_finding_absence_review_decision_state"))
    op.create_index("ix_finding_absence_review_decisions_org_item",
        "finding_absence_review_decisions", ["org_id", "item_id", "version"])

    for table in ("batches", "decisions"):
        op.create_index(f"ix_finding_absence_review_{table}_actor",
            f"finding_absence_review_{table}", ["actor_id"])


def downgrade():
    op.drop_table("finding_absence_review_decisions")
    op.drop_table("finding_absence_review_items")
    op.drop_table("finding_absence_review_batches")
