"""Protect destructive test fixtures against invalid or development targets."""

import pytest

from tests.conftest import _is_test_db


@pytest.mark.parametrize("url, safe", [
    (None, False),
    ("", False),
    ("not a URL", False),
    ("postgresql+psycopg://localhost:invalid/auditmind_test", False),
    ("sqlite:///auditmind_test", False),
    ("postgresql+psycopg://localhost/auditmind", False),
    ("postgresql+psycopg://localhost/auditmind_test", True),
    ("postgresql://localhost/another_test", True),
])
def test_only_postgres_test_database_names_are_accepted(url, safe):
    assert _is_test_db(url) is safe
