"""Materialize consolidation visibility, retaining physical source/history rows.

Rebuild affected partial indexes concurrently. Requires deployment coordination:
old application predicates do not imply the new visibility predicate. Do not
activate on a running old application without a maintenance/rollout plan.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

COLUMNS = ('consolidation_id','consolidation_alias_id','consolidation_history_id')


def upgrade():
    if not sa.inspect(op.get_bind()).has_table('organization_consolidation_revisions'):
        op.create_table('organization_consolidation_revisions',
        sa.Column('org_id',pg.UUID(as_uuid=True),sa.ForeignKey('organizations.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('revision',sa.BigInteger(),nullable=False,server_default='0'))
    for column in COLUMNS:
        if column not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns('findings')}:
            op.add_column('findings', sa.Column(column, pg.UUID(as_uuid=True)))
        if 'fk_findings_'+column not in {c['name'] for c in sa.inspect(op.get_bind()).get_foreign_keys('findings')}:
            op.create_foreign_key('fk_findings_'+column, 'findings', 'finding_consolidations',
                ['org_id',column], ['org_id','id'], deferrable=True, initially='DEFERRED')
        op.execute('CREATE INDEX IF NOT EXISTS ix_findings_'+column+' ON findings (org_id, '+column+') WHERE '+column+' IS NOT NULL')
    if 'ck_finding_consolidation_alias' not in {c['name'] for c in sa.inspect(op.get_bind()).get_check_constraints('findings')}:
        op.create_check_constraint('ck_finding_consolidation_alias','findings',
            'consolidation_alias_id IS NULL OR (consolidation_id IS NOT NULL AND consolidation_history_id IS NOT NULL AND consolidation_alias_id = consolidation_id AND consolidation_history_id = consolidation_id)')
    _replace_indexes(_NEW_INDEXES)


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM findings WHERE consolidation_id IS NOT NULL OR consolidation_alias_id IS NOT NULL OR consolidation_history_id IS NOT NULL) OR EXISTS (SELECT 1 FROM organization_consolidation_revisions WHERE revision > 0)')):
        raise RuntimeError('Retained consolidation visibility/history prevents schema downgrade')
    _replace_indexes(_OLD_INDEXES)
    op.drop_constraint('ck_finding_consolidation_alias','findings',type_='check')
    for column in reversed(COLUMNS):
        op.drop_index('ix_findings_'+column,table_name='findings')
        op.drop_constraint('fk_findings_'+column,'findings',type_='foreignkey')
        op.drop_column('findings',column)
    op.drop_table('organization_consolidation_revisions')


def _replace_indexes(definitions):
    # Frozen SQL, not imports of future application metadata. Build replacement
    # before dropping the old index; swaps take place transactionally afterward.
    for name, definition in sorted(definitions.items()):
        temporary = name+'_c53'
        sql = definition.replace('CREATE INDEX '+name+' ', 'CREATE INDEX CONCURRENTLY '+temporary+' ', 1)
        with op.get_context().autocommit_block():
            op.execute('DROP INDEX CONCURRENTLY IF EXISTS '+temporary)
            op.execute(sql)
        op.drop_index(name,table_name='findings')
        op.execute('ALTER INDEX '+temporary+' RENAME TO '+name)


# Frozen predicates retain index-only count/seek paths after visibility changes.
_OLD_INDEXES = {'ix_findings_active_assignee': 'CREATE INDEX ix_findings_active_assignee ON findings '
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
                            'gin_trgm_ops) WHERE archived_at IS NULL AND suppression_id IS NULL'}

_NEW_INDEXES = {'ix_findings_active_assignee': 'CREATE INDEX ix_findings_active_assignee ON findings '
                                '(assignee_id) WHERE archived_at IS NULL AND suppression_id IS '
                                'NULL AND consolidation_alias_id IS NULL',
 'ix_findings_active_assignee_id_group_page': 'CREATE INDEX '
                                              'ix_findings_active_assignee_id_group_page ON '
                                              'findings (org_id, assignee_id, severity, created_at '
                                              'DESC NULLS LAST, id) WHERE archived_at IS NULL AND '
                                              'suppression_id IS NULL AND consolidation_alias_id '
                                              'IS NULL',
 'ix_findings_active_category_asc_page': 'CREATE INDEX ix_findings_active_category_asc_page ON '
                                         'findings (org_id, lower(category) ASC NULLS LAST, (\n'
                                         'CASE\n'
                                         "    WHEN severity::text = 'critical'::text THEN 0\n"
                                         "    WHEN severity::text = 'high'::text THEN 1\n"
                                         "    WHEN severity::text = 'medium'::text THEN 2\n"
                                         "    WHEN severity::text = 'low'::text THEN 3\n"
                                         '    ELSE NULL::integer\n'
                                         'END), created_at DESC NULLS LAST, id) WHERE archived_at '
                                         'IS NULL AND suppression_id IS NULL AND '
                                         'consolidation_alias_id IS NULL',
 'ix_findings_active_category_desc_page': 'CREATE INDEX ix_findings_active_category_desc_page ON '
                                          'findings (org_id, lower(category) DESC NULLS LAST, (\n'
                                          'CASE\n'
                                          "    WHEN severity::text = 'critical'::text THEN 0\n"
                                          "    WHEN severity::text = 'high'::text THEN 1\n"
                                          "    WHEN severity::text = 'medium'::text THEN 2\n"
                                          "    WHEN severity::text = 'low'::text THEN 3\n"
                                          '    ELSE NULL::integer\n'
                                          'END), created_at DESC NULLS LAST, id) WHERE archived_at '
                                          'IS NULL AND suppression_id IS NULL AND '
                                          'consolidation_alias_id IS NULL',
 'ix_findings_active_created_page': 'CREATE INDEX ix_findings_active_created_page ON findings '
                                    '(org_id, created_at, id) WHERE archived_at IS NULL AND '
                                    'suppression_id IS NULL AND consolidation_alias_id IS NULL',
 'ix_findings_active_domain_page': 'CREATE INDEX ix_findings_active_domain_page ON findings '
                                   '(org_id, domain, (\n'
                                   'CASE\n'
                                   "    WHEN severity::text = 'critical'::text THEN 0\n"
                                   "    WHEN severity::text = 'high'::text THEN 1\n"
                                   "    WHEN severity::text = 'medium'::text THEN 2\n"
                                   "    WHEN severity::text = 'low'::text THEN 3\n"
                                   '    ELSE NULL::integer\n'
                                   'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                   'NULL AND suppression_id IS NULL AND consolidation_alias_id IS '
                                   'NULL',
 'ix_findings_active_due_presence': 'CREATE INDEX ix_findings_active_due_presence ON findings '
                                    '(org_id) WHERE archived_at IS NULL AND suppression_id IS NULL '
                                    'AND consolidation_alias_id IS NULL AND (due_date IS NOT NULL '
                                    'OR due_expires_at IS NOT NULL)',
 'ix_findings_active_due_search': 'CREATE INDEX ix_findings_active_due_search ON findings (org_id) '
                                  'WHERE archived_at IS NULL AND suppression_id IS NULL AND '
                                  'consolidation_alias_id IS NULL AND due_date IS NOT NULL',
 'ix_findings_active_long_text': 'CREATE INDEX ix_findings_active_long_text ON findings (org_id) '
                                 'WHERE archived_at IS NULL AND '
                                 'COALESCE(octet_length(lower(COALESCE(description, '
                                 'category::text))), 0) > 1024 AND suppression_id IS NULL AND '
                                 'consolidation_alias_id IS NULL',
 'ix_findings_active_org_assignee_id': 'CREATE INDEX ix_findings_active_org_assignee_id ON '
                                       'findings (org_id, assignee_id) WHERE archived_at IS NULL '
                                       'AND suppression_id IS NULL AND consolidation_alias_id IS '
                                       'NULL',
 'ix_findings_active_org_domain_severity': 'CREATE INDEX ix_findings_active_org_domain_severity ON '
                                           'findings (org_id, domain, severity) WHERE archived_at '
                                           'IS NULL AND suppression_id IS NULL AND '
                                           'consolidation_alias_id IS NULL',
 'ix_findings_active_org_scan_id': 'CREATE INDEX ix_findings_active_org_scan_id ON findings '
                                   '(org_id, scan_id) WHERE archived_at IS NULL AND suppression_id '
                                   'IS NULL AND consolidation_alias_id IS NULL',
 'ix_findings_active_org_source': 'CREATE INDEX ix_findings_active_org_source ON findings (org_id, '
                                  'source) WHERE archived_at IS NULL AND suppression_id IS NULL '
                                  'AND consolidation_alias_id IS NULL',
 'ix_findings_active_org_workflow_status': 'CREATE INDEX ix_findings_active_org_workflow_status ON '
                                           'findings (org_id, workflow_status) WHERE archived_at '
                                           'IS NULL AND suppression_id IS NULL AND '
                                           'consolidation_alias_id IS NULL',
 'ix_findings_active_review_presence': 'CREATE INDEX ix_findings_active_review_presence ON '
                                       'findings (org_id) WHERE archived_at IS NULL AND '
                                       'suppression_id IS NULL AND consolidation_alias_id IS NULL '
                                       'AND (risk_review_date IS NOT NULL OR '
                                       'risk_review_expires_at IS NOT NULL)',
 'ix_findings_active_review_search': 'CREATE INDEX ix_findings_active_review_search ON findings '
                                     '(org_id) WHERE archived_at IS NULL AND suppression_id IS '
                                     'NULL AND consolidation_alias_id IS NULL AND risk_review_date '
                                     'IS NOT NULL',
 'ix_findings_active_severity_page': 'CREATE INDEX ix_findings_active_severity_page ON findings '
                                     '(org_id, (\n'
                                     'CASE\n'
                                     "    WHEN severity::text = 'critical'::text THEN 0\n"
                                     "    WHEN severity::text = 'high'::text THEN 1\n"
                                     "    WHEN severity::text = 'medium'::text THEN 2\n"
                                     "    WHEN severity::text = 'low'::text THEN 3\n"
                                     '    ELSE NULL::integer\n'
                                     'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                     'NULL AND suppression_id IS NULL AND consolidation_alias_id '
                                     'IS NULL',
 'ix_findings_active_source_asc_page': 'CREATE INDEX ix_findings_active_source_asc_page ON '
                                       'findings (org_id, lower(source) ASC NULLS LAST, (\n'
                                       'CASE\n'
                                       "    WHEN severity::text = 'critical'::text THEN 0\n"
                                       "    WHEN severity::text = 'high'::text THEN 1\n"
                                       "    WHEN severity::text = 'medium'::text THEN 2\n"
                                       "    WHEN severity::text = 'low'::text THEN 3\n"
                                       '    ELSE NULL::integer\n'
                                       'END), created_at DESC NULLS LAST, id) WHERE archived_at IS '
                                       'NULL AND suppression_id IS NULL AND consolidation_alias_id '
                                       'IS NULL',
 'ix_findings_active_source_desc_page': 'CREATE INDEX ix_findings_active_source_desc_page ON '
                                        'findings (org_id, lower(source) DESC NULLS LAST, (\n'
                                        'CASE\n'
                                        "    WHEN severity::text = 'critical'::text THEN 0\n"
                                        "    WHEN severity::text = 'high'::text THEN 1\n"
                                        "    WHEN severity::text = 'medium'::text THEN 2\n"
                                        "    WHEN severity::text = 'low'::text THEN 3\n"
                                        '    ELSE NULL::integer\n'
                                        'END), created_at DESC NULLS LAST, id) WHERE archived_at '
                                        'IS NULL AND suppression_id IS NULL AND '
                                        'consolidation_alias_id IS NULL',
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
                                     'category::text))), 0) <= 1024 AND suppression_id IS NULL AND '
                                     'consolidation_alias_id IS NULL',
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
                                      'category::text))), 0) <= 1024 AND suppression_id IS NULL '
                                      'AND consolidation_alias_id IS NULL',
 'ix_findings_active_workflow_status_group_page': 'CREATE INDEX '
                                                  'ix_findings_active_workflow_status_group_page '
                                                  'ON findings (org_id, workflow_status, severity, '
                                                  'created_at DESC NULLS LAST, id) WHERE '
                                                  'archived_at IS NULL AND suppression_id IS NULL '
                                                  'AND consolidation_alias_id IS NULL',
 'ix_findings_category_trgm': 'CREATE INDEX ix_findings_category_trgm ON findings USING gin '
                              '(category gin_trgm_ops) WHERE archived_at IS NULL AND '
                              'suppression_id IS NULL AND consolidation_alias_id IS NULL',
 'ix_findings_description_trgm': 'CREATE INDEX ix_findings_description_trgm ON findings USING gin '
                                 '(description gin_trgm_ops) WHERE archived_at IS NULL AND '
                                 'suppression_id IS NULL AND consolidation_alias_id IS NULL',
 'ix_findings_org_created': 'CREATE INDEX ix_findings_org_created ON findings (org_id, created_at) '
                            'WHERE archived_at IS NULL AND suppression_id IS NULL AND '
                            'consolidation_alias_id IS NULL',
 'ix_findings_org_severity_created': 'CREATE INDEX ix_findings_org_severity_created ON findings '
                                     '(org_id, severity, created_at) WHERE archived_at IS NULL AND '
                                     'suppression_id IS NULL AND consolidation_alias_id IS NULL',
 'ix_findings_risk_verified': 'CREATE INDEX ix_findings_risk_verified ON findings (org_id, domain, '
                              'severity, risk_verification_expires_at) WHERE archived_at IS NULL '
                              'AND suppression_id IS NULL AND consolidation_alias_id IS NULL AND '
                              "risk_verification_state='approved'",
 'ix_findings_source_trgm': 'CREATE INDEX ix_findings_source_trgm ON findings USING gin (source '
                            'gin_trgm_ops) WHERE archived_at IS NULL AND suppression_id IS NULL '
                            'AND consolidation_alias_id IS NULL'}
