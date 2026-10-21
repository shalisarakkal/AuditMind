"""Queue the verified baseline without representing restricted text as available."""

import json
from pathlib import Path
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeDocument
from app.services.knowledge_service import queue_version

NIST_REVISION = "78650f02ad9321bb7b817846f8fbd4f2bcd620de"
NIST_SOURCE = f"https://github.com/usnistgov/oscal-content/blob/{NIST_REVISION}/nist.gov/CSF/v2.0/json/NIST_CSF_v2.0_catalog.json"


def nist_text() -> str:
    path = Path(__file__).resolve().parents[1] / "data" / "nist_csf_2_catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))["catalog"]
    lines = [f"# {catalog['metadata']['title']}", f"OSCAL catalog version: {catalog['metadata']['version']}"]

    def walk(node):
        if node.get("title"):
            lines.append(f"## {node.get('id', '')}: {node['title']}")
        if node.get("prose"):
            lines.append(node["prose"])
        for key in ("groups", "controls", "parts"):
            for child in node.get(key, []):
                walk(child)
    walk(catalog)
    return "\n\n".join(lines)


def queue_baseline(db: Session, actor_id: uuid.UUID) -> list[str]:
    sources = [
        ("NIST CSF 2.0", "NIST", "CSF 2.0 / OSCAL 1.2.0", NIST_SOURCE, "official",
         "NIST OSCAL content: US government public domain / CC0 1.0. No NIST endorsement implied.", nist_text()),
        ("CIS Controls v8.1 — source reference", "CIS", "8.1", "https://www.cisecurity.org/controls/v8-1", "reference",
         "Full text not bundled. Verify licensing before uploading authorized material.",
         "CIS Controls v8.1 source reference. Official full text has not been loaded. Obtain authorized material from CIS and verify permitted processing before upload."),
        ("ISO/IEC 27001:2022 — source reference", "ISO", "2022", "https://www.iso.org/standard/27001", "reference",
         "Copyrighted standard: full text not bundled; authorized import required.",
         "ISO/IEC 27001:2022 source reference. Official full text has not been loaded. Verify your license permits the intended processing before upload."),
        ("ISO/IEC 27002:2022 — source reference", "ISO", "2022", "https://www.iso.org/standard/75652.html", "reference",
         "Copyrighted guidance: full text not bundled; authorized import required.",
         "ISO/IEC 27002:2022 source reference. Official full text has not been loaded. Verify your license permits the intended processing before upload."),
    ]
    ids = []
    for title, framework, edition, source, kind, rights, content in sources:
        document = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.org_id.is_(None), KnowledgeDocument.title == title))
        version = queue_version(db, org_id=None, actor_id=actor_id, title=title, framework=framework,
            edition=edition, source=source, content_kind=kind, rights=rights, content=content,
            document_id=document.id if document else None)
        ids.append(str(version.id))
    return ids
