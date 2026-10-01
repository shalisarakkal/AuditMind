import unicodedata

import pytest

from app.core.security import hash_password, pwd_context, verify_password
from app.services.password_policy import check_password
from app.services.security_policy import PasswordRules

SIMPLE = PasswordRules()
COMPLEX = PasswordRules(
    rule="complex",
    min_length=14,
    require_upper=True,
    require_lower=True,
    require_digit=True,
    require_symbol=True,
    history_count=2,
)
EMAIL = "ann@acme.io"


def codes(password, rules=SIMPLE, **kwargs):
    return [p.code for p in check_password(password, rules, email=EMAIL, **kwargs)]


def test_simple_is_length_only():
    assert codes("abcdefghijkl") == []
    assert codes("abcdefghijk") == ["too_short"]
    assert codes("a" * 128) == []
    assert codes("a" * 129) == ["too_long"]


def test_not_the_email():
    assert codes("Ann@Acme.io") == ["too_short", "is_email"]
    assert codes(EMAIL, PasswordRules(min_length=1)) == ["is_email"]


def test_complex_lists_every_missing_kind():
    assert codes("abcdefghijklmn", COMPLEX) == ["upper", "digit", "symbol"]
    assert codes("Abcdefghijk1!x", COMPLEX) == []


def test_length_counts_characters_not_bytes():
    # 12 Japanese characters: 36 bytes in UTF-8, but 12 characters.
    password = "日本語のパスワードです。"
    assert len(password) == 12 and len(password.encode()) == 36
    assert codes(password) == []
    assert codes("日本語" * 43) == ["too_long"]  # 129 characters


def test_scripts_without_case_need_a_latin_capital_when_required():
    rules = PasswordRules(rule="complex", min_length=12, require_upper=True)
    assert codes("മലയാളംപാസ്‌വേഡ്", rules) == ["upper"]
    assert codes("മലയാളംപാസ്‌വേഡ്A", rules) == []
    assert codes("Δελταβήταγάμμα", rules) == []  # Greek has case


def test_not_the_current_password_nor_a_recent_one():
    current, older, oldest, ancient = (hash_password(p) for p in ("Current-pass-1", "Older-pass-12", "Oldest-pass-1", "Ancient-pass-1"))
    kwargs = {"current_hash": current, "history_hashes": [older, oldest, ancient]}
    assert codes("Current-pass-1", COMPLEX, **kwargs) == ["is_current"]
    assert codes("Older-pass-12", COMPLEX, **kwargs) == ["too_short", "reused"]
    assert codes("Oldest-pass-1", COMPLEX, **kwargs) == ["too_short", "reused"]
    # history_count 2: the third one back may be used again.
    assert codes("Ancient-pass-1", COMPLEX, **kwargs) == []
    # Simple keeps no history, only "not the current one".
    assert codes("Older-pass-12", SIMPLE, **kwargs) == []


def test_messages_name_the_org_that_asks():
    [problem] = check_password("short", PasswordRules(min_length=16), email=EMAIL, required_by={"min_length": "Acme"})
    assert problem.message == "Use at least 16 characters (required by Acme)"


@pytest.mark.parametrize("password", ["ü" * 128, "日本語" * 42 + "ab", "🔐" * 100])
def test_every_character_of_a_long_multibyte_password_counts(password):
    """Plain bcrypt reads only the first 72 bytes (24 three-byte characters):
    a password differing after them would be accepted."""
    stored = hash_password(password)
    assert len(stored) <= 255
    assert verify_password(password, stored)
    assert not verify_password(password[:-1] + "x", stored)


def test_a_password_typed_in_another_form_still_matches():
    composed = unicodedata.normalize("NFC", "Café-crème-2026")
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    assert verify_password(decomposed, hash_password(composed))


def test_hashes_from_before_still_verify_and_are_replaced():
    legacy = pwd_context.handler("bcrypt").hash("Sup3rSecret!")
    assert verify_password("Sup3rSecret!", legacy)
    assert pwd_context.needs_update(legacy)
    assert not pwd_context.needs_update(hash_password("Sup3rSecret!"))
