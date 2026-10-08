import pytest


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """Every test gets its own database and results folder, never the real ones."""
    monkeypatch.setenv("QFLOW_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("QFLOW_RESULTS", str(tmp_path / "results"))
