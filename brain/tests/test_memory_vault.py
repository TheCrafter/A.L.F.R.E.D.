from alfred_brain.memory.vault import Vault


def test_write_creates_obsidian_note(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("Dimitris prefers terse replies", type="preference", tags=["style"])
    assert rec.path.is_file()
    assert rec.path.parent.name == "memories"
    body = rec.path.read_text(encoding="utf-8")
    assert body.startswith("---\n")              # frontmatter
    assert "type: preference" in body
    assert "Dimitris prefers terse replies" in body
    assert rec.id in body
    assert rec.tags == ["style"]


def test_read_round_trips(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("alpha beta", type="fact", tags=["t1", "t2"])
    again = v.read(rec.path)
    assert again.id == rec.id
    assert again.text == "alpha beta"
    assert again.type == "fact"
    assert again.tags == ["t1", "t2"]
    assert again.status == "confirmed"


def test_all_lists_every_note(tmp_path):
    v = Vault(tmp_path / "vault")
    v.write("one")
    v.write("two")
    assert {r.text for r in v.all()} == {"one", "two"}


def test_delete_by_id(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("removable")
    assert v.delete(rec.id) is True
    assert v.all() == []
    assert v.delete("nonexistent") is False


def test_slug_is_filesystem_safe(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("Hello, World! / weird:name?")
    assert rec.path.is_file()                    # no illegal chars crashed the write
    assert "/" not in rec.path.name and ":" not in rec.path.name


def test_write_accepts_status(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("provisional fact", status="provisional")
    assert rec.status == "provisional"
    assert v.read(rec.path).status == "provisional"


def test_update_rewrites_in_place(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("old text", type="note", status="provisional")
    path_before = rec.path
    updated = v.update(rec.id, text="new text", status="confirmed")
    assert updated is not None
    assert updated.id == rec.id
    assert updated.path == path_before  # filename/slug preserved
    assert updated.text == "new text"
    assert updated.status == "confirmed"
    assert updated.updated is not None
    reread = v.read(path_before)
    assert reread.text == "new text" and reread.status == "confirmed"


def test_update_unknown_id_returns_none(tmp_path):
    v = Vault(tmp_path / "vault")
    assert v.update("nope", text="x") is None
