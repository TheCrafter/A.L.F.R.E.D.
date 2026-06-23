from pathlib import Path

from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.server import create_app


def _write_home(monkeypatch, tmp_path, body: str) -> None:
    home = tmp_path / "alfred-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(body, encoding="utf-8")
    monkeypatch.setenv("ALFRED_HOME", str(home))


def test_reload_applies_hot_fields(tmp_path, monkeypatch):
    app = create_app(Settings(provider="scripted", persona_intensity="full", _env_file=None))
    client = TestClient(app)
    _write_home(monkeypatch, tmp_path,
                "[persona]\nintensity = \"off\"\n[agent]\nmax_tool_iterations = 2\n")
    body = client.post("/config/reload").json()
    assert "persona_intensity" in body["changed"]
    assert "max_tool_iterations" in body["changed"]
    assert app.state.agent._max_iterations == 2


def test_reload_reports_startup_only_pending(tmp_path, monkeypatch):
    app = create_app(Settings(port=8766, _env_file=None))
    client = TestClient(app)
    _write_home(monkeypatch, tmp_path, "[server]\nport = 9123\n")
    body = client.post("/config/reload").json()
    assert "port" in body["startup_only_pending"]


def test_invalid_reload_is_rejected_and_keeps_old(tmp_path, monkeypatch):
    app = create_app(Settings(persona_intensity="full", _env_file=None))
    client = TestClient(app)
    _write_home(monkeypatch, tmp_path, "[persona]\nintensity = \"bogus\"\n")
    resp = client.post("/config/reload")
    assert resp.status_code == 400
    # unchanged
    assert app.state.agent._system  # still the original system prompt


def test_reload_provider_change_is_reflected_in_models(tmp_path, monkeypatch):
    # start on groq (key present), reload to scripted; /models must follow.
    app = create_app(Settings(provider="groq", groq_api_key="x", _env_file=None))
    client = TestClient(app)
    assert client.get("/models").json()["current"]["provider"] == "groq"
    _write_home(monkeypatch, tmp_path, "[reasoning]\nprovider = \"scripted\"\n")
    client.post("/config/reload")
    assert client.get("/models").json()["current"]["provider"] == "scripted"
