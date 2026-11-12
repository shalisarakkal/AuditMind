"""Verify covering count plans with 100k retained findings; not a SaaS load test."""
import json
import time
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql

from app.models.finding import Finding
from app.services.scoring_service import count_org_findings
from tests.conftest import requires_db
from tests.integration.test_finding_consolidation_foundation import native
from tests.integration.test_consolidation_visibility import apply

pytestmark = requires_db


def test_large_visible_counts_retain_index_only_scan_before_and_after_pair(db_session,native):
    org=uuid.UUID(native['org']);engine=db_session.get_bind()
    assert engine.url.database=='auditmind_test'
    # Seed once in the database rather than timing Python row construction and
    # 100,000 separate statement-trigger invocations. Query plans are measured
    # below; this synthetic seed is not an importer throughput benchmark.
    db_session.execute(text("""INSERT INTO findings
        (id,org_id,domain,severity,source,description,created_at)
        SELECT gen_random_uuid(), :org, 'backup_recovery', 'low',
            'synthetic_visibility_benchmark', repeat('Synthetic benchmark payload ',30), now()
        FROM generate_series(1,100000)"""), {'org':org})
    db_session.commit()
    measurements=[]
    def measure(label,expected):
        db_session.commit()
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.exec_driver_sql('VACUUM (ANALYZE) findings')
        query=select(Finding.domain,Finding.severity,func.count()).where(Finding.org_id==org,
            Finding.active()).group_by(Finding.domain,Finding.severity)
        sql=str(query.compile(dialect=postgresql.dialect(),compile_kwargs={'literal_binds':True}))
        plan=db_session.scalar(text('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+sql))[0]
        def nodes(node):
            yield node
            for child in node.get('Plans',[]):yield from nodes(child)
        entries=list(nodes(plan['Plan']))
        scans=[node for node in entries if node['Node Type']=='Index Only Scan']
        assert scans,plan
        heap_fetches=sum(node.get('Heap Fetches',0) for node in scans)
        # Recently changed pair tuples can need heap visibility checks even
        # after VACUUM while another snapshot is alive. Bound these checks;
        # never require all-visible pages as a publication correctness rule.
        assert heap_fetches <= 64, json.dumps(plan)
        assert not any('Subplan Name' in node or 'Join Type' in node for node in entries),plan
        started=time.perf_counter()
        counts=count_org_findings(db_session,org)
        assert sum(sum(values.values()) for values in counts.values())==expected
        measurements.append(dict(case=label,findings=expected,seconds=round(time.perf_counter()-started,4),
            index_names=[node['Index Name'] for node in scans],heap_fetches=heap_fetches))
    measure('before_pair',100002)
    apply(db_session,native);db_session.commit()
    measure('after_pair',100001)
    assert db_session.scalar(select(func.count()).select_from(Finding).where(Finding.org_id==org))==100002
    print('CONSOLIDATION_VISIBILITY_MEASUREMENTS='+json.dumps(measurements,sort_keys=True))
