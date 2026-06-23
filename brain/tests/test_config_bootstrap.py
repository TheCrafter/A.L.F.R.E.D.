from pathlib import Path

from alfred_brain.config import bootstrap_config, render_template


def test_template_documents_allowed_values_and_catalog():
    body = render_template({})
    assert "full | light | off" in body
    assert "groq | gemini | scripted" in body
    assert "llama-3.3-70b-versatile" in body   # from the registry catalog
    assert "gemini-2.5-flash" in body
    assert "DEBUG | INFO | WARNING | ERROR | CRITICAL" in body


def test_bootstrap_writes_seeded_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "h"))
    monkeypatch.setenv("ALFRED_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_seeded")
    path = bootstrap_config()
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert 'provider = "groq"' in text
    assert "gsk_seeded" in text


def test_bootstrap_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "h"))
    path = (tmp_path / "h")
    path.mkdir(parents=True)
    (path / "config.toml").write_text("[reasoning]\nprovider = \"scripted\"\n", encoding="utf-8")
    bootstrap_config()
    assert 'provider = "scripted"' in (path / "config.toml").read_text(encoding="utf-8")


def test_bootstrap_survives_unwritable_home(tmp_path, monkeypatch):
    # point home at a path whose parent is a file -> mkdir fails
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("ALFRED_HOME", str(blocker / "nested"))
    bootstrap_config()  # must not raise
