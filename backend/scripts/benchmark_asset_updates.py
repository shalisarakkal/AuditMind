"""Opt-in cloud reimport benchmark, isolated in an owned local *_test schema."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True,help='Retained cloud inventory JSON; read only')
    parser.add_argument('--expected-assets',type=int,default=500000)
    parser.add_argument('--control-rows',type=int,default=500)
    args=parser.parse_args()
    if not args.source.is_file() or not 1<=args.control_rows<=2000:
        raise SystemExit('Require an existing source and 1..2000 control rows')
    from app.core.config import settings
    from sqlalchemy import create_engine,select,text,update,event
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy import bindparam
    from app.db.base import Base
    from app.models.organization import Organization
    from app.models.scan import Scan
    from app.models.asset import Asset
    from app.services import ingestion_service as ingestion
    from app.services.import_profiles import FAMILIES,builtin_profile
    import httpx,httpx2
    def forbidden(*a,**kw): raise RuntimeError('External HTTP forbidden in benchmark')
    for module in (httpx,httpx2):
        module.HTTPTransport.handle_request=forbidden
        module.AsyncHTTPTransport.handle_async_request=forbidden
    url=make_url(settings.TEST_DATABASE_URL)
    if url.get_backend_name()!='postgresql' or url.host not in ('localhost','127.0.0.1') or not (url.database or '').endswith('_test'):
        raise SystemExit('Only local PostgreSQL *_test targets allowed')
    schema='asset_update_bench_'+uuid.uuid4().hex
    assert re.fullmatch(r'asset_update_bench_[0-9a-f]{32}',schema)
    output=Path(__file__).resolve().parents[2]/'temp/testing/asset-updates'/schema
    output.mkdir(parents=True)
    evidence={'schema':schema,'ordinary_data_changed':False,'runs':[]}
    with args.source.open('rb') as source:
        evidence['source_sha256']=hashlib.file_digest(source,'sha256').hexdigest()
    maintenance=create_engine(url)
    engine=create_engine(url.update_query_dict({'options':f'-csearch_path={schema},public'}))
    created=False
    def save(): (output/'results.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    def checksum(db,ids=None):
        where='' if ids is None else ' WHERE a.id=ANY(:ids)'
        return str(db.execute(text('SELECT count(*),sum(hashtextextended(to_jsonb(a)::text,0)::numeric) FROM assets a'+where),{} if ids is None else {'ids':ids}).one())
    def publish(db,org,label):
        scan=Scan(org_id=org.id,scan_type='cloud_inventory_import',source='upload',profile='cloud_inventory',
            filename='synthetic-cloud.json',started_at=datetime.now(timezone.utc))
        db.add(scan);db.commit()
        item={'mode':label,'bulk_update_statements':0}
        def record(conn,cursor,statement,parameters,context,executemany):
            if statement.lower().startswith('update assets as target set'):item['bulk_update_statements']+=1
        event.listen(engine,'before_cursor_execute',record)
        started=time.perf_counter()
        last=[None,0]
        def progress(phase,done,total):
            if phase!=last[0] or done-last[1]>=100000:
                last[:]=[phase,done]
                print(json.dumps({'mode':label,'phase':phase,'done':done,'total':total,'elapsed':round(time.perf_counter()-started,1)}),flush=True)
        try:
            report=ingestion.process_import(db,scan,'profile','json',args.source,builtin_profile(FAMILIES['cloud_inventory']),progress=progress)
        finally:event.remove(engine,'before_cursor_execute',record)
        item.update(seconds=round(time.perf_counter()-started,3),created=report.created,updated=report.updated)
        db.refresh(scan)
        assert scan.status.value=='completed'
        evidence['runs'].append(item);save();print(json.dumps(item),flush=True)
    try:
        with maintenance.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
        created=True
        Base.metadata.create_all(engine)
        with Session(engine,autoflush=False) as db:
            assert db.scalar(text('select current_schema()'))==schema
            org=Organization(name='Isolated cloud asset update benchmark');db.add(org);db.commit()
            publish(db,org,'seed')
            assert db.scalar(text('select count(*) from assets'))==args.expected_assets
            before=checksum(db);db.rollback()
            ids=list(db.scalars(select(Asset.id).order_by(Asset.id).limit(args.control_rows)));db.rollback()
            control_digests=[]
            for mode in ('old-row-updates','old-without-invalidation','bulk-updates'):
                revision=db.scalar(text('select asset_revision from organization_list_revisions where org_id=:id'),{'id':org.id})
                started=time.perf_counter()
                if mode=='old-without-invalidation':
                    # Diagnostic only: this owned test schema is dropped, and
                    # rollback restores its triggers. Never a production fix.
                    assert db.scalar(text('select current_schema()'))==schema
                    db.execute(text('ALTER TABLE assets DISABLE TRIGGER am_list_update'))
                    db.execute(text('ALTER TABLE assets DISABLE TRIGGER am_evidence_update'))
                values={identifier:{'environment':'benchmark-control'} for identifier in ids}
                details={identifier:{'benchmark_marker':'changed'} for identifier in ids}
                if mode!='bulk-updates':
                    db.execute(update(Asset),[{'id':identifier,**patch} for identifier,patch in values.items()])
                    table=Asset.__table__
                    db.execute(update(table).where(table.c.id==bindparam('asset_id'))
                        .values(details=table.c.details.op('||')(bindparam('new_details',type_=JSONB))),
                        [{'asset_id':identifier,'new_details':patch} for identifier,patch in details.items()])
                else:ingestion._bulk_update_assets(db,values,details)
                seconds=round(time.perf_counter()-started,3)
                delta=db.scalar(text('select asset_revision from organization_list_revisions where org_id=:id'),{'id':org.id})-revision
                control_digests.append(checksum(db,ids))
                item={'mode':mode,'rows':len(ids),'seconds':seconds,'list_revision_updates':delta}
                evidence['runs'].append(item);save();print(json.dumps(item),flush=True)
                db.rollback()
            assert len(set(control_digests))==1
            publish(db,org,'existing-assets-reimport')
            assert evidence['runs'][-1]['created']==0
            assert evidence['runs'][-1]['updated']==args.expected_assets
            assert checksum(db)==before,'Reimport changed the stored asset payloads'
            evidence['passed']=True
    finally:
        engine.dispose()
        if created:
            with maintenance.begin() as c:
                assert c.scalar(text('select current_database()'))==url.database
                assert re.fullmatch(r'asset_update_bench_[0-9a-f]{32}',schema)
                c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            evidence['schema_removed']=True
        maintenance.dispose();save();print('Evidence: '+str(output),flush=True)


if __name__=='__main__':
    if not __debug__:raise SystemExit('Assertions must be enabled')
    main()
