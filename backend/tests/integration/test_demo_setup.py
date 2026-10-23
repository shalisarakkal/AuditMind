"""Demo data is repeatable and never resets user edits or credentials."""
import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from scripts.demo import DEMO_EMAIL, PLATFORM_EMAIL, configure_demo, demo_url, seed_demo
from app.core.config import Settings, settings
from app.core.security import verify_password
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.organization import Organization
from app.models.report import Report
from app.models.user import User
from app.services.asset_types import ASSET_TYPES
from tests.conftest import requires_db


@pytest.mark.parametrize("url", ["sqlite:///demo.db", "postgresql://u:p@remote.example/app", "postgresql://u:p@localhost/auditmind_test"])
def test_demo_refuses_unsafe_targets(url):
    with pytest.raises(ValueError):
        demo_url(url)


def test_demo_uses_explicit_schema_without_changing_database():
    url = demo_url("postgresql+psycopg://u:p@localhost/auditmind")
    assert url.database == "auditmind"
    assert url.query["options"] == "-csearch_path=auditmind_demo,public"


def test_demo_disables_external_credentials_and_keeps_public_signup_closed(monkeypatch):
    for field in Settings.model_fields:
        monkeypatch.setattr(settings, field, getattr(settings, field))
    for key in ("DATABASE_URL", "COOKIE_SECURE", "PUBLIC_SIGNUP", "RULE_BASED_TEST_REPORTS_ENABLED",
                "ARCHIVE_AUTO_PURGE", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VOYAGE_API_KEY",
                "CORS_ORIGINS", "UPLOAD_DIR", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+psycopg://u:p@localhost/auditmind")
    configure_demo()
    assert not settings.ANTHROPIC_API_KEY and not settings.OPENAI_API_KEY and not settings.VOYAGE_API_KEY
    assert not settings.PUBLIC_SIGNUP and not settings.COOKIE_SECURE
    assert settings.RULE_BASED_TEST_REPORTS_ENABLED
    assert make_url(os.environ["DATABASE_URL"]).query["options"] == "-csearch_path=auditmind_demo,public"


@requires_db
def test_seed_is_idempotent_and_contains_only_synthetic_preview(db_session):
    passwords = seed_demo(db_session)
    assert set(passwords) == {DEMO_EMAIL, PLATFORM_EMAIL}
    admin = db_session.scalar(select(User).where(User.email == DEMO_EMAIL))
    assert verify_password(passwords[DEMO_EMAIL], admin.hashed_password)
    original_hash = admin.hashed_password
    org = db_session.scalar(select(Organization))
    org.name = "User-edited demo name"
    db_session.commit()
    assert seed_demo(db_session) == {}
    assert admin.hashed_password == original_hash
    assert org.name == "User-edited demo name"
    assert db_session.scalar(select(func.count()).select_from(Asset)) == 4
    assert all(a.type in ASSET_TYPES for a in db_session.scalars(select(Asset)))
    assert db_session.scalar(select(func.count()).select_from(Finding)) == 7
    report = db_session.scalar(select(Report))
    assert report.data["provenance"]["assessment_type"] == "rule_based_test"
    assert report.data["provenance"]["external_processing"] is False


@requires_db
def test_seed_refuses_existing_non_demo_data(db_session):
    db_session.add(Organization(name="Not demo data"))
    db_session.commit()
    with pytest.raises(ValueError, match="populated database"):
        seed_demo(db_session)
    assert db_session.scalar(select(func.count()).select_from(User)) == 0
