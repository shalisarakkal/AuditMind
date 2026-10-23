from copy import deepcopy
from types import SimpleNamespace
import pytest
from app.services import report_service as service


@pytest.mark.parametrize("count", [None, 0, 1, 2, 3])
def test_sampling_and_zero_baseline(count):
    data = {"total_findings": 2, "provenance": {"rule_based": {"overall_score": 0, "overall_tier": "critical"}}}
    if count is not None:
        data["provenance"]["sampled_findings"] = [{}] * count
    before = deepcopy(data)
    lines = " ".join(service._assessment_display_lines(data))
    assert "baseline: 0/100" in lines
    assert ("All counted findings" in lines) == (count == 2)
    assert ("did not receive every finding" in lines) == (count is not None and count < 2)
    assert data == before


def test_export_interpretation_escaping_and_pdf(monkeypatch):
    data = {"total_findings": 0, "provenance": {"evidence_limitation": "<script>untrusted</script>"}}
    report = SimpleNamespace(title="Synthetic", frameworks=None, generated_at=None, data=data)
    html = service.render_report_html(report)
    assert "AI resilience score (advisory)" in html
    assert "baseline: not recorded" in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    seen = []
    original = service.Paragraph
    def capture(text, style):
        seen.append(text)
        return original(text, style)
    monkeypatch.setattr(service, "Paragraph", capture)
    assert service.render_report_pdf(report).startswith(b"%PDF")
    assert any("AI resilience score (advisory)" in text for text in seen)
    assert any("not a calibrated probability" in text for text in seen)
    data["provenance"] = {"assessment_type": "rule_based_test"}
    assert "AI resilience score (advisory)" not in service.render_report_html(report)
