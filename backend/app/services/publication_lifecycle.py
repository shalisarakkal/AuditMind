"""Admission/worker guard for current publications, including later observations."""
from fastapi import HTTPException
from sqlalchemy import func, select


def ensure_free(db, org_id, kind, identifier):
    if db.scalar(select(func.am_publication_affected(org_id, kind, identifier))):
        raise HTTPException(409, dict(code='active_observation_publication',
            message='Undo the active observation publication before changing or removing this source.'))
