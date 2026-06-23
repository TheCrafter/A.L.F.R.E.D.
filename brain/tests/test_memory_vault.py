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


def test_filename_is_safe_title_not_full_text(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("Dimitris is 32 and lives in Greece.",
                  title="Dimitris - age and location")
    assert rec.path.name == "Dimitris - age and location.md"
    assert rec.title == "Dimitris - age and location"


def test_illegal_filename_chars_stripped(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("x", title='a/b:c*d?e"f<g>h|i')
    assert not any(c in rec.path.name for c in '\\/:*?"<>|')


def test_filename_collision_gets_numeric_suffix(tmp_path):
    v = Vault(tmp_path / "vault")
    a = v.write("first", title="Same Title")
    b = v.write("second", title="Same Title")
    assert a.path.name == "Same Title.md"
    assert b.path.name == "Same Title 2.md"
    assert a.id != b.id


def test_empty_title_derives_from_text(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("alpha beta gamma delta epsilon zeta eta theta iota")
    assert rec.title == "alpha beta gamma delta epsilon zeta eta theta"


def test_links_render_and_round_trip(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("Dimitris is 32.", title="Dimitris age",
                  links=["Dimitris", "Greece"])
    raw = rec.path.read_text(encoding="utf-8")
    assert "Related: [[Dimitris]], [[Greece]]" in raw
    again = v.read(rec.path)
    assert again.text == "Dimitris is 32."   # Related line excluded from text
    assert again.links == ["Dimitris", "Greece"]
    assert again.title == "Dimitris age"


def test_no_links_no_related_line(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("plain fact", title="Plain")
    raw = rec.path.read_text(encoding="utf-8")
    assert "Related:" not in raw
    assert v.read(rec.path).links == []


def test_update_keeps_filename_stable(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("old", title="Original Title")
    out = v.update(rec.id, text="new", title="Totally Different", links=["Greece"])
    assert out is not None
    assert out.path.name == "Original Title.md"   # NOT renamed
    assert out.title == "Totally Different"
    assert out.links == ["Greece"]


def test_ensure_entity_creates_hub(tmp_path):
    v = Vault(tmp_path / "vault")
    stem = v.ensure_entity("Dimitris", "person")
    assert stem == "Dimitris"
    hub = (tmp_path / "vault" / "entities" / "Dimitris.md")
    assert hub.exists()
    raw = hub.read_text(encoding="utf-8")
    assert "type: person" in raw and "# Dimitris" in raw


def test_ensure_entity_is_case_insensitive_dedup(tmp_path):
    v = Vault(tmp_path / "vault")
    a = v.ensure_entity("Dimitris", "person")
    b = v.ensure_entity("dimitris", "person")
    assert a == b == "Dimitris"   # reuses first-seen spelling
    hubs = list((tmp_path / "vault" / "entities").glob("*.md"))
    assert len(hubs) == 1


def test_entities_excluded_from_facts(tmp_path):
    v = Vault(tmp_path / "vault")
    v.write("a fact", title="Fact A")
    v.ensure_entity("Dimitris", "person")
    assert [r.title for r in v.all()] == ["Fact A"]   # hub not in all()


def test_list_entities(tmp_path):
    v = Vault(tmp_path / "vault")
    v.ensure_entity("Dimitris", "person")
    v.ensure_entity("Greece", "place")
    assert sorted(v.list_entities()) == [("Dimitris", "person"), ("Greece", "place")]


# Regression tests for fix wave 2026-06-24

def test_text_with_related_line_round_trips(tmp_path):
    """Fix 1: text containing a 'Related:' line must not be truncated."""
    v = Vault(tmp_path / "vault")
    text = "The email said:\nRelated: see the attachment."
    rec = v.write(text, title="email note")
    again = v.read(rec.path)
    assert again.text == text
    assert again.links == []


def test_text_with_related_line_plus_real_links(tmp_path):
    """Fix 1: text with embedded 'Related:' line + real links both preserved."""
    v = Vault(tmp_path / "vault")
    text = "Note:\nRelated: prior emails."
    rec = v.write(text, title="mixed note", links=["Dimitris"])
    again = v.read(rec.path)
    assert again.text == text
    assert again.links == ["Dimitris"]


def test_text_with_wikilink_brackets_not_mistaken_for_links(tmp_path):
    """Fix 1: wikilink syntax in body text does not end up as links."""
    v = Vault(tmp_path / "vault")
    text = "See [[some doc]] for details."
    rec = v.write(text, title="doc ref")
    again = v.read(rec.path)
    assert again.text == text
    assert again.links == []


def test_entity_name_with_brackets_sanitized(tmp_path):
    """Fix 2: brackets in entity name are stripped from filename."""
    v = Vault(tmp_path / "vault")
    stem = v.ensure_entity("Project [Alpha]", "project")
    assert "[" not in stem and "]" not in stem
    hub = tmp_path / "vault" / "entities" / f"{stem}.md"
    assert hub.exists()
