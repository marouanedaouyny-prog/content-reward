"""Integration tests use fixtures instead of starting outbound research scans."""
import pytest


@pytest.fixture(autouse=True)
def isolate_background_research(monkeypatch):
    monkeypatch.setenv('CLIPPING_TREND_AGENT', 'false')
