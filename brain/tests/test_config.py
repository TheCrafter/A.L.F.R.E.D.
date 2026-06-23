import pytest
from pydantic import ValidationError

from alfred_brain.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.provider == "gemini"
    assert s.port == 8766
    assert s.persona_intensity == "full"
    assert s.max_tool_iterations == 5
    assert s.gemini_model == "gemini-2.5-flash"
    assert s.log_level == "INFO"


def test_env_override(monkeypatch):
    monkeypatch.setenv("ALFRED_PROVIDER", "scripted")
    monkeypatch.setenv("ALFRED_PORT", "9999")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    monkeypatch.setenv("ALFRED_LOG_LEVEL", "DEBUG")
    s = Settings(_env_file=None)
    assert s.provider == "scripted"
    assert s.port == 9999
    assert s.gemini_api_key == "secret"
    assert s.log_level == "DEBUG"


def test_kwargs_override():
    s = Settings(provider="scripted", port=1234, _env_file=None)
    assert s.provider == "scripted"
    assert s.port == 1234


def test_invalid_enum_rejected():
    with pytest.raises(ValidationError):
        Settings(persona_intensity="ful", _env_file=None)


def test_invalid_port_rejected():
    with pytest.raises(ValidationError):
        Settings(port=0, _env_file=None)
