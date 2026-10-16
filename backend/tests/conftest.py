# WHAT THIS FILE IS FOR: shared setup for the automatic tests.
# pytest (the tool that runs the tests) loads it before every test file.
import pytest


# Points each test at a throwaway database and results folder, so tests never touch real data.
@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """Every test gets its own database and results folder, never the real ones."""
    monkeypatch.setenv("QFLOW_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("QFLOW_RESULTS", str(tmp_path / "results"))
