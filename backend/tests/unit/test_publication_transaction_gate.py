import uuid
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.services import publication_transactions as core


@pytest.mark.parametrize('entry', [core.publish, core.undo, core.update_settings])
def test_production_gate_cannot_be_opened_by_client_flags(entry):
    with pytest.raises(HTTPException) as error:
        entry(allow_writes=True, integrated=True, enabled=True, confirm=True)
    assert error.value.status_code==409


@pytest.mark.parametrize('change', [dict(replacement={'severity':'low'}),dict(allow_writes=True),
    dict(confirm=1),dict(confirm='true'),dict(expected_version=True),dict(expected_version='0'),
    dict(expected_version=-1),dict(rationale='  '),dict(review_token='bad')])
def test_internal_request_rejects_replacement_data_and_ambiguous_confirmation(change):
    body=dict(request_id=uuid.uuid4(),expected_version=0,review_token='a'*64,rationale='Review',confirm=True)
    with pytest.raises(ValidationError):core.PublicationRequest(**(body|change))
