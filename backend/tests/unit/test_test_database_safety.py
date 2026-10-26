"""Protect destructive test fixtures against invalid or development targets."""

import pytest
from types import SimpleNamespace

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


@pytest.mark.parametrize('required, available', [(False, False), (False, True), (True, True), (True, False)])
def test_required_postgres_fails_before_test_execution(monkeypatch, required, available):
    from tests import conftest
    monkeypatch.setattr(conftest, 'DB_AVAILABLE', available)
    session = SimpleNamespace(config=SimpleNamespace(getoption=lambda name: required))
    if required and not available:
        with pytest.raises(pytest.UsageError, match='PostgreSQL test database is required'):
            conftest.pytest_sessionstart(session)
    else:
        conftest.pytest_sessionstart(session)


@pytest.mark.parametrize('required, skipped, failed', [(True, True, True), (True, False, False), (False, True, False)])
def test_required_postgres_does_not_silently_accept_skips(required, skipped, failed):
    from tests import conftest
    reporter = SimpleNamespace(stats={'skipped': [object()]} if skipped else {})
    config = SimpleNamespace(getoption=lambda name: required,
        pluginmanager=SimpleNamespace(getplugin=lambda name: reporter))
    session = SimpleNamespace(config=config, exitstatus=pytest.ExitCode.OK)
    conftest.pytest_sessionfinish(session, 0)
    assert (session.exitstatus == pytest.ExitCode.TESTS_FAILED) is failed


@pytest.mark.parametrize('module_name', ['httpx', 'httpx2'])
def test_real_http_requires_an_explicit_mock_transport(module_name):
    from importlib import import_module
    transport_module = import_module(module_name)
    with transport_module.Client(trust_env=False) as client:
        with pytest.raises(AssertionError, match='Real HTTP forbidden'):
            client.get('https://inference.invalid')


@pytest.mark.parametrize('module_name', ['httpx', 'httpx2'])
def test_real_async_http_requires_an_explicit_mock_transport(module_name):
    import asyncio
    from importlib import import_module
    transport_module = import_module(module_name)

    async def request():
        async with transport_module.AsyncClient(trust_env=False) as client:
            with pytest.raises(AssertionError, match='Real HTTP forbidden'):
                await client.get('https://inference.invalid')

    asyncio.run(request())
