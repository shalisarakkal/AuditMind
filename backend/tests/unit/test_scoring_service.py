from app.models.enums import Domain, RiskTier, Severity
from app.models.finding import Finding
from app.services.scoring_service import (
    DOMAIN_WEIGHTS,
    overall_score,
    score_all_domains,
    score_domain,
    tier_for_score,
)


def make_finding(domain: Domain, severity: Severity) -> Finding:
    return Finding(domain=domain, severity=severity, org_id=None)


def test_tier_boundaries():
    assert tier_for_score(100) == RiskTier.low
    assert tier_for_score(80) == RiskTier.low
    assert tier_for_score(79.9) == RiskTier.medium
    assert tier_for_score(60) == RiskTier.medium
    assert tier_for_score(59.9) == RiskTier.high
    assert tier_for_score(40) == RiskTier.high
    assert tier_for_score(39.9) == RiskTier.critical
    assert tier_for_score(0) == RiskTier.critical


def test_score_domain_no_findings_is_perfect_score():
    score, tier, justification = score_domain(Domain.identity_access, [])
    assert score == 100.0
    assert tier == RiskTier.low
    assert "No findings" in justification


def test_score_domain_applies_deductions_for_matching_domain_only():
    findings = [
        make_finding(Domain.identity_access, Severity.critical),
        make_finding(Domain.identity_access, Severity.high),
        make_finding(Domain.network_config, Severity.critical),
    ]
    score, tier, _ = score_domain(Domain.identity_access, findings)
    assert score == 100 - 15 - 7
    assert tier == RiskTier.medium


def test_score_domain_floors_at_zero():
    findings = [make_finding(Domain.identity_access, Severity.critical) for _ in range(10)]
    score, tier, _ = score_domain(Domain.identity_access, findings)
    assert score == 0.0
    assert tier == RiskTier.critical


def test_score_all_domains_covers_every_domain():
    result = score_all_domains([])
    assert set(result.keys()) == set(Domain)
    assert all(score == 100.0 for score, _tier, _just in result.values())


def test_domain_weights_sum_to_one():
    assert round(sum(DOMAIN_WEIGHTS.values()), 6) == 1.0


def test_overall_score_is_weighted_average():
    domain_scores = {domain: (100.0, RiskTier.low, "") for domain in Domain}
    domain_scores[Domain.identity_access] = (0.0, RiskTier.critical, "")

    overall, tier = overall_score(domain_scores)

    expected = 100.0 * (1 - DOMAIN_WEIGHTS[Domain.identity_access])
    assert round(overall, 6) == round(expected, 6)
    assert tier == RiskTier.low
