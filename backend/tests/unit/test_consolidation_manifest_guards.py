"""Malformed internal inputs must fail before any database lookup."""
import uuid
from types import SimpleNamespace

import pytest

from app.services.consolidation_dependencies import manifest


class NoDatabaseReads:
    def __getattr__(self, name):
        raise AssertionError(f"Unexpected database access: {name}")


@pytest.mark.parametrize('case', ['missing_identity', 'malformed_identity', 'missing_tool',
    'wrong_pair', 'wrong_org', 'foreign_finding', 'foreign_observation', 'over_limit', 'empty'])
def test_manifest_rejects_invalid_context_without_queries(case):
    org, first, second, asset, tool = [uuid.uuid4() for _ in range(5)]
    decision = SimpleNamespace(org_id=org, canonical_finding_id=first,
        finding_a_id=first, finding_b_id=second)
    findings = {key: SimpleNamespace(org_id=org) for key in (first, second)}
    observation = SimpleNamespace(org_id=org, finding_id=first)
    observations = [observation]
    identity = dict(canonical_asset_id=str(asset), tool_id=str(tool))
    if case == 'missing_identity': identity = None
    elif case == 'malformed_identity': identity['canonical_asset_id'] = 'not-a-uuid'
    elif case == 'missing_tool': identity.pop('tool_id')
    elif case == 'wrong_pair': decision.finding_b_id = uuid.uuid4()
    elif case == 'wrong_org': decision.org_id = uuid.uuid4()
    elif case == 'foreign_finding': findings[first].org_id = uuid.uuid4()
    elif case == 'foreign_observation': observation.org_id = uuid.uuid4()
    elif case == 'over_limit': observations *= 1001
    elif case == 'empty': observations = []
    assert manifest(NoDatabaseReads(), org, decision, findings, observations, identity) is None


@pytest.mark.parametrize('pending', ['new', 'dirty', 'deleted'])
def test_preview_connection_release_preserves_pending_changes(pending):
    from fastapi import HTTPException
    from app.api.routes.finding_consolidations import release_request_reads
    state = dict(new=set(), dirty=set(), deleted=set())
    state[pending].add('pending work')
    db = SimpleNamespace(**state, rollback=lambda: pytest.fail('Pending work was discarded'))
    with pytest.raises(HTTPException) as error:
        release_request_reads(db)
    assert error.value.status_code == 409
