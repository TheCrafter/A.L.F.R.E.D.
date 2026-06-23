from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.server import create_app


def test_models_lists_scripted_and_reports_current():
    c = TestClient(create_app(Settings(provider="scripted", _env_file=None)))
    body = c.get("/models").json()
    assert body["current"] == {"provider": "scripted", "model": "scripted"}
    assert {"provider": "scripted", "model": "scripted"} in body["available"]


def test_models_lists_groq_only_when_key_present():
    with_key = TestClient(create_app(Settings(provider="scripted", groq_api_key="x", _env_file=None)))
    providers = {m["provider"] for m in with_key.get("/models").json()["available"]}
    assert "groq" in providers

    without = TestClient(create_app(Settings(provider="scripted", _env_file=None)))
    providers = {m["provider"] for m in without.get("/models").json()["available"]}
    assert "groq" not in providers and "gemini" not in providers


def test_switch_model_swaps_the_active_provider():
    app = create_app(Settings(provider="scripted", groq_api_key="x", _env_file=None))
    c = TestClient(app)
    r = c.post("/models", json={"provider": "groq", "model": "llama-3.3-70b-versatile"})
    assert r.status_code == 200
    assert r.json()["current"] == {"provider": "groq", "model": "llama-3.3-70b-versatile"}
    from alfred_brain.providers.groq import GroqProvider
    assert isinstance(app.state.agent._provider, GroqProvider)


def test_switch_to_keyless_provider_is_rejected():
    app = create_app(Settings(provider="scripted", _env_file=None))
    c = TestClient(app)
    r = c.post("/models", json={"provider": "gemini", "model": "gemini-2.5-flash"})
    assert r.status_code == 400
