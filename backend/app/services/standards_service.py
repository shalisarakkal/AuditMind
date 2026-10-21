"""Standards service for seeding, managing, and retrieving compliance controls."""

import logging
import uuid
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import app.db.base  # noqa: F401
from app.data.standards_corpus import STANDARDS_DATA
from app.models.document import Document
from app.services.embedding_service import get_embedding


logger = logging.getLogger("app.standards")


def seed_standards_knowledge_base(db: Session, force_refresh: bool = False) -> int:
    """Seeds the platform-wide compliance standards (CIS/NIST/ISO) into the
    documents table with 1536-dim embeddings.
    If force_refresh is True, existing global standard documents are replaced.
    Returns the number of standards added/updated.
    """
    existing_count = db.scalar(
        select(Document).where(Document.org_id.is_(None), Document.type == "standard")
    )

    if existing_count and not force_refresh:
        logger.info("Standards knowledge base already seeded.")
        return 0

    if force_refresh:
        db.execute(
            delete(Document).where(Document.org_id.is_(None), Document.type == "standard")
        )

    count = 0
    for item in STANDARDS_DATA:
        # Check if already exists by control_id
        control_id = item.get("control_id")
        existing = db.execute(
            select(Document).where(
                Document.org_id.is_(None),
                Document.control_id == control_id,
            )
        ).scalar_one_or_none()

        full_text = f"{item['title']}. {item['content_ref']}: {item['content']}"
        vector = get_embedding(full_text)

        if existing:
            existing.title = item["title"]
            existing.content = item["content"]
            existing.content_ref = item["content_ref"]
            existing.framework = item["framework"]
            existing.version = item["version"]
            existing.source = item["source"]
            existing.embedding = vector
        else:
            doc = Document(
                id=uuid.uuid4(),
                org_id=None,  # Shared platform standard
                type="standard",
                source=item["source"],
                title=item["title"],
                content=item["content"],
                content_ref=item["content_ref"],
                framework=item["framework"],
                control_id=item["control_id"],
                version=item["version"],
                embedding=vector,
            )
            db.add(doc)
        count += 1

    db.commit()
    logger.info(f"Seeded {count} standard controls into pgvector knowledge base.")
    return count
