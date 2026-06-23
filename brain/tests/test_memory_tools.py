import pytest

from alfred_brain.memory import VaultMemory
from alfred_brain.memory.tools import ForgetTool, RecallTool, RememberTool
from alfred_brain.tools.base import Tool
from tests.test_memory_index import FakeEmbedder


def _mem(tmp_path):
    return VaultMemory(tmp_path / "vault", FakeEmbedder())


async def test_remember_tool_stores(tmp_path):
    m = _mem(tmp_path)
    out = await RememberTool(m).run({"text": "alpha fact", "type": "fact", "tags": ["x"]})
    assert m.all()[0].text == "alpha fact"
    assert m.all()[0].type == "fact"
    assert "remember" in out.lower() or m.all()[0].id in out


async def test_recall_tool_returns_ids_and_text(tmp_path):
    m = _mem(tmp_path)
    rec = m.remember("alpha thing")
    out = await RecallTool(m).run({"query": "alpha"})
    assert rec.id in out
    assert "alpha thing" in out


async def test_forget_tool_deletes(tmp_path):
    m = _mem(tmp_path)
    rec = m.remember("alpha removable")
    out = await ForgetTool(m).run({"id": rec.id})
    assert m.all() == []
    assert "forg" in out.lower() or rec.id in out


async def test_remember_tool_requires_text(tmp_path):
    m = _mem(tmp_path)
    out = await RememberTool(m).run({"text": "   "})
    assert "required" in out.lower()
    assert m.all() == []


async def test_tools_conform_and_carry_risk(tmp_path):
    m = _mem(tmp_path)
    for tool, risk_name in [(RememberTool(m), "sensitive"),
                            (RecallTool(m), "safe"),
                            (ForgetTool(m), "sensitive")]:
        assert isinstance(tool, Tool)
        assert tool.risk.value == risk_name
        assert "type" in tool.parameters


async def test_remember_tool_with_title_and_entities(tmp_path):
    m = _mem(tmp_path)
    tool = RememberTool(m)
    await tool.run({"text": "Dimitris created Alfred.", "title": "Dimitris created Alfred",
                    "entities": [{"name": "Dimitris", "type": "person"},
                                 {"name": "Alfred", "type": "project"}]})
    rec = m.all()[0]
    assert rec.title == "Dimitris created Alfred"
    assert rec.links == ["Dimitris", "Alfred"]
    assert sorted(m.list_entities()) == [("Alfred", "project"), ("Dimitris", "person")]


async def test_remember_tool_without_title_derives_one(tmp_path):
    m = _mem(tmp_path)
    await RememberTool(m).run({"text": "one two three four five six seven eight nine"})
    rec = m.all()[0]
    assert rec.title == "one two three four five six seven eight"
    assert rec.links == []
