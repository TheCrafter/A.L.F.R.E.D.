from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.server import create_app


def test_get_config_redacts_and_reports(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_secret")
    app = create_app(Settings(provider="scripted", _env_file=None))
    body = TestClient(app).get("/config").json()["config"]
    assert body["groq_api_key"]["value"] == "set"
    assert "gsk_secret" not in str(body)
    assert body["provider"]["value"] == "scripted"
