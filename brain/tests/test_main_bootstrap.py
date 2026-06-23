from alfred_brain.__main__ import load_settings


def test_load_settings_bootstraps_then_reads(tmp_path, monkeypatch):
    home = tmp_path / "alfred-home"
    monkeypatch.setenv("ALFRED_HOME", str(home))
    monkeypatch.setenv("ALFRED_PROVIDER", "scripted")
    settings = load_settings()
    assert (home / "config.toml").is_file()      # bootstrap ran
    assert settings.provider == "scripted"        # env still wins


def test_load_settings_migrates_dotenv_into_config(tmp_path, monkeypatch):
    # a dev .env in the working dir must be seeded into config.toml on first run
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / ".env").write_text("GROQ_API_KEY=gsk_from_dotenv\n", encoding="utf-8")
    monkeypatch.chdir(workdir)
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)  # don't let a real env var shadow it
    load_settings()
    text = (tmp_path / "home" / "config.toml").read_text(encoding="utf-8")
    assert "gsk_from_dotenv" in text
