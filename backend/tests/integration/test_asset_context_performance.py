"""Indexed managed context on an isolated synthetic inventory; not SaaS capacity."""
import uuid
from datetime import datetime,timezone
import pytest
from sqlalchemy import insert,select,text
from app.models.asset import Asset
from app.models.asset_context import AssetContext, AssetContextHistory
from app.models.membership import OrgMembership
from tests.conftest import requires_db
from tests.helpers import register,first_org_id
pytestmark=requires_db

def test_context_filters_use_scoped_indexes_and_read_only_selected_page(client,db_session):
    h=register(client,'context-performance@example.io');org=uuid.UUID(first_org_id(client,h))
    owner=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==org));db_session.commit()
    target=None
    for chunk in range(10):
        ids=[uuid.uuid4() for _ in range(500)];target=ids[-1] if chunk==9 else target
        db_session.execute(insert(Asset),[dict(id=i,org_id=org,type='server',hostname='synthetic-'+str(i)) for i in ids])
        db_session.execute(insert(AssetContext),[dict(asset_id=i,org_id=org,version=1,owner_id=owner if i==target else None,
            owner_label='context-performance@example.io' if i==target else None,environment='Distinct business context' if i==target else 'Production',
            business_criticality='critical' if i==target else 'low',updated_at=datetime.now(timezone.utc)) for i in ids]);db_session.commit()
    db_session.execute(text('ANALYZE asset_contexts'));db_session.commit()
    for column,value,index in [('environment','Distinct business context',('ix_asset_context_org_environment',)),('owner_id',owner,('ix_asset_context_org_owner_id','ix_asset_context_owner_org'))]:
        plan=db_session.scalar(text(f'EXPLAIN (FORMAT JSON) SELECT asset_id FROM asset_contexts WHERE org_id=:o AND {column}=:value'),{'o':org,'value':value})
        assert any(name in str(plan) for name in index),plan
        assert "org_id" in str(plan) and column in str(plan)
    # Account removal must locate retained actor references without scanning
    # every unrelated context decision in the installation.
    ids=db_session.scalars(select(Asset.id).where(Asset.org_id==org)).all()
    db_session.execute(insert(AssetContextHistory),[dict(id=uuid.uuid4(),asset_id=i,org_id=org,actor_id=owner if i==target else None,actor_label='Synthetic reviewer',version=1,before={},after={},rationale='Synthetic history index probe',created_at=datetime.now(timezone.utc)) for i in ids]);db_session.commit()
    db_session.execute(text('ANALYZE asset_context_history'));db_session.commit()
    history_plan=db_session.scalar(text('EXPLAIN (FORMAT JSON) SELECT id FROM asset_context_history WHERE actor_id=:actor'),{'actor':owner})
    assert 'ix_asset_context_history_actor' in str(history_plan),history_plan
    response=client.get(f'/api/v1/orgs/{org}/assets',headers=h,params={'managed_environment':'Distinct business context','limit':1})
    assert response.status_code==200,response.text
    body=response.json();assert body['total']==1 and len(body['items'])==1 and body['items'][0]['id']==str(target)
    assert body['items'][0]['context']['business_criticality']=='critical'
