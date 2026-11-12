"""Retained suppression, visibility fences and reappearance review."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("finding_suppressions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("identity_version", sa.String(50), nullable=False),
        sa.Column("candidate_key", sa.String(100), nullable=False),
        sa.Column("source_fingerprint", sa.String(64)),
        sa.Column("label", sa.String(500), nullable=False, server_default=""),
        sa.Column("reappearance_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("identity", pg.JSONB(), nullable=False),
        sa.Column("finding_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "identity_version", "candidate_key", name="uq_finding_suppression_identity"),
        sa.UniqueConstraint("org_id", "id", name="uq_finding_suppression_owner"),
        sa.CheckConstraint("version > 0", name="ck_finding_suppression_version"),
        sa.CheckConstraint("state IN ('suppressed','cleared')", name="ck_finding_suppression_state"))
    op.create_index("ix_finding_suppressions_source", "finding_suppressions", ["org_id", "source_fingerprint", "state"])
    op.create_index("ix_finding_suppressions_org_state_page", "finding_suppressions", ["org_id", "state", "created_at", "id"])
    op.create_table("finding_suppression_decisions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("suppression_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("context", pg.JSONB(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("actor_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "suppression_id"], ["finding_suppressions.org_id", "finding_suppressions.id"], ondelete="CASCADE", name="fk_suppression_decision_owner"),
        sa.UniqueConstraint("org_id", "request_id", name="uq_suppression_decision_request"),
        sa.UniqueConstraint("suppression_id", "version", name="uq_suppression_decision_version"),
        sa.CheckConstraint("version > 0", name="ck_suppression_decision_version"),
        sa.CheckConstraint("state IN ('suppressed','cleared')", name="ck_suppression_decision_state"),
        sa.CheckConstraint("length(btrim(rationale)) BETWEEN 1 AND 2000", name="ck_suppression_decision_rationale"))
    op.create_index("ix_suppression_decisions_org_history", "finding_suppression_decisions", ["org_id", "suppression_id", "version"])
    op.create_index("ix_suppression_decisions_actor", "finding_suppression_decisions", ["actor_id"])

    op.create_table("organization_suppression_revisions",
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_table("finding_suppression_reappearances",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("suppression_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("scan_id", pg.UUID(as_uuid=True)),
        sa.Column("filename", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "suppression_id"], ["finding_suppressions.org_id", "finding_suppressions.id"], ondelete="CASCADE", name="fk_suppression_reappearance_owner"),
        sa.UniqueConstraint("org_id", "suppression_id", "observation_id", name="uq_suppression_reappearance"))
    op.create_index("ix_suppression_reappearance_history", "finding_suppression_reappearances", ["org_id", "suppression_id", "created_at", "id"])
    op.add_column("findings", sa.Column("suppression_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key("fk_findings_suppression", "findings", "finding_suppressions", ["suppression_id"], ["id"], deferrable=True, initially="DEFERRED")
    op.add_column("findings", sa.Column("suppression_history_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key("fk_findings_suppression_history", "findings", "finding_suppressions", ["suppression_history_id"], ["id"], deferrable=True, initially="DEFERRED")
    _indexes(True)


def downgrade():
    _indexes(False)
    op.drop_constraint("fk_findings_suppression_history", "findings", type_="foreignkey")
    op.drop_column("findings", "suppression_history_id")
    op.drop_constraint("fk_findings_suppression", "findings", type_="foreignkey")
    op.drop_column("findings", "suppression_id")
    op.drop_table("finding_suppression_reappearances")
    op.drop_table("organization_suppression_revisions")
    op.drop_table("finding_suppression_decisions")
    op.drop_table("finding_suppressions")


# Frozen definitions: future model changes must not rewrite this migration.
_OLD_INDEXES = {'ix_findings_active_assignee': 'CREATE INDEX ix_findings_active_assignee ON findings '
                                '(assignee_id) WHERE archived_at IS NULL',
 'ix_findings_active_assignee_id_group_page': 'CREATE INDEX '
                                              'ix_findings_active_assignee_id_group_page ON '
                                              'findings (org_id, assignee_id, severity, created_at '
                                              'DESC NULLS LAST, id) WHERE archived_at IS NULL',
 'ix_findings_active_category_asc_page': 'CREATE INDEX ix_findings_active_category_asc_page ON '
                                         'findings (org_id, lower(category) ASC NULLS LAST, (\n'
                                         'CASE\n'
                                         "    WHEN severity::text = 'critical'::text THEN 0\n"
                                         "    WHEN severity::text = 'high'::text THEN 1\n"
                                         "    WHEN severity::text = 'medium'::text THEN 2\n"
                                         "    WHEN severity::text = 'low'::text THEN 3\n"
                                         '    ELSE NULL::integer\n'
                                         'END), created_at DESC NULLS LAST, id) WHERE archived_at '
                                         'IS NULL',
 'ix_findings_active_category_desc_page': 'CREATE INDEX ix_findings_active_category_desc_page ON '
                                          'findings (org_id, lower(category) DESC NULLS LAST, (\n'
                                          'CASE\n'
                                          "    WHEN severity::text = 'critical'::text THEN 0\n"
                                          "    WHEN severity::text = 'high'::text THEN 1\n"
                                          "    WHEN severity::text = 'medium'::text THEN 2\n"
                                          "    WHEN severity::text = 'low'::text THEN 3\n"
                                          '    ELSE NULL::integer\n'
                                          'END), created_at DESC NULLS LAST, id) WHERE archived_at '
                                          'IS NULL',
 'ix_findings_active_created_page': 'CREATE INDEX ix_findings_active_created_page ON findings '
                                    '(org_id, created_at, id) WHERE archived_at IS NULL',
 'ix_findings_active_domain_page': 'CREATE INDEX ix_findings_active_domain_page ON findings '
                                   '(org_id, domain, (\n'
                                   'CASE\n'
                                   "    WHEN severity::text = 'critical'::text THEN 0\n"
                                   "    WHEN severity::text = 'high'::text THEN 1\n"
                                   "    WHEN severity::text = 'medium'::text THEN 2\n"
                                   "    WHEN severity::text = 'low'::text THEN 3\n"
                                   '    ELSE NULL::integer\n'
                                   'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                   'NULL',
 'ix_findings_active_due_presence': 'CREATE INDEX ix_findings_active_due_presence ON findings '
                                    '(org_id) WHERE archived_at IS NULL AND (due_date IS NOT NULL '
                                    'OR due_expires_at IS NOT NULL)',
 'ix_findings_active_due_search': 'CREATE INDEX ix_findings_active_due_search ON findings (org_id) '
                                  'WHERE archived_at IS NULL AND due_date IS NOT NULL',
 'ix_findings_active_long_text': 'CREATE INDEX ix_findings_active_long_text ON findings (org_id) '
                                 'WHERE archived_at IS NULL AND '
                                 'COALESCE(octet_length(lower(COALESCE(description, '
                                 'category::text))), 0) > 1024',
 'ix_findings_active_org_assignee_id': 'CREATE INDEX ix_findings_active_org_assignee_id ON '
                                       'findings (org_id, assignee_id) WHERE archived_at IS NULL',
 'ix_findings_active_org_domain_severity': 'CREATE INDEX ix_findings_active_org_domain_severity ON '
                                           'findings (org_id, domain, severity) WHERE archived_at '
                                           'IS NULL',
 'ix_findings_active_org_scan_id': 'CREATE INDEX ix_findings_active_org_scan_id ON findings '
                                   '(org_id, scan_id) WHERE archived_at IS NULL',
 'ix_findings_active_org_source': 'CREATE INDEX ix_findings_active_org_source ON findings (org_id, '
                                  'source) WHERE archived_at IS NULL',
 'ix_findings_active_org_workflow_status': 'CREATE INDEX ix_findings_active_org_workflow_status ON '
                                           'findings (org_id, workflow_status) WHERE archived_at '
                                           'IS NULL',
 'ix_findings_active_review_presence': 'CREATE INDEX ix_findings_active_review_presence ON '
                                       'findings (org_id) WHERE archived_at IS NULL AND '
                                       '(risk_review_date IS NOT NULL OR risk_review_expires_at IS '
                                       'NOT NULL)',
 'ix_findings_active_review_search': 'CREATE INDEX ix_findings_active_review_search ON findings '
                                     '(org_id) WHERE archived_at IS NULL AND risk_review_date IS '
                                     'NOT NULL',
 'ix_findings_active_severity_page': 'CREATE INDEX ix_findings_active_severity_page ON findings '
                                     '(org_id, (\n'
                                     'CASE\n'
                                     "    WHEN severity::text = 'critical'::text THEN 0\n"
                                     "    WHEN severity::text = 'high'::text THEN 1\n"
                                     "    WHEN severity::text = 'medium'::text THEN 2\n"
                                     "    WHEN severity::text = 'low'::text THEN 3\n"
                                     '    ELSE NULL::integer\n'
                                     'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                     'NULL',
 'ix_findings_active_source_asc_page': 'CREATE INDEX ix_findings_active_source_asc_page ON '
                                       'findings (org_id, lower(source) ASC NULLS LAST, (\n'
                                       'CASE\n'
                                       "    WHEN severity::text = 'critical'::text THEN 0\n"
                                       "    WHEN severity::text = 'high'::text THEN 1\n"
                                       "    WHEN severity::text = 'medium'::text THEN 2\n"
                                       "    WHEN severity::text = 'low'::text THEN 3\n"
                                       '    ELSE NULL::integer\n'
                                       'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                       'NULL',
 'ix_findings_active_source_desc_page': 'CREATE INDEX ix_findings_active_source_desc_page ON '
                                        'findings (org_id, lower(source) DESC NULLS LAST, (\n'
                                        'CASE\n'
                                        "    WHEN severity::text = 'critical'::text THEN 0\n"
                                        "    WHEN severity::text = 'high'::text THEN 1\n"
                                        "    WHEN severity::text = 'medium'::text THEN 2\n"
                                        "    WHEN severity::text = 'low'::text THEN 3\n"
                                        '    ELSE NULL::integer\n'
                                        'END), created_at DESC NULLS LAST, id) WHERE archived_at '
                                        'IS NULL',
 'ix_findings_active_text_asc_page': 'CREATE INDEX ix_findings_active_text_asc_page ON findings '
                                     '(org_id, lower(COALESCE(description, category::text)) ASC '
                                     'NULLS LAST, (\n'
                                     'CASE\n'
                                     "    WHEN severity::text = 'critical'::text THEN 0\n"
                                     "    WHEN severity::text = 'high'::text THEN 1\n"
                                     "    WHEN severity::text = 'medium'::text THEN 2\n"
                                     "    WHEN severity::text = 'low'::text THEN 3\n"
                                     '    ELSE NULL::integer\n'
                                     'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                     'NULL AND COALESCE(octet_length(lower(COALESCE(description, '
                                     'category::text))), 0) <= 1024',
 'ix_findings_active_text_desc_page': 'CREATE INDEX ix_findings_active_text_desc_page ON findings '
                                      '(org_id, lower(COALESCE(description, category::text)) DESC '
                                      'NULLS LAST, (\n'
                                      'CASE\n'
                                      "    WHEN severity::text = 'critical'::text THEN 0\n"
                                      "    WHEN severity::text = 'high'::text THEN 1\n"
                                      "    WHEN severity::text = 'medium'::text THEN 2\n"
                                      "    WHEN severity::text = 'low'::text THEN 3\n"
                                      '    ELSE NULL::integer\n'
                                      'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                      'NULL AND COALESCE(octet_length(lower(COALESCE(description, '
                                      'category::text))), 0) <= 1024',
 'ix_findings_active_workflow_status_group_page': 'CREATE INDEX '
                                                  'ix_findings_active_workflow_status_group_page '
                                                  'ON findings (org_id, workflow_status, severity, '
                                                  'created_at DESC NULLS LAST, id) WHERE '
                                                  'archived_at IS NULL',
 'ix_findings_archive_batch': 'CREATE INDEX ix_findings_archive_batch ON findings '
                              '(archive_batch_id) WHERE archive_batch_id IS NOT NULL',
 'ix_findings_category_trgm': 'CREATE INDEX ix_findings_category_trgm ON findings USING gin '
                              '(category gin_trgm_ops) WHERE archived_at IS NULL',
 'ix_findings_description_trgm': 'CREATE INDEX ix_findings_description_trgm ON findings USING gin '
                                 '(description gin_trgm_ops) WHERE archived_at IS NULL',
 'ix_findings_org_created': 'CREATE INDEX ix_findings_org_created ON findings (org_id, created_at) '
                            'WHERE archived_at IS NULL',
 'ix_findings_org_severity_created': 'CREATE INDEX ix_findings_org_severity_created ON findings '
                                     '(org_id, severity, created_at) WHERE archived_at IS NULL',
 'ix_findings_risk_verified': 'CREATE INDEX ix_findings_risk_verified ON findings (org_id, domain, '
                              'severity, risk_verification_expires_at) WHERE archived_at IS NULL '
                              "AND risk_verification_state='approved'",
 'ix_findings_source_trgm': 'CREATE INDEX ix_findings_source_trgm ON findings USING gin (source '
                            'gin_trgm_ops) WHERE archived_at IS NULL'}
_NEW_INDEXES = {'ix_findings_active_assignee': 'CREATE INDEX ix_findings_active_assignee ON findings '
                                '(assignee_id) WHERE archived_at IS NULL AND suppression_id IS '
                                'NULL',
 'ix_findings_active_assignee_id_group_page': 'CREATE INDEX '
                                              'ix_findings_active_assignee_id_group_page ON '
                                              'findings (org_id, assignee_id, severity, created_at '
                                              'DESC NULLS LAST, id) WHERE archived_at IS NULL AND '
                                              'suppression_id IS NULL',
 'ix_findings_active_category_asc_page': 'CREATE INDEX ix_findings_active_category_asc_page ON '
                                         'findings (org_id, lower(category) ASC NULLS LAST, (\n'
                                         'CASE\n'
                                         "    WHEN severity::text = 'critical'::text THEN 0\n"
                                         "    WHEN severity::text = 'high'::text THEN 1\n"
                                         "    WHEN severity::text = 'medium'::text THEN 2\n"
                                         "    WHEN severity::text = 'low'::text THEN 3\n"
                                         '    ELSE NULL::integer\n'
                                         'END), created_at DESC NULLS LAST, id) WHERE archived_at '
                                         'IS NULL AND suppression_id IS NULL',
 'ix_findings_active_category_desc_page': 'CREATE INDEX ix_findings_active_category_desc_page ON '
                                          'findings (org_id, lower(category) DESC NULLS LAST, (\n'
                                          'CASE\n'
                                          "    WHEN severity::text = 'critical'::text THEN 0\n"
                                          "    WHEN severity::text = 'high'::text THEN 1\n"
                                          "    WHEN severity::text = 'medium'::text THEN 2\n"
                                          "    WHEN severity::text = 'low'::text THEN 3\n"
                                          '    ELSE NULL::integer\n'
                                          'END), created_at DESC NULLS LAST, id) WHERE archived_at '
                                          'IS NULL AND suppression_id IS NULL',
 'ix_findings_active_created_page': 'CREATE INDEX ix_findings_active_created_page ON findings '
                                    '(org_id, created_at, id) WHERE archived_at IS NULL AND '
                                    'suppression_id IS NULL',
 'ix_findings_active_domain_page': 'CREATE INDEX ix_findings_active_domain_page ON findings '
                                   '(org_id, domain, (\n'
                                   'CASE\n'
                                   "    WHEN severity::text = 'critical'::text THEN 0\n"
                                   "    WHEN severity::text = 'high'::text THEN 1\n"
                                   "    WHEN severity::text = 'medium'::text THEN 2\n"
                                   "    WHEN severity::text = 'low'::text THEN 3\n"
                                   '    ELSE NULL::integer\n'
                                   'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                   'NULL AND suppression_id IS NULL',
 'ix_findings_active_due_presence': 'CREATE INDEX ix_findings_active_due_presence ON findings '
                                    '(org_id) WHERE archived_at IS NULL AND suppression_id IS NULL '
                                    'AND (due_date IS NOT NULL OR due_expires_at IS NOT NULL)',
 'ix_findings_active_due_search': 'CREATE INDEX ix_findings_active_due_search ON findings (org_id) '
                                  'WHERE archived_at IS NULL AND suppression_id IS NULL AND '
                                  'due_date IS NOT NULL',
 'ix_findings_active_long_text': 'CREATE INDEX ix_findings_active_long_text ON findings (org_id) '
                                 'WHERE archived_at IS NULL AND '
                                 'COALESCE(octet_length(lower(COALESCE(description, '
                                 'category::text))), 0) > 1024 AND suppression_id IS NULL',
 'ix_findings_active_org_assignee_id': 'CREATE INDEX ix_findings_active_org_assignee_id ON '
                                       'findings (org_id, assignee_id) WHERE archived_at IS NULL '
                                       'AND suppression_id IS NULL',
 'ix_findings_active_org_domain_severity': 'CREATE INDEX ix_findings_active_org_domain_severity ON '
                                           'findings (org_id, domain, severity) WHERE archived_at '
                                           'IS NULL AND suppression_id IS NULL',
 'ix_findings_active_org_scan_id': 'CREATE INDEX ix_findings_active_org_scan_id ON findings '
                                   '(org_id, scan_id) WHERE archived_at IS NULL AND suppression_id '
                                   'IS NULL',
 'ix_findings_active_org_source': 'CREATE INDEX ix_findings_active_org_source ON findings (org_id, '
                                  'source) WHERE archived_at IS NULL AND suppression_id IS NULL',
 'ix_findings_active_org_workflow_status': 'CREATE INDEX ix_findings_active_org_workflow_status ON '
                                           'findings (org_id, workflow_status) WHERE archived_at '
                                           'IS NULL AND suppression_id IS NULL',
 'ix_findings_active_review_presence': 'CREATE INDEX ix_findings_active_review_presence ON '
                                       'findings (org_id) WHERE archived_at IS NULL AND '
                                       'suppression_id IS NULL AND (risk_review_date IS NOT NULL '
                                       'OR risk_review_expires_at IS NOT NULL)',
 'ix_findings_active_review_search': 'CREATE INDEX ix_findings_active_review_search ON findings '
                                     '(org_id) WHERE archived_at IS NULL AND suppression_id IS '
                                     'NULL AND risk_review_date IS NOT NULL',
 'ix_findings_active_severity_page': 'CREATE INDEX ix_findings_active_severity_page ON findings '
                                     '(org_id, (\n'
                                     'CASE\n'
                                     "    WHEN severity::text = 'critical'::text THEN 0\n"
                                     "    WHEN severity::text = 'high'::text THEN 1\n"
                                     "    WHEN severity::text = 'medium'::text THEN 2\n"
                                     "    WHEN severity::text = 'low'::text THEN 3\n"
                                     '    ELSE NULL::integer\n'
                                     'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                     'NULL AND suppression_id IS NULL',
 'ix_findings_active_source_asc_page': 'CREATE INDEX ix_findings_active_source_asc_page ON '
                                       'findings (org_id, lower(source) ASC NULLS LAST, (\n'
                                       'CASE\n'
                                       "    WHEN severity::text = 'critical'::text THEN 0\n"
                                       "    WHEN severity::text = 'high'::text THEN 1\n"
                                       "    WHEN severity::text = 'medium'::text THEN 2\n"
                                       "    WHEN severity::text = 'low'::text THEN 3\n"
                                       '    ELSE NULL::integer\n'
                                       'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                       'NULL AND suppression_id IS NULL',
 'ix_findings_active_source_desc_page': 'CREATE INDEX ix_findings_active_source_desc_page ON '
                                        'findings (org_id, lower(source) DESC NULLS LAST, (\n'
                                        'CASE\n'
                                        "    WHEN severity::text = 'critical'::text THEN 0\n"
                                        "    WHEN severity::text = 'high'::text THEN 1\n"
                                        "    WHEN severity::text = 'medium'::text THEN 2\n"
                                        "    WHEN severity::text = 'low'::text THEN 3\n"
                                        '    ELSE NULL::integer\n'
                                        'END), created_at DESC NULLS LAST, id) WHERE archived_at '
                                        'IS NULL AND suppression_id IS NULL',
 'ix_findings_active_text_asc_page': 'CREATE INDEX ix_findings_active_text_asc_page ON findings '
                                     '(org_id, lower(COALESCE(description, category::text)) ASC '
                                     'NULLS LAST, (\n'
                                     'CASE\n'
                                     "    WHEN severity::text = 'critical'::text THEN 0\n"
                                     "    WHEN severity::text = 'high'::text THEN 1\n"
                                     "    WHEN severity::text = 'medium'::text THEN 2\n"
                                     "    WHEN severity::text = 'low'::text THEN 3\n"
                                     '    ELSE NULL::integer\n'
                                     'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                     'NULL AND COALESCE(octet_length(lower(COALESCE(description, '
                                     'category::text))), 0) <= 1024 AND suppression_id IS NULL',
 'ix_findings_active_text_desc_page': 'CREATE INDEX ix_findings_active_text_desc_page ON findings '
                                      '(org_id, lower(COALESCE(description, category::text)) DESC '
                                      'NULLS LAST, (\n'
                                      'CASE\n'
                                      "    WHEN severity::text = 'critical'::text THEN 0\n"
                                      "    WHEN severity::text = 'high'::text THEN 1\n"
                                      "    WHEN severity::text = 'medium'::text THEN 2\n"
                                      "    WHEN severity::text = 'low'::text THEN 3\n"
                                      '    ELSE NULL::integer\n'
                                      'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                      'NULL AND COALESCE(octet_length(lower(COALESCE(description, '
                                      'category::text))), 0) <= 1024 AND suppression_id IS NULL',
 'ix_findings_active_workflow_status_group_page': 'CREATE INDEX '
                                                  'ix_findings_active_workflow_status_group_page '
                                                  'ON findings (org_id, workflow_status, severity, '
                                                  'created_at DESC NULLS LAST, id) WHERE '
                                                  'archived_at IS NULL AND suppression_id IS NULL',
 'ix_findings_archive_batch': 'CREATE INDEX ix_findings_archive_batch ON findings '
                              '(archive_batch_id) WHERE archive_batch_id IS NOT NULL',
 'ix_findings_category_trgm': 'CREATE INDEX ix_findings_category_trgm ON findings USING gin '
                              '(category gin_trgm_ops) WHERE archived_at IS NULL AND '
                              'suppression_id IS NULL',
 'ix_findings_description_trgm': 'CREATE INDEX ix_findings_description_trgm ON findings USING gin '
                                 '(description gin_trgm_ops) WHERE archived_at IS NULL AND '
                                 'suppression_id IS NULL',
 'ix_findings_org_created': 'CREATE INDEX ix_findings_org_created ON findings (org_id, created_at) '
                            'WHERE archived_at IS NULL AND suppression_id IS NULL',
 'ix_findings_org_severity_created': 'CREATE INDEX ix_findings_org_severity_created ON findings '
                                     '(org_id, severity, created_at) WHERE archived_at IS NULL AND '
                                     'suppression_id IS NULL',
 'ix_findings_risk_verified': 'CREATE INDEX ix_findings_risk_verified ON findings (org_id, domain, '
                              'severity, risk_verification_expires_at) WHERE archived_at IS NULL '
                              "AND suppression_id IS NULL AND risk_verification_state='approved'",
 'ix_findings_source_trgm': 'CREATE INDEX ix_findings_source_trgm ON findings USING gin (source '
                            'gin_trgm_ops) WHERE archived_at IS NULL AND suppression_id IS NULL',
 'ix_findings_suppressed_org': 'CREATE INDEX ix_findings_suppressed_org ON findings (org_id, '
                               'suppression_id, created_at) WHERE archived_at IS NULL AND '
                               'suppression_id IS NOT NULL',
 'ix_findings_suppression_history': 'CREATE INDEX ix_findings_suppression_history ON findings '
                                    '(suppression_history_id) WHERE suppression_history_id IS NOT '
                                    'NULL',
 'ix_findings_suppression_link': 'CREATE INDEX ix_findings_suppression_link ON findings '
                                 '(suppression_id) WHERE suppression_id IS NOT NULL'}


def _indexes(upgrade):
    before, after = (_OLD_INDEXES, _NEW_INDEXES) if upgrade else (_NEW_INDEXES, _OLD_INDEXES)
    for name in sorted(before):
        if before.get(name) == after.get(name): continue
        op.drop_index(name, table_name="findings")
    for name in sorted(after):
        if before.get(name) == after.get(name): continue
        op.execute(sa.text(after[name]))
