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


async def test_tools_conform_and_carry_risk(tmp_path):
    m = _mem(tmp_path)
    for tool, risk_name in [(RememberTool(m), "sensitive"),
                            (RecallTool(m), "safe"),
                            (ForgetTool(m), "sensitive")]:
        assert isinstance(tool, Tool)
        assert tool.risk.value == risk_name
        assert "type" in tool.parameters
