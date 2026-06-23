from pathlib import Path

from alfred_brain.config import Settings, effective_config


def test_redacts_secrets_and_reports_sources(tmp_path, monkeypatch):
    home = tmp_path / "alfred-home"
    home.mkdir(parents=True)
    (home / "config.toml").write_text("[persona]\nintensity = \"light\"\n", encoding="utf-8")
    monkeypatch.setenv("ALFRED_HOME", str(home))
    monkeypatch.setenv("ALFRED_PROVIDER", "scripted")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_secret")

    s = Settings(_env_file=None)
    view = effective_config(s)

    assert view["groq_api_key"]["value"] == "set"        # redacted, not the key
    assert "gsk_secret" not in str(view)
    assert view["gemini_api_key"]["value"] == "unset"
    assert view["provider"]["source"] == "env"           # env var set
    assert view["persona_intensity"]["source"] == "file" # only in the file
    assert view["port"]["source"] == "default"           # nowhere set
