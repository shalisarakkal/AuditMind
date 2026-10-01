import pytest
from pydantic import ValidationError

from app.services.security_policy import (
    PasswordRules,
    SecuritySettings,
    apply_changes,
    combine,
)

DEFAULTS = SecuritySettings()


def org(**changes) -> SecuritySettings:
    return apply_changes(DEFAULTS, changes)


def test_one_layer_is_taken_as_it_is():
    policy = combine([(None, DEFAULTS)])
    assert (policy.idle_minutes, policy.max_session_days) == (480, 7)
    assert (policy.lockout_threshold, policy.lockout_window_minutes, policy.lock_minutes) == (5, 15, 15)
    assert policy.password == PasswordRules()  # Simple: 12 to 128, nothing else
    assert policy.required_by == {}


def test_the_strictest_value_of_each_setting_wins_and_names_its_org():
    policy = combine(
        [
            ("Acme", org(idle_minutes=30, max_session_days=10)),
            ("Beta", org(idle_minutes=120, max_session_days=2)),
        ]
    )
    assert (policy.idle_minutes, policy.max_session_days) == (30, 2)
    assert policy.required_by == {"idle_minutes": "Acme", "max_session_days": "Beta"}


@pytest.mark.parametrize(
    "a, b, expected",
    [
        (0, 6, 6),  # 0 = never locks: any limit is stricter
        (3, 6, 3),
        (0, 0, 0),
    ],
)
def test_lockout_threshold_zero_means_never(a, b, expected):
    assert combine([("A", org(lockout_threshold=a)), ("B", org(lockout_threshold=b))]).lockout_threshold == expected


@pytest.mark.parametrize("a, b, expected", [(10, 20, 20), (0, 20, 0), (20, 0, 0)])
def test_a_lock_until_an_admin_unlocks_beats_any_duration(a, b, expected):
    assert combine([("A", org(lock_minutes=a)), ("B", org(lock_minutes=b))]).lock_minutes == expected


def test_complex_beats_simple_and_brings_its_rules():
    policy = combine(
        [
            ("Simple Co", org()),
            ("Strict Co", org(password_rule="complex", min_length=16, require_symbol=False, expiry_days=90)),
        ]
    )
    assert policy.password == PasswordRules(
        rule="complex",
        min_length=16,
        require_upper=True,
        require_lower=True,
        require_digit=True,
        require_symbol=False,
        history_count=5,
        expiry_days=90,
    )
    assert policy.required_by["min_length"] == "Strict Co"
    assert "require_symbol" not in policy.required_by  # both orgs agree: not required


def test_expiry_never_loses_to_any_expiry():
    policy = combine(
        [
            ("A", org(password_rule="complex", expiry_days=0)),
            ("B", org(password_rule="complex", expiry_days=365)),
            ("C", org(password_rule="complex", expiry_days=30)),
        ]
    )
    assert (policy.password.expiry_days, policy.required_by["expiry_days"]) == (30, "C")


def test_a_simple_orgs_complex_settings_dont_apply():
    # Stored Complex settings of an org on Simple don't count.
    policy = combine([("A", org(password_rule="simple", min_length=40))])
    assert policy.password.min_length == 12


@pytest.mark.parametrize(
    "changes",
    [
        {"idle_minutes": 9},
        {"idle_minutes": 601},
        {"max_session_days": 1},
        {"max_session_days": 11},
        {"lockout_threshold": 2},
        {"lockout_threshold": 7},
        {"lockout_window_minutes": 9},
        {"lock_minutes": 5},
        {"lock_minutes": 21},
        {"min_length": 11},
        {"min_length": 65},
        {"history_count": 25},
        {"expiry_days": 29},
        {"expiry_days": 366},
        {"password_rule": "medium"},
        {"unknown_setting": 1},
    ],
)
def test_settings_outside_the_ranges_are_refused(changes):
    with pytest.raises(ValidationError):
        org(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"idle_minutes": 10},
        {"idle_minutes": 600},
        {"lockout_threshold": 0},
        {"lockout_threshold": 3},
        {"lock_minutes": 0},
        {"lock_minutes": 20},
        {"expiry_days": 0},
        {"expiry_days": 365},
    ],
)
def test_the_ends_of_each_range_are_allowed(changes):
    org(**changes)
