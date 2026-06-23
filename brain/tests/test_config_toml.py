from pathlib import Path

from alfred_brain.config import Settings


def _write(tmp_path: Path, body: str) -> None:
    home = tmp_path / "alfred-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(body, encoding="utf-8")


def test_file_values_load_and_flatten(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "alfred-home"))
    _write(tmp_path, """
[server]
port = 9100
[reasoning]
provider = "scripted"
[persona]
intensity = "light"
[logging]
level = "WARNING"
""")
    s = Settings(_env_file=None)
    assert s.port == 9100
    assert s.provider == "scripted"
    assert s.persona_intensity == "light"
    assert s.log_level == "WARNING"


def test_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "alfred-home"))
    _write(tmp_path, "[reasoning]\nprovider = \"scripted\"\n")
    monkeypatch.setenv("ALFRED_PROVIDER", "groq")
    s = Settings(_env_file=None)
    assert s.provider == "groq"  # env wins over file


def test_unknown_keys_tolerated(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "alfred-home"))
    _write(tmp_path, "[mystery]\nwidgets = 3\n[reasoning]\nprovider = \"scripted\"\n")
    s = Settings(_env_file=None)  # must not raise
    assert s.provider == "scripted"
