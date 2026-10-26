from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.schemas.finding_workflow import WorkflowBulk, WorkflowUpdate


@pytest.mark.parametrize("extra", [dict(status=None), dict(status="closed"),
    dict(expected_version=True), dict(expected_version=-1), dict(rationale="  "),
    dict(verification="  "), dict(rationale="x" * 2001), dict(unrecognized="value")])
def test_invalid_patch(extra):
    with pytest.raises(ValidationError):
        WorkflowUpdate.model_validate(dict(expected_version=0, rationale="Reviewed") | extra)


def test_omission_and_explicit_null_are_distinct():
    omitted = WorkflowUpdate(expected_version=0, rationale="Reviewed")
    clear = WorkflowUpdate(expected_version=0, rationale="Reviewed", due_date=None)
    assert "due_date" not in omitted.model_fields_set
    assert "due_date" in clear.model_fields_set


@pytest.mark.parametrize("size", [0, 101])
def test_bulk_size_bounds(size):
    with pytest.raises(ValidationError):
        WorkflowBulk(targets=[dict(finding_id=uuid4(), expected_version=0) for _ in range(size)],
            patch=dict(rationale="Reviewed"))
