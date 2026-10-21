import json
import uuid
import asyncio
from io import BytesIO
from datetime import datetime, timezone
from types import SimpleNamespace
from zipfile import ZipFile

from app.api.routes.reports import download_report
from app.models.enums import ReportStatus
from app.services.report_service import render_report_html, render_report_pdf


def test_render_report_html_escapes_untrusted_report_content():
    report = SimpleNamespace(
        title='<script>alert("title")</script>',
        frameworks="CIS",
        generated_at=datetime.now(timezone.utc),
        data={
            "executive_summary": "<script>alert('summary')</script>",
            "resilience_summary": "Safe & sound",
            "domains": [],
            "remediations": [],
            "compliance_citations": [
                {
                    "control_id": "<img src=x>",
                    "framework": "CIS",
                    "title": "<script>alert('citation')</script>",
                    "content": "A & B",
                }
            ],
        },
    )

    rendered = render_report_html(report)

    assert "<script>" not in rendered
    assert "<img src=x>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "A &amp; B" in rendered


def test_json_report_download_serializes_snapshot():
    report = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        status=ReportStatus.completed,
        data={"executive_summary": "Ready", "overall_score": 82},
    )
    db = SimpleNamespace(get=lambda model, report_id: report)

    response = download_report(
        org_id=report.org_id,
        report_id=report.id,
        format="json",
        db=db,
        _=None,
    )

    assert response.media_type == "application/json"
    assert json.loads(response.body) == report.data


def test_pdf_report_download_returns_a_pdf_attachment():
    report = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        title="Annual Audit",
        frameworks="CIS",
        status=ReportStatus.completed,
        generated_at=datetime.now(timezone.utc),
        data={
            "overall_score": 82,
            "overall_tier": "low",
            "executive_summary": "A sample audit summary.",
            "resilience_summary": "A sample resilience summary.",
            "domains": [],
            "remediations": [],
            "compliance_citations": [],
            "provenance": {"assessment_type": "ai", "model": "test-model"},
        },
    )
    db = SimpleNamespace(get=lambda model, report_id: report)

    response = download_report(
        org_id=report.org_id,
        report_id=report.id,
        format="pdf",
        db=db,
        _=None,
    )

    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"].endswith(f"{report.id}.pdf\"")
    assert response.body.startswith(b"%PDF-")


def test_bulk_report_download_contains_each_selected_pdf():
    reports = [
        SimpleNamespace(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            title=title,
            frameworks="CIS",
            status=ReportStatus.completed,
            generated_at=datetime.now(timezone.utc),
            data={"overall_score": 70, "executive_summary": title, "domains": []},
        )
        for title in ("Annual Audit", "Quarterly Audit")
    ]
    db = SimpleNamespace(
        scalars=lambda statement: SimpleNamespace(all=lambda: list(reports)),
    )

    from app.api.routes.reports import ReportBulkDownloadRequest, bulk_download_reports

    response = bulk_download_reports(
        org_id=reports[0].org_id,
        payload=ReportBulkDownloadRequest(ids=[report.id for report in reports]),
        db=db,
        _=None,
    )
    async def read_archive():
        return b"".join([chunk async for chunk in response.body_iterator])

    archive_content = asyncio.run(read_archive())

    assert response.media_type == "application/zip"
    with ZipFile(BytesIO(archive_content)) as archive:
        assert len(archive.namelist()) == 2
        for report in reports:
            pdf = archive.read(next(name for name in archive.namelist() if str(report.id) in name))
            assert pdf.startswith(b"%PDF-")
