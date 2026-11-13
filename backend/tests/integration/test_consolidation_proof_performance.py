"""Bounded proof work on a large unrelated population; local warm-query evidence."""
import copy
import json
import time
import uuid
from datetime import timedelta
import pytest
from sqlalchemy import func,insert,select,text
from sqlalchemy.dialects import postgresql
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.models.finding_identity_binding import ObservationIdentityBinding
from app.services import status_scoring
from tests.conftest import requires_db
from tests.integration.test_finding_consolidation_foundation import native,select_pair
from tests.integration.test_consolidation_proof import approved

pytestmark=requires_db


@pytest.mark.parametrize('observations',[2,1000])
def test_group_proof_uses_approved_subset_and_bounded_source_set(client,db_session,native,observations):
    n=native;org=uuid.UUID(n['org'])
    if observations>2:
        source=n['source']
        binding=db_session.scalar(select(ObservationIdentityBinding).where(ObservationIdentityBinding.observation_id==source.id))
        rows=[];bindings=[]
        for i in range(observations-2):
            values={column.name:copy.deepcopy(getattr(source,column.name)) for column in FindingObservation.__table__.columns}
            identifier=uuid.uuid4()
            values.update(id=identifier,occurrence=i+100,recorded_at=source.recorded_at-timedelta(seconds=i+1))
            values['payload']={**values['payload'],'description':'Synthetic retained text '*350}
            rows.append(values)
            bindings.append(dict(id=uuid.uuid4(),org_id=org,observation_id=identifier,version=1,state='bound',
                tool_id=binding.tool_id,canonical_asset_id=binding.canonical_asset_id,context=binding.context,
                rationale='Independent bounded source review',actor_id=binding.actor_id,actor_label=binding.actor_label))
        db_session.execute(insert(FindingObservation),rows)
        db_session.execute(insert(ObservationIdentityBinding),bindings)
        db_session.commit();select_pair(client,n)
    db_session.execute(text("""INSERT INTO findings(id,org_id,domain,severity,source,description,created_at)
        SELECT gen_random_uuid(),:org,'backup_recovery','low','synthetic_unapproved_population',
            'Unrelated unapproved finding',now() FROM generate_series(1,100000)"""),{'org':org})
    db_session.commit()
    endpoint,result=approved(client,db_session,n)
    assert result['records'][0]['attestation']['group_context']['observation_count']==observations
    db_session.commit()
    with db_session.get_bind().connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.exec_driver_sql('ANALYZE findings, finding_observations, finding_verifications')
    query=select(func.count()).select_from(Finding).where(Finding.org_id==org,Finding.active(),status_scoring.eligible_exclusion())
    sql=str(query.compile(dialect=postgresql.dialect(),compile_kwargs={'literal_binds':True}))
    plan=db_session.scalar(text('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+sql))[0]
    def walk(node):
        yield node
        for child in node.get('Plans',[]):yield from walk(child)
    nodes=list(walk(plan['Plan']))
    assert not any(n['Node Type']=='Seq Scan' and n.get('Relation Name')=='findings' for n in nodes),json.dumps(plan)
    started=time.perf_counter()
    assert db_session.scalar(query)==1
    elapsed=time.perf_counter()-started
    assert elapsed<15 # Hang guard, not a service-level objective.
    print('CONSOLIDATION_PROOF_MEASUREMENTS='+json.dumps(dict(unapproved=100000,observations=observations,
        seconds=round(elapsed,4),execution_ms=plan['Execution Time'],
        indexes=sorted({n['Index Name'] for n in nodes if 'Index Name' in n}))))
