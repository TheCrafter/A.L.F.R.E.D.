import pytest


@pytest.fixture(autouse=True)
def isolate_alfred_home(tmp_path, monkeypatch):
    """Point $ALFRED_HOME at an empty temp dir so no test reads/writes ~/.alfred."""
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "alfred-home"))
    yield
