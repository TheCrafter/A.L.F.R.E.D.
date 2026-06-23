from alfred_brain.memory import Memory, VaultMemory
from tests.test_memory_index import FakeEmbedder


def _mem(tmp_path):
    return VaultMemory(tmp_path / "vault", FakeEmbedder())


def test_remember_then_recall_finds_it(tmp_path):
    m = _mem(tmp_path)
    m.remember("alpha alpha matters", type="fact")
    m.remember("beta is unrelated")
    hits = m.recall("alpha", k=1)
    assert len(hits) == 1
    assert "alpha" in hits[0].text


def test_remember_writes_a_note_on_disk(tmp_path):
    m = _mem(tmp_path)
    rec = m.remember("persisted", tags=["t"])
    assert rec.path.is_file()
    assert {r.text for r in m.all()} == {"persisted"}


def test_forget_removes_from_recall_and_disk(tmp_path):
    m = _mem(tmp_path)
    rec = m.remember("alpha forgettable")
    assert m.forget(rec.id) is True
    assert m.all() == []
    assert m.recall("alpha", k=5) == []
    assert m.forget(rec.id) is False


def test_index_rebuilds_from_existing_vault(tmp_path):
    first = _mem(tmp_path)
    first.remember("alpha persisted across restart")
    # a fresh facade over the same vault dir must recall it (index rebuilt on init)
    second = VaultMemory(tmp_path / "vault", FakeEmbedder())
    assert second.recall("alpha", k=1)[0].text == "alpha persisted across restart"


def test_is_a_memory(tmp_path):
    assert isinstance(_mem(tmp_path), Memory)


def test_remember_default_status_confirmed(tmp_path):
    from alfred_brain.memory import VaultMemory
    from tests.test_memory_index import FakeEmbedder
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    rec = mem.remember("a fact")
    assert rec.status == "confirmed"


def test_update_changes_status_and_text_and_index(tmp_path):
    from alfred_brain.memory import VaultMemory
    from tests.test_memory_index import FakeEmbedder
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    rec = mem.remember("user likes tea", type="preference", status="provisional")
    out = mem.update(rec.id, text="user likes coffee", status="confirmed")
    assert out is not None and out.status == "confirmed"
    hits = mem.recall("coffee", k=5)
    assert any(h.text == "user likes coffee" for h in hits)


def test_update_unknown_id_returns_none(tmp_path):
    from alfred_brain.memory import VaultMemory
    from tests.test_memory_index import FakeEmbedder
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    assert mem.update("missing", text="x") is None
