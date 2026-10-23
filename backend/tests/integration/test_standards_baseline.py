"""Real PostgreSQL baseline ingestion; restricted references never become evidence."""
from sqlalchemy import func, select

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeIndex, KnowledgeVersion
from app.models.user import User
from app.services import knowledge_embeddings
from tests.conftest import requires_db
from tests.helpers import first_org_id, register, run_worker


@requires_db
def test_shared_baseline_permissions_publication_and_repeat_loading(client, db_session, monkeypatch):
    headers = register(client, 'baseline-owner@example.io')
    org = first_org_id(client, headers)
    endpoint = '/api/v1/platform/documents/load-baseline'
    assert client.post(endpoint, headers=headers).status_code == 403
    root = db_session.scalar(select(User).where(User.email == 'baseline-owner@example.io'))
    root.is_sysadmin = True
    db_session.commit()
    monkeypatch.setattr(knowledge_embeddings, 'embed', lambda profile, texts, **kw: [[1.0] + [0.0] * 1023 for _ in texts])
    first = client.post(endpoint, headers=headers)
    assert first.status_code == 202, first.text
    assert len(first.json()['version_ids']) == 4
    assert run_worker() == 4
    documents = db_session.scalars(select(KnowledgeDocument).where(KnowledgeDocument.org_id.is_(None))).all()
    assert len(documents) == 4
    for document in documents:
        version = db_session.scalar(select(KnowledgeVersion).where(KnowledgeVersion.document_id == document.id))
        assert version.current
        chunks = db_session.scalar(select(func.count()).select_from(KnowledgeChunk).join(KnowledgeIndex)
            .where(KnowledgeIndex.version_id == version.id))
        if document.framework == 'NIST':
            assert version.content_kind == 'official' and chunks > 0
            assert 'OSCAL catalog version:' in version.content
            assert '78650f02ad9321bb7b817846f8fbd4f2bcd620de' in version.source
        else:
            assert version.content_kind == 'reference' and chunks == 0
            assert 'full text' in version.content.lower()
    repeated = client.post(endpoint, headers=headers)
    assert repeated.status_code == 202
    assert repeated.json()['version_ids'] == first.json()['version_ids']
    assert db_session.scalar(select(func.count()).select_from(KnowledgeVersion)) == 4
    assert run_worker() == 0
    # A regular organization member can retrieve only the published shared NIST
    # source, never the unlicensed CIS/ISO reference placeholders.
    member_headers = register(client, 'baseline-reader@example.io')
    member_org = first_org_id(client, member_headers)
    found = client.post(f'/api/v1/orgs/{member_org}/documents/search', headers=member_headers,
        json={'query': 'governance', 'frameworks': ['NIST', 'CIS', 'ISO']})
    assert found.status_code == 200
    assert found.json()['items']
    assert {item['framework'] for item in found.json()['items']} == {'NIST'}
