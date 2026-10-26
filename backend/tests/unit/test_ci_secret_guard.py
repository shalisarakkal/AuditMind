import runpy
from pathlib import Path

import pytest

PATTERNS = runpy.run_path(str(Path(__file__).resolve().parents[3] / "scripts/check_tracked_secrets.py"))["PATTERNS"]


@pytest.mark.parametrize("value", ["sk" + "-" + "x" * 32, "ghp" + "_" + "x" * 35,
                                    "AK" + "IA" + "A" * 16])
def test_provider_patterns_detect_without_exposing_values(value):
    assert any(pattern.search(value) for pattern in PATTERNS)


def test_plain_risk_words_are_not_provider_tokens():
    assert not any(pattern.search("risk-management-and-dashboard-regression-check") for pattern in PATTERNS)
