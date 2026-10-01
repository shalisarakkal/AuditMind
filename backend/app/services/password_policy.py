"""Checking a new password against the password rule (Simple or Complex,
services/security_policy.py). No database: the caller passes the current
password's hash and the history to compare with.

Lengths count characters, whatever the script: "日本語" is 3, though 9
bytes. Passwords are compared in one normalized form (core/security.py).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.core.security import normalize_password, verify_password
from app.services.security_policy import PasswordRules


@dataclass(frozen=True)
class Problem:
    code: str
    message: str


def check_password(
    password: str,
    rules: PasswordRules,
    *,
    email: str,
    current_hash: str | None = None,
    history_hashes: Sequence[str] = (),
    required_by: dict[str, str] | None = None,
) -> list[Problem]:
    """Every way `password` breaks the rules (none: it's fine).
    history_hashes: the previous passwords, newest first; the rule's
    history_count of them are checked."""
    required_by = required_by or {}

    def why(setting: str, message: str) -> str:
        org = required_by.get(setting)
        return f"{message} (required by {org})" if org else message

    password = normalize_password(password)
    problems: list[Problem] = []
    if len(password) < rules.min_length:
        problems.append(Problem("too_short", why("min_length", f"Use at least {rules.min_length} characters")))
    if len(password) > rules.max_length:
        problems.append(Problem("too_long", f"Use at most {rules.max_length} characters"))
    if password.casefold() == email.casefold():
        problems.append(Problem("is_email", "Don't use your email address as your password"))
    for setting, test, message in (
        ("require_upper", str.isupper, "Include an upper-case letter (such as A)"),
        ("require_lower", str.islower, "Include a lower-case letter (such as a)"),
        ("require_digit", str.isdigit, "Include a digit (0-9)"),
        ("require_symbol", lambda ch: not ch.isalnum(), "Include a symbol (such as ! or #)"),
    ):
        if getattr(rules, setting) and not any(test(ch) for ch in password):
            problems.append(Problem(setting.removeprefix("require_"), why(setting, message)))

    if current_hash and verify_password(password, current_hash):
        problems.append(Problem("is_current", "Choose a password different from your current one"))
    elif any(verify_password(password, h) for h in history_hashes[: rules.history_count]):
        problems.append(
            Problem("reused", why("history_count", f"Don't reuse any of your last {rules.history_count} passwords"))
        )
    return problems
