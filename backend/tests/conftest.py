import pytest

from backend.seed import seed


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    """Give each test its own freshly seeded database."""
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "test.db"))
    seed()
