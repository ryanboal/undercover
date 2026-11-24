import pytest
from fastapi.testclient import TestClient

from agent import __main__ as cli
from agent import api, harness
from backend.main import app
from backend.tests.conftest import client, database

BASE_URL = "http://testserver/api"

__all__ = ["client", "database"]


@pytest.fixture(autouse=True)
def backend(monkeypatch):
    """Send the agent's requests to the test backend."""
    monkeypatch.setattr(api, "client", lambda: TestClient(app, BASE_URL))
    monkeypatch.setattr(harness, "RETRY_DELAY", 0)
    monkeypatch.setattr(api, "CONNECT_DELAYS", (0, 0, 0))
    monkeypatch.setattr(cli, "LOCK_PORT", 0)
