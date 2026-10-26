"""Read-side serialization does not create evidence or change source fields."""
from types import SimpleNamespace
from uuid import uuid4
from app.services.finding_workflow import _state


def test_state_is_json_safe_and_source_independent():
    finding = SimpleNamespace(workflow_status="open", assignee_id=uuid4(),
        due_date=None, risk_review_date=None, description="Original evidence")
    state = _state(finding)
    assert state["assignee_id"] == str(finding.assignee_id)
    assert set(state) == {"status", "assignee_id", "due_date", "risk_review_date", "due_timezone", "due_expires_at", "risk_review_timezone", "risk_review_expires_at"}
    assert finding.description == "Original evidence"
