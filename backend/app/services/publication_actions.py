"""Authorized, default-off single-finding publication; private core remains closed."""
from fastapi import HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.services import publication_transactions as core, publication_consumers as consumers
from app.services.publication_read import storage_available

TABLES = ('organization_publication_settings', 'organization_publication_revisions',
          'observation_publication_dependencies')
SOURCES = ('assets','scans','findings','identity_tools','finding_observations','observation_identity_bindings','asset_scans')
REASON = 'Scanner-field publication requires coordinated database activation and all source lifecycle guards.'


def available(db):
    if not storage_available(db) or not all(db.scalar(select(func.to_regclass(name))) is not None for name in TABLES):
        return False
    for signature in ('am_publication_affected(uuid,text,uuid)', 'am_publication_source_guard()'):
        if db.scalar(select(func.to_regprocedure(signature))) is None:
            return False
    count=db.scalar(text("""SELECT count(*) FROM pg_trigger WHERE tgname='am_publication_source_guard'
        AND NOT tgisinternal AND tgenabled IN ('O','A') AND tgrelid IN
        (to_regclass('assets'),to_regclass('scans'),to_regclass('findings'),to_regclass('identity_tools'),
         to_regclass('finding_observations'),to_regclass('observation_identity_bindings'),to_regclass('asset_scans'))"""))
    return count == len(SOURCES)


def configuration(db, org_id):
    if not available(db):
        return dict(available=False, enabled=False, version=0, reason=REASON)
    return dict(available=True, **core.configuration(db, org_id), reason=None)


def require_available(db):
    if not available(db):
        raise HTTPException(409, dict(code='publication_activation_required', message=REASON))


def update_setting(db, org_id, actor_id, payload):
    core._clean(db)
    try:
        core._check_actor(db, org_id, actor_id)
        require_available(db)
        result=core._stage_setting(db, org_id, actor_id, payload)
        db.commit()
        return dict(available=True, **result, reason=None)
    except BaseException:
        db.rollback()
        raise


def preview(db, org_id, actor_id, finding_id, observation_id=None):
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409, 'Complete pending database changes before preview')
    with db.get_bind().engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with Session(bind=connection) as snapshot:
            snapshot.execute(text('SET TRANSACTION READ ONLY'))
            snapshot.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            core._check_actor(snapshot, org_id, actor_id)
            require_available(snapshot)
            if observation_id is None:
                prepared=core._undo_prepare(snapshot, org_id, actor_id, finding_id, consumers.CONTRACT)
                changes=prepared['changes'];no_op=False
            else:
                prepared=core._publish_prepare(snapshot, org_id, actor_id, finding_id, observation_id, consumers.CONTRACT)
                changes=prepared['plan']['changes'];no_op=prepared['plan']['no_op']
            return dict(contract=consumers.CONTRACT, operation='publish' if observation_id else 'undo',
                finding_id=str(finding_id), observation_id=str(observation_id) if observation_id else str(prepared['receipt'].observation_id),
                review_token=prepared['review_token'], expected_version=prepared['expected_version'],
                apply_available=not no_op, no_op=no_op, changes=changes, provenance=prepared['plan']['provenance'],
                message='Fresh single-finding review. Scanner fields may change; original ownership and current workflow are preserved. This does not restore an earlier scoring approval.')


def apply(db, org_id, actor_id, finding_id, payload, observation_id=None):
    core._clean(db)
    try:
        # Even receipt lookup must recheck current authorization. Policy-off
        # admission still permits authorized Undo and exact recorded replays.
        core._check_actor(db, org_id, actor_id)
        require_available(db)
        result=consumers._stage(db, org_id, actor_id, finding_id, payload, observation_id)
        db.commit()
        return result
    except BaseException:
        db.rollback()
        raise
