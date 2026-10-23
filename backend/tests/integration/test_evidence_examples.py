"""Synthetic demonstrations cannot be mistaken for provider evaluation."""
import pytest
from sqlalchemy import select, func
from scripts.evidence_examples import STATES, example_id, seed_examples, snapshot
from scripts.demo import seed_demo, DEMO_EMAIL
from app.models.report import Report
from app.models.user import User
from app.schemas.evidence_assessment import EvidenceSnapshot
from app.services.report_service import render_report_html, render_report_pdf
from tests.conftest import requires_db


@pytest.mark.parametrize("state", STATES)
def test_snapshot_and_exports(state):
    data = snapshot(state)
    assert EvidenceSnapshot.model_validate(data)
    assert data["provenance"]["external_processing"] is False
    assert data["provenance"]["evidence_qualification"]["operational_approval"] is False
    assert all(d["evidence_status"] == state for d in data["domains"])
    assert data["overall_score"] == (70 if state == "sufficient" else None)
    report = Report(title=data["title"], data=data, frameworks="SYNTHETIC")
    html = render_report_html(report)
    assert "Synthetic mock - no AI calls" in html
    assert "not a real audit" in html
    assert render_report_pdf(report).startswith(b"%PDF")


def test_unknown_state_refused():
    with pytest.raises(ValueError):
        snapshot("unknown")


def test_ordinary_schema_refused():
    from unittest.mock import Mock
    db = Mock()
    db.execute.return_value.one.return_value = ("public", "auditmind")
    with pytest.raises(ValueError, match="isolated demo"):
        seed_examples(db)
    db.commit.assert_not_called()


@requires_db
def test_persistent_examples_preserve_existing_demo(db_session):
    seed_demo(db_session)
    admin = db_session.scalar(select(User).where(User.email == DEMO_EMAIL))
    password_hash = admin.hashed_password
    assert seed_examples(db_session) == 4
    report = db_session.get(Report, example_id("limited"))
    report.title = "User-edited example"
    db_session.commit()
    assert seed_examples(db_session) == 0
    assert report.title == "User-edited example"
    assert admin.hashed_password == password_hash
    assert db_session.scalar(select(func.count()).select_from(Report)) == 5
