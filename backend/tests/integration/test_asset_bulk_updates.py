"""Bulk import updates retain omission/null/JSON semantics and avoid no-op writes."""
import pytest
from sqlalchemy import select
from app.models.asset import Asset
from app.models.organization import Organization
from app.models.list_revision import OrganizationListRevision
from app.services.ingestion_service import _bulk_update_assets
from tests.conftest import requires_db

pytestmark = requires_db


def test_mixed_updates_preserve_omitted_fields_and_merge_json(db_session):
    org = Organization(name="Synthetic bulk semantics")
    db_session.add(org); db_session.flush()
    first = Asset(org_id=org.id,type="server",hostname="first",environment="old",tags=["old"],
        details={"keep":1,"nested":{"old":1},"region":"old"})
    second = Asset(org_id=org.id,type="server",hostname="second",environment="untouched",tags=["keep"],details={"keep":2})
    db_session.add_all([first,second]);db_session.commit()
    _bulk_update_assets(db_session, {first.id:{"environment":None,"tags":[]},second.id:{"hostname":"renamed"}},
        {first.id:{"region":"new","nested":{"new":2}},second.id:{"region":"west"}})
    db_session.commit();db_session.expire_all()
    assert first.environment is None and first.tags == [] and first.hostname == "first"
    assert first.details == {"keep":1,"nested":{"new":2},"region":"new"}
    assert second.environment == "untouched" and second.tags == ["keep"]
    assert second.hostname == "renamed" and second.details == {"keep":2,"region":"west"}


def test_same_payload_does_not_rewrite_or_invalidate_assets(db_session):
    org=Organization(name="Synthetic unchanged update")
    db_session.add(org);db_session.flush()
    asset=Asset(org_id=org.id,type="server",hostname="same",details={"region":"west"})
    db_session.add(asset);db_session.commit()
    from sqlalchemy import text
    before=db_session.execute(text('select xmin::text,ctid::text from assets where id=:id'),{'id':asset.id}).one()
    revision=db_session.scalar(select(OrganizationListRevision.asset_revision).where(OrganizationListRevision.org_id==org.id))
    _bulk_update_assets(db_session,{asset.id:{"hostname":"same"}},{asset.id:{"region":"west"}})
    db_session.commit()
    assert db_session.execute(text('select xmin::text,ctid::text from assets where id=:id'),{'id':asset.id}).one()==before
    assert db_session.scalar(select(OrganizationListRevision.asset_revision).where(OrganizationListRevision.org_id==org.id))==revision
