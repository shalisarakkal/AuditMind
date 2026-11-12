"""Release gate and pre-transaction checks must not mutate caller state."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.consolidation_transactions import _stage_metadata, publish


class NoDatabaseAccess:
    def __getattr__(self, name):
        raise AssertionError(f"Unexpected database access: {name}")


@pytest.mark.parametrize('pending', ['new', 'dirty', 'deleted'])
def test_pending_caller_changes_are_rejected_before_transaction_access(pending):
    db = NoDatabaseAccess()
    db.new, db.dirty, db.deleted = set(), set(), set()
    getattr(db, pending).add('Caller-owned pending work')
    with pytest.raises(HTTPException) as caught:
        _stage_metadata(db, None, None, None)
    assert caught.value.status_code == 409
    assert getattr(db, pending) == {'Caller-owned pending work'}


def test_publish_has_no_enable_parameter_or_database_side_effect():
    with pytest.raises(HTTPException) as caught:
        publish(NoDatabaseAccess(), enabled=True, integration_ready=True, confirm=True)
    assert caught.value.status_code == 409


def test_stale_snapshot_write_transaction_is_rejected_before_staging():
    db = NoDatabaseAccess()
    db.new, db.dirty, db.deleted = set(), set(), set()
    db.connection = lambda: SimpleNamespace(get_isolation_level=lambda: 'REPEATABLE READ')
    with pytest.raises(HTTPException) as caught:
        _stage_metadata(db, None, None, SimpleNamespace(confirm=True))
    assert caught.value.status_code == 409
