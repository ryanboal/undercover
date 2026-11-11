import pytest
from fastapi.testclient import TestClient

from agent import tools
from backend.main import app
from backend.seed import seed


@pytest.fixture(autouse=True)
def backend(tmp_path, monkeypatch):
    """Give each test a freshly seeded database, and point the agent at the app."""
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "test.db"))
    seed()
    monkeypatch.setattr(tools, "backend", lambda: TestClient(app))
