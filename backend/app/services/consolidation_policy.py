"""Separate organization opt-in. Disabling blocks new applies, never undoes groups."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models.finding_consolidation import OrganizationConsolidationSettings


def configuration(db,org_id):
    row=db.scalar(select(OrganizationConsolidationSettings).where(OrganizationConsolidationSettings.org_id==org_id).execution_options(populate_existing=True))
    return dict(enabled=row.enabled if row else False,version=row.version if row else 0)


def _update(db,org_id,actor_id,payload):
    from app.services.consolidation_transactions import _admit, _bounded_lock_wait
    from app.services.events import record_event
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409,'Complete pending database changes first')
    if db.connection().get_isolation_level()!='READ COMMITTED':
        raise HTTPException(409,'A fresh read-committed transaction is required')
    with db.begin_nested(), _bounded_lock_wait(db):
        actor=_admit(db,org_id,actor_id)
        current=configuration(db,org_id)
        if payload.expected_version!=current['version']:
            raise HTTPException(409,'Consolidation setting changed; reload before saving')
        if payload.enabled==current['enabled']:
            return current
        row=db.get(OrganizationConsolidationSettings,org_id)
        if row is None:
            row=OrganizationConsolidationSettings(org_id=org_id,enabled=payload.enabled,version=1);db.add(row)
        else:
            row.enabled=payload.enabled;row.version+=1
        record_event(db,'settings_changed',org_id=org_id,actor=actor,item='Reviewed finding consolidation',
            details=dict(enabled=payload.enabled,version=row.version))
        db.flush()
    db.commit()
    return configuration(db,org_id)


def update(db,org_id,actor_id,payload):
    from sqlalchemy.exc import DBAPIError
    try:
        return _update(db,org_id,actor_id,payload)
    except DBAPIError as error:
        if getattr(error.orig,'sqlstate',None) in ('55P03','23505','23503'):
            raise HTTPException(409,'Consolidation settings are busy or changed; reload before retrying') from error
        raise
