from alfred_brain.agent import AgentLoop
from alfred_brain.memory import VaultMemory
from alfred_brain.providers.base import TextChunk
from alfred_brain.tools.registry import ToolRegistry
from tests.test_memory_index import FakeEmbedder


class _CaptureProvider:
    name = "capture"

    def __init__(self):
        self.system = None

    async def run_turn(self, messages, tools, system):
        self.system = system
        yield TextChunk("ok", final=True)


async def test_recalled_memory_is_injected_into_system(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    mem.remember("alpha is the launch code", type="fact")
    prov = _CaptureProvider()
    loop = AgentLoop(prov, ToolRegistry(), "BASE", max_iterations=1,
                     memory=mem, recall_top_k=5)
    await loop.run(corr="c1", text="what is alpha", publish=lambda m: None)
    assert "BASE" in prov.system
    assert "alpha is the launch code" in prov.system


async def test_no_memory_leaves_system_unchanged(tmp_path):
    prov = _CaptureProvider()
    loop = AgentLoop(prov, ToolRegistry(), "BASE", max_iterations=1)  # memory=None
    await loop.run(corr="c1", text="hi", publish=lambda m: None)
    assert prov.system == "BASE"


async def test_set_recall_top_k(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    loop = AgentLoop(_CaptureProvider(), ToolRegistry(), "BASE", memory=mem)
    loop.set_recall_top_k(2)
    assert loop._recall_top_k == 2
