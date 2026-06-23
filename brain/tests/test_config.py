from alfred_brain.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.provider == "gemini"
    assert s.port == 8766
    assert s.persona_intensity == "full"
    assert s.max_tool_iterations == 5
    assert s.gemini_model == "gemini-2.5-flash"


def test_env_override(monkeypatch):
    monkeypatch.setenv("ALFRED_PROVIDER", "scripted")
    monkeypatch.setenv("ALFRED_PORT", "9999")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    s = Settings(_env_file=None)
    assert s.provider == "scripted"
    assert s.port == 9999
    assert s.gemini_api_key == "secret"


def test_kwargs_override():
    s = Settings(provider="scripted", port=0, _env_file=None)
    assert s.provider == "scripted"
    assert s.port == 0
