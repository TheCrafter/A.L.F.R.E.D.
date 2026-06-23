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
