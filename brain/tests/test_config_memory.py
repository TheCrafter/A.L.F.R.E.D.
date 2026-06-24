import pytest
from pydantic import ValidationError

from alfred_brain.config import Settings
from alfred_brain.config.bootstrap import render_template


def test_memory_defaults():
    s = Settings(_env_file=None)
    assert s.memory_vault_dir is None
    assert s.memory_embed_model == "BAAI/bge-small-en-v1.5"
    assert s.memory_recall_top_k == 5


def test_memory_from_toml(tmp_path, monkeypatch):
    home = tmp_path / "alfred-home"
    home.mkdir(parents=True)
    (home / "config.toml").write_text(
        "[memory]\nrecall_top_k = 9\nembed_model = \"x\"\n", encoding="utf-8")
    monkeypatch.setenv("ALFRED_HOME", str(home))
    s = Settings(_env_file=None)
    assert s.memory_recall_top_k == 9
    assert s.memory_embed_model == "x"


def test_recall_top_k_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(memory_recall_top_k=0, _env_file=None)


def test_template_documents_memory_section():
    body = render_template({})
    assert "[memory]" in body
    assert "recall_top_k" in body
    assert "embed_model" in body


def test_formation_defaults(monkeypatch):
    for v in ("ALFRED_WINDOW_MESSAGES", "ALFRED_EXTRACT_MODEL", "ALFRED_EXTRACT_RECALL_K"):
        monkeypatch.delenv(v, raising=False)
    from alfred_brain.config import Settings
    s = Settings(_env_file=None)
    assert s.memory_window_messages == 20
    assert s.memory_extract_model == ""
    assert s.memory_extract_recall_k == 5


def test_formation_from_env(monkeypatch):
    monkeypatch.setenv("ALFRED_WINDOW_MESSAGES", "8")
    monkeypatch.setenv("ALFRED_EXTRACT_RECALL_K", "3")
    from alfred_brain.config import Settings
    s = Settings(_env_file=None)
    assert s.memory_window_messages == 8
    assert s.memory_extract_recall_k == 3


def test_formation_from_toml(tmp_path, monkeypatch):
    from alfred_brain.config.toml_source import read_flat_toml
    p = tmp_path / "config.toml"
    p.write_text("[memory]\nwindow_messages = 12\nextract_recall_k = 2\n", encoding="utf-8")
    flat = read_flat_toml(p)
    assert flat["memory_window_messages"] == 12
    assert flat["memory_extract_recall_k"] == 2


def test_user_name_default_empty(monkeypatch):
    monkeypatch.delenv("ALFRED_USER_NAME", raising=False)
    from alfred_brain.config import Settings
    assert Settings(_env_file=None).memory_user_name == ""


def test_user_name_from_env(monkeypatch):
    monkeypatch.setenv("ALFRED_USER_NAME", "Dimitris")
    from alfred_brain.config import Settings
    assert Settings(_env_file=None).memory_user_name == "Dimitris"


def test_user_name_from_toml(tmp_path):
    from alfred_brain.config.toml_source import read_flat_toml
    p = tmp_path / "config.toml"
    p.write_text("[memory]\nuser_name = \"Dimitris\"\n", encoding="utf-8")
    assert read_flat_toml(p)["memory_user_name"] == "Dimitris"
