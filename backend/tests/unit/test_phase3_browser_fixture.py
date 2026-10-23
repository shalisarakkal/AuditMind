"""Safety guards must reject broad targets before creating an engine/schema."""
from pathlib import Path
import runpy
import sys

import pytest

from app.core.config import settings


@pytest.mark.parametrize('schema', ['public', 'auditmind_demo', 'phase3_browser_bad', 'phase3_browser_aaaaaaaaaaaa;DROP'])
def test_browser_fixture_rejects_non_fixture_schema(monkeypatch, schema):
    monkeypatch.setattr(sys, 'argv', ['fixture', 'cleanup', '--schema', schema])
    with pytest.raises(SystemExit, match='Invalid isolated fixture schema'):
        runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/phase3_browser_fixture.py'), run_name='__main__')


@pytest.mark.parametrize('url', ['sqlite://', 'postgresql://localhost/auditmind',
    'postgresql://remote.example/auditmind_test', 'postgresql://localhost/other_test'])
def test_browser_fixture_rejects_nonlocal_or_wrong_database(monkeypatch, url):
    monkeypatch.setattr(settings, 'TEST_DATABASE_URL', url)
    monkeypatch.setattr(sys, 'argv', ['fixture', 'cleanup', '--schema', 'phase3_browser_aaaaaaaaaaaa'])
    with pytest.raises(SystemExit, match='Local auditmind_test only'):
        runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/phase3_browser_fixture.py'), run_name='__main__')
