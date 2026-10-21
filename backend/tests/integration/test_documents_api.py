import uuid
from unittest.mock import Mock

import pytest
from sqlalchemy import select, update

from app.models.event import Event
from app.models.knowledge import KnowledgeIndex, KnowledgeVersion
from app.services import knowledge_embeddings, knowledge_service
from tests.conftest import requires_db
from tests.helpers import first_org_id, member, register, run_worker

pytestmark = requires_db


def upload(client, headers, org, content="Require MFA for administrators", document_id=None, title="Access policy", framework=""):
    data = {"title": title, "framework": framework, "edition": "1", "source": "Internal policy", "content_kind": "organization_policy", "rights": "Organization owns this policy"}
    if document_id:
        data["document_id"] = document_id
        data["edition"] = "2"
    return client.post(f"/api/v1/orgs/{org}/documents", headers=headers, data=data,
                       files={"file": ("policy.md", content.encode())})


def test_ingest_retrieve_versions_and_scope(client, db_session, monkeypatch):
    monkeypatch.setattr(knowledge_embeddings, "embed", lambda profile, texts, **kw: [[1.0] + [0.0] * 1023 for _ in texts])
    admin = register(client, "knowledge@example.io")
    org = first_org_id(client, admin)
    other = register(client, "other-knowledge@example.io")
    other_org = first_org_id(client, other)
    response = upload(client, admin, org)
    assert response.status_code == 202, response.text
    doc = response.json()
    version = doc["versions"][0]["id"]
    uploaded = db_session.scalar(
        select(Event).where(Event.org_id == uuid.UUID(org), Event.type == "document_uploaded")
    )
    assert uploaded is not None
    assert uploaded.item == "Access policy"
    assert uploaded.actor_label == "knowledge@example.io"
    assert uploaded.details["version_id"] == version
    activity = client.get(
        f"/api/v1/orgs/{org}/events",
        headers=admin,
        params={"q": "Document uploaded"},
    )
    assert activity.status_code == 200
    assert [event["type"] for event in activity.json()["items"]] == ["document_uploaded"]
    listing = client.get(
        f"/api/v1/orgs/{org}/documents",
        headers=admin,
        params={"q": "Internal policy", "sort": "created", "order": "desc", "limit": 100, "offset": 0},
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["created_at"]
    facets = client.get(f"/api/v1/orgs/{org}/documents/facets", headers=admin)
    assert facets.status_code == 200
    assert "" in facets.json()["framework"]

    reindex = client.post(
        f"/api/v1/orgs/{org}/documents/versions/{version}/reindex",
        headers=admin,
    )
    assert reindex.status_code == 200, reindex.text
    assert db_session.scalar(
        select(Event).where(Event.org_id == uuid.UUID(org), Event.type == "document_index_queued")
    ) is not None

    assert run_worker() == 1
    result = client.post(f"/api/v1/orgs/{org}/documents/search", headers=admin, json={"query": "administrator MFA", "frameworks": ["NIST"]})
    assert result.status_code == 200, result.text
    assert result.json()["items"][0]["version_id"] == version
    assert client.get(f"/api/v1/orgs/{other_org}/documents/versions/{version}", headers=other).status_code == 404
    assert client.post(f"/api/v1/orgs/{other_org}/documents/search", headers=other, json={"query": "MFA"}).json()["items"] == []
    newer = upload(client, admin, org, "Require phishing-resistant MFA", doc["id"], title="Access policy v2", framework="NIST")
    assert newer.status_code == 202, newer.text
    assert newer.json()["title"] == "Access policy v2"
    assert newer.json()["framework"] == "NIST"
    same_upload = upload(client, admin, org, "Require phishing-resistant MFA", doc["id"], title="Access policy v2", framework="NIST")
    assert same_upload.status_code == 202, same_upload.text
    assert [version["id"] for version in same_upload.json()["versions"]] == [version["id"] for version in newer.json()["versions"]]
    assert len(same_upload.json()["versions"]) == 2
    assert run_worker() == 1
    old = db_session.get(KnowledgeVersion, uuid.UUID(version), populate_existing=True)
    assert not old.current and old.retired_at
    current = newer.json()["versions"][0]
    retired = client.post(
        f"/api/v1/orgs/{org}/documents/versions/{current['id']}/retire",
        headers=admin,
    )
    assert retired.status_code == 200, retired.text
    assert db_session.scalar(
        select(Event).where(Event.org_id == uuid.UUID(org), Event.type == "document_retired")
    ) is not None
    purge = client.post(f"/api/v1/orgs/{org}/documents/versions/{version}/purge?confirmed=true", headers=admin)
    assert purge.status_code == 200, purge.text
    db_session.refresh(old)
    assert old.content is None and old.purged_at
    assert db_session.scalar(
        select(Event).where(Event.org_id == uuid.UUID(org), Event.type == "document_removed")
    ) is not None


def test_viewers_cannot_upload_and_consent_is_separate(client, db_session):
    admin = register(client, "document-roles@example.io")
    org = first_org_id(client, admin)
    viewer = member(client, admin, org, "viewer")
    assert upload(client, viewer, org).status_code == 403
    settings = client.get(f"/api/v1/orgs/{org}/documents/settings", headers=admin)
    assert settings.status_code == 200, settings.text
    data = settings.json()
    assert not data["report_granted"] and not data["embedding_granted"]
    response = client.put(f"/api/v1/orgs/{org}/documents/settings/consent", headers=admin,
                          json={"purpose": "report", "granted": True, "target": data["report_target"]})
    assert response.status_code == 200, response.text
    consent_event = db_session.scalar(
        select(Event).where(Event.org_id == uuid.UUID(org), Event.type == "knowledge_consent_changed")
    )
    assert consent_event is not None
    assert consent_event.item == "Report processing consent"
    assert consent_event.actor_label == "document-roles@example.io"
    assert consent_event.details == {
        "purpose": "report",
        "from": False,
        "to": True,
        "target": data["report_target"],
    }
    data = client.get(f"/api/v1/orgs/{org}/documents/settings", headers=admin).json()
    assert data["report_granted"] and not data["embedding_granted"]


def test_bulk_retire_and_remove_versions(client, db_session):
    admin = register(client, "bulk-documents@example.io")
    org = first_org_id(client, admin)
    first = upload(client, admin, org, "First policy")
    second = upload(client, admin, org, "Second policy", title="Second policy")
    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    version_ids = [first.json()["versions"][0]["id"], second.json()["versions"][0]["id"]]

    retired = client.post(
        f"/api/v1/orgs/{org}/documents/bulk-retire",
        headers=admin,
        json={"ids": version_ids},
    )
    assert retired.status_code == 200, retired.text
    assert retired.json() == {"changed": 2}
    versions = [db_session.get(KnowledgeVersion, uuid.UUID(version_id), populate_existing=True) for version_id in version_ids]
    assert all(version.retired_at and not version.current for version in versions)

    unconfirmed = client.post(
        f"/api/v1/orgs/{org}/documents/bulk-remove",
        headers=admin,
        json={"ids": version_ids},
    )
    assert unconfirmed.status_code == 422
    duplicate = client.post(
        f"/api/v1/orgs/{org}/documents/bulk-retire",
        headers=admin,
        json={"ids": [version_ids[0], version_ids[0]]},
    )
    assert duplicate.status_code == 422

    removed = client.post(
        f"/api/v1/orgs/{org}/documents/bulk-remove?confirmed=true",
        headers=admin,
        json={"ids": version_ids},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"changed": 2}
    assert all(
        db_session.get(KnowledgeVersion, uuid.UUID(version_id), populate_existing=True).content is None
        for version_id in version_ids
    )
    assert db_session.scalar(
        select(Event).where(Event.org_id == uuid.UUID(org), Event.type == "document_retired").limit(1)
    ) is not None
    assert db_session.scalar(
        select(Event).where(Event.org_id == uuid.UUID(org), Event.type == "document_removed").limit(1)
    ) is not None


def test_reactivate_retired_version_reindexes_before_publishing(client, db_session, monkeypatch):
    monkeypatch.setattr(
        knowledge_embeddings,
        "embed",
        lambda profile, texts, **kwargs: [[1.0] + [0.0] * (profile.dimensions - 1) for _ in texts],
    )
    admin = register(client, "reactivate-documents@example.io")
    org = first_org_id(client, admin)

    first = upload(client, admin, org, "Require MFA for administrators")
    assert first.status_code == 202, first.text
    document = first.json()
    retired_id = document["versions"][0]["id"]
    assert run_worker() == 1

    second = upload(
        client,
        admin,
        org,
        "Require phishing-resistant MFA",
        document_id=document["id"],
        title="Access policy",
    )
    assert second.status_code == 202, second.text
    current_id = second.json()["versions"][0]["id"]
    assert run_worker() == 1

    blocked = client.post(
        f"/api/v1/orgs/{org}/documents/versions/{retired_id}/reactivate",
        headers=admin,
    )
    assert blocked.status_code == 409

    retired_current = client.post(
        f"/api/v1/orgs/{org}/documents/versions/{current_id}/retire",
        headers=admin,
    )
    assert retired_current.status_code == 200, retired_current.text
    queued = client.post(
        f"/api/v1/orgs/{org}/documents/versions/{retired_id}/reactivate",
        headers=admin,
    )
    assert queued.status_code == 200, queued.text

    old = db_session.get(KnowledgeVersion, uuid.UUID(retired_id), populate_existing=True)
    assert old.retired_at and not old.current
    index = db_session.scalar(select(KnowledgeIndex).where(KnowledgeIndex.version_id == uuid.UUID(retired_id)))
    assert index.publish_version and index.status == "pending"
    reactivation_event = db_session.scalar(
        select(Event).where(Event.org_id == uuid.UUID(org), Event.type == "document_reactivation_queued")
    )
    assert reactivation_event is not None
    assert reactivation_event.details["version_id"] == retired_id

    removal_during_reactivation = client.post(
        f"/api/v1/orgs/{org}/documents/versions/{retired_id}/purge?confirmed=true",
        headers=admin,
    )
    assert removal_during_reactivation.status_code == 409
    db_session.refresh(old)
    assert old.content is not None

    def fail_embedding(profile, texts):
        raise RuntimeError(f"embedding unavailable: {profile.model} for {len(texts)} chunks")

    monkeypatch.setattr(knowledge_embeddings, "embed", fail_embedding)
    assert run_worker() == 1
    db_session.refresh(old)
    db_session.refresh(index)
    assert old.retired_at and not old.current
    assert index.status == "failed"

    monkeypatch.setattr(
        knowledge_embeddings,
        "embed",
        lambda profile, texts, **kwargs: [[1.0] + [0.0] * (profile.dimensions - 1) for _ in texts],
    )
    retried = client.post(
        f"/api/v1/orgs/{org}/documents/versions/{retired_id}/reactivate",
        headers=admin,
    )
    assert retried.status_code == 200, retried.text
    assert run_worker() == 1
    db_session.refresh(old)
    current = db_session.get(KnowledgeVersion, uuid.UUID(current_id), populate_existing=True)
    assert old.current and old.retired_at is None
    assert not current.current and current.retired_at

    search = client.post(
        f"/api/v1/orgs/{org}/documents/search",
        headers=admin,
        json={"query": "administrator MFA"},
    )
    assert search.status_code == 200, search.text
    assert search.json()["items"][0]["version_id"] == retired_id


def test_retiring_queued_document_prevents_later_publication(client, db_session, monkeypatch):
    embed = Mock()
    monkeypatch.setattr(knowledge_embeddings, "embed", embed)
    admin = register(client, "retire-queued@example.io")
    org = first_org_id(client, admin)
    document = upload(client, admin, org).json()
    version_id = document["versions"][0]["id"]
    response = client.post(f"/api/v1/orgs/{org}/documents/versions/{version_id}/retire", headers=admin)
    assert response.status_code == 200, response.text
    assert run_worker() == 0
    version = db_session.get(KnowledgeVersion, uuid.UUID(version_id), populate_existing=True)
    assert version.retired_at and not version.current
    embed.assert_not_called()


def test_retiring_running_index_blocks_purge_until_worker_acknowledges(client, db_session, monkeypatch):
    embed = Mock()
    monkeypatch.setattr(knowledge_embeddings, "embed", embed)
    admin = register(client, "retire-running@example.io")
    org = first_org_id(client, admin)
    document = upload(client, admin, org).json()
    version_id = document["versions"][0]["id"]
    index = db_session.scalar(select(KnowledgeIndex).where(KnowledgeIndex.version_id == uuid.UUID(version_id)))
    # A worker claims the job after this request's session cached pending.
    assert index.status == "pending"
    with db_session.get_bind().begin() as connection:
        connection.execute(update(KnowledgeIndex).where(KnowledgeIndex.id == index.id).values(status="running"))
    base = f"/api/v1/orgs/{org}/documents/versions/{version_id}"
    assert client.post(f"{base}/retire", headers=admin).status_code == 200
    assert client.post(f"{base}/purge?confirmed=true", headers=admin).status_code == 409
    with pytest.raises(knowledge_service.KnowledgeError, match="retired"):
        knowledge_service.process_index(db_session, index.id)
    embed.assert_not_called()
    assert client.post(f"{base}/purge?confirmed=true", headers=admin).status_code == 200
