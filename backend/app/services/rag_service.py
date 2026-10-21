"""RAG (Retrieval-Augmented Generation) service for querying compliance standards (CIS/NIST/ISO)."""

import uuid
from typing import Any, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

import app.db.base  # noqa: F401
from app.models.document import Document
from app.services.embedding_service import get_embedding


def retrieve_relevant_standards(
    db: Session,
    query_text: str,
    org_id: uuid.UUID | None = None,
    frameworks: Sequence[str] | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Retrieves top-k relevant standard controls / policy snippets from pgvector
    using cosine similarity.
    Includes shared platform standards (org_id IS NULL) and org-specific policies.
    """
    if not query_text or not query_text.strip():
        return []

    if org_id is not None:
        from app.services.knowledge_service import retrieve
        return retrieve(db, org_id, query_text[:1200], list(frameworks) if frameworks else None, limit)

    query_vector = get_embedding(query_text)

    # Base filter: global platform documents or org-specific documents
    org_filter = or_(Document.org_id.is_(None), Document.org_id == org_id) if org_id else Document.org_id.is_(None)

    stmt = select(
        Document.control_id,
        Document.framework,
        Document.version,
        Document.title,
        Document.content,
        Document.content_ref,
        Document.source,
        Document.embedding.cosine_distance(query_vector).label("distance"),
    ).where(org_filter)

    if frameworks:
        # Filter by requested frameworks (e.g. ['CIS', 'NIST', 'ISO'])
        fw_upper = [f.upper() for f in frameworks]
        stmt = stmt.where(Document.framework.in_(fw_upper))

    stmt = stmt.order_by("distance").limit(limit)

    results = db.execute(stmt).all()

    citations = []
    for r in results:
        citations.append(
            {
                "control_id": r.control_id or "GENERAL",
                "framework": r.framework or "STANDARD",
                "version": r.version or "",
                "title": r.title or "",
                "content": r.content or "",
                "content_ref": r.content_ref or "",
                "source": r.source or "",
                "distance": float(r.distance) if r.distance is not None else 0.0,
            }
        )
    return citations


def retrieve_standards_for_findings(
    db: Session,
    findings_summary: list[dict[str, Any]],
    org_id: uuid.UUID | None = None,
    frameworks: Sequence[str] | None = None,
    max_total: int = 10,
) -> list[dict[str, Any]]:
    """Retrieves relevant standards matching the organization's highest-severity findings."""
    if not findings_summary:
        # Fall back to general resilience controls
        return retrieve_relevant_standards(
            db,
            "cyber resilience identity access vulnerability network backup monitoring incident response",
            org_id=org_id,
            frameworks=frameworks,
            limit=max_total,
        )

    # Build targeted queries per domain/category
    seen_controls = set()
    collected = []

    # 1. Query for the most severe findings
    for finding in findings_summary[:5]:
        text_query = f"{finding.get('domain', '')} {finding.get('category', '')} {finding.get('title', '')} {finding.get('description', '')}"
        matches = retrieve_relevant_standards(
            db, text_query, org_id=org_id, frameworks=frameworks, limit=3
        )
        for m in matches:
            cid = m.get("citation_id", m["control_id"])
            if cid not in seen_controls:
                seen_controls.add(cid)
                collected.append(m)
                if len(collected) >= max_total:
                    break
        if len(collected) >= max_total:
            break

    # If still below max_total, fetch baseline controls
    if len(collected) < max_total:
        baseline = retrieve_relevant_standards(
            db,
            "baseline security configuration account management vulnerability monitoring incident response",
            org_id=org_id,
            frameworks=frameworks,
            limit=max_total - len(collected),
        )
        for m in baseline:
            cid = m.get("citation_id", m["control_id"])
            if cid not in seen_controls:
                seen_controls.add(cid)
                collected.append(m)

    return collected
