import pytest

from alfred_brain.memory import VaultMemory
from alfred_brain.memory.extraction import EntityRef, Extractor, route_status, _parse_ops
from alfred_brain.providers.base import TextChunk, TurnMessage
from tests.test_memory_index import FakeEmbedder


class _FakeProvider:
    """Yields a fixed response text as a single final TextChunk."""
    name = "fake"

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    async def run_turn(self, messages, tools, system):
        self.calls += 1
        text = self._responses[min(self.calls - 1, len(self._responses) - 1)]
        yield TextChunk(text, final=True)


def _batch():
    return [TurnMessage(role="user", content="My name is Dimitris, I created you.")]


def test_route_status_table():
    assert route_status("high", "low") == "confirmed"
    assert route_status("high", "high") == "provisional"
    assert route_status("low", "low") == "provisional"
    assert route_status("low", "high") == "provisional"


def test_parse_ops_tolerates_fences_and_prose():
    raw = 'Sure!\n```json\n{"operations": [{"action": "add", "text": "x"}]}\n```\n'
    ops = _parse_ops(raw)
    assert len(ops) == 1 and ops[0].action == "add" and ops[0].text == "x"


def test_parse_ops_raises_on_garbage():
    with pytest.raises(ValueError):
        _parse_ops("no json here")


async def test_extract_adds_routed_memory(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    prov = _FakeProvider(
        '{"operations": [{"action": "add", "text": "User is named Dimitris", '
        '"type": "fact", "confidence": "high", "stakes": "low"}]}')
    applied = await Extractor(prov, mem).extract(_batch())
    assert len(applied) == 1
    assert applied[0].status == "confirmed"
    assert any("Dimitris" in r.text for r in mem.all())


async def test_extract_high_stakes_is_provisional(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    prov = _FakeProvider(
        '{"operations": [{"action": "add", "text": "bank PIN is 1234", '
        '"confidence": "high", "stakes": "high"}]}')
    applied = await Extractor(prov, mem).extract(_batch())
    assert applied[0].status == "provisional"


async def test_extract_update_existing(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    rec = mem.remember("user likes tea", type="preference", status="provisional")
    prov = _FakeProvider(
        '{"operations": [{"action": "update", "id": "%s", '
        '"text": "user likes coffee", "confidence": "high", "stakes": "low"}]}' % rec.id)
    applied = await Extractor(prov, mem).extract(_batch())
    assert applied[0].id == rec.id and applied[0].status == "confirmed"
    assert any("coffee" in r.text for r in mem.all())


async def test_extract_retries_once_then_gives_up(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    prov = _FakeProvider("garbage", "still garbage")
    applied = await Extractor(prov, mem).extract(_batch())
    assert applied == [] and prov.calls == 2


async def test_extract_empty_batch_no_call(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    prov = _FakeProvider("{}")
    assert await Extractor(prov, mem).extract([]) == []
    assert prov.calls == 0


async def test_extract_provider_error_returns_empty(tmp_path):
    class _Boom:
        name = "boom"
        async def run_turn(self, messages, tools, system):
            raise RuntimeError("down")
            yield  # pragma: no cover
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    assert await Extractor(_Boom(), mem).extract(_batch()) == []


def test_parse_ops_reads_title_and_entities():
    raw = ('{"operations": [{"action": "add", "text": "Dimitris is 32.", '
           '"title": "Dimitris age", "entities": [{"name": "Dimitris", "type": "person"}, '
           '{"name": "Xland", "type": "bogus"}]}]}')
    ops = _parse_ops(raw)
    assert ops[0].title == "Dimitris age"
    assert ops[0].entities[0] == EntityRef("Dimitris", "person")
    assert ops[0].entities[1].type == "topic"   # invalid type coerced


async def test_apply_creates_hubs_and_links(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    prov = _FakeProvider(
        '{"operations": [{"action": "add", "text": "Dimitris is 32 and in Greece.", '
        '"title": "Dimitris age and location", "confidence": "high", "stakes": "low", '
        '"entities": [{"name": "Dimitris", "type": "person"}, '
        '{"name": "Greece", "type": "place"}]}]}')
    applied = await Extractor(prov, mem).extract(_batch())
    assert applied[0].title == "Dimitris age and location"
    assert applied[0].links == ["Dimitris", "Greece"]
    assert sorted(mem.list_entities()) == [("Dimitris", "person"), ("Greece", "place")]
    assert applied[0].path.name == "Dimitris age and location.md"


async def test_known_entities_passed_to_provider(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    mem.ensure_entity("Dimitris", "person")

    class _CaptureProvider:
        name = "cap"
        def __init__(self): self.system = None; self.user = None
        async def run_turn(self, messages, tools, system):
            self.system = system
            self.user = messages[0].content
            yield TextChunk('{"operations": []}', final=True)

    prov = _CaptureProvider()
    await Extractor(prov, mem).extract(_batch())
    assert "Dimitris" in prov.user   # known entity surfaced to the model
