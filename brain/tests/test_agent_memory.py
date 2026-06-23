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


import asyncio

from alfred_brain.memory.working import WorkingMemory


class _SpyExtractor:
    def __init__(self):
        self.batches = []
    async def extract(self, batch):
        self.batches.append(batch)
        return []


async def test_working_context_is_fed_into_turn(tmp_path):
    wm = WorkingMemory(window=10)
    wm.append("user", "earlier question")
    wm.append("assistant", "earlier answer")
    prov = _CaptureProvider()

    class _CaptureMessages(_CaptureProvider):
        def __init__(self):
            super().__init__()
            self.messages = None
        async def run_turn(self, messages, tools, system):
            self.messages = list(messages)
            self.system = system
            yield TextChunk("ok", final=True)

    prov = _CaptureMessages()
    loop = AgentLoop(prov, ToolRegistry(), "BASE", max_iterations=1, working=wm)
    await loop.run(corr="c1", text="new question", publish=lambda m: None)
    contents = [m.content for m in prov.messages]
    assert "earlier question" in contents and "new question" in contents


async def test_overflow_schedules_extraction(tmp_path):
    wm = WorkingMemory(window=2)  # batch_size 1: every aged-out msg triggers a batch
    spy = _SpyExtractor()
    loop = AgentLoop(_CaptureProvider(), ToolRegistry(), "BASE", max_iterations=1,
                     working=wm, extractor=spy)
    for i in range(3):
        await loop.run(corr=f"c{i}", text=f"msg {i}", publish=lambda m: None)
        await asyncio.sleep(0)  # let the scheduled task run
    assert spy.batches, "extraction should have been scheduled on overflow"


async def test_provisional_memory_labeled_unconfirmed(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    mem.remember("user may live in Athens", type="fact", status="provisional")
    prov = _CaptureProvider()
    loop = AgentLoop(prov, ToolRegistry(), "BASE", max_iterations=1,
                     memory=mem, recall_top_k=5)
    await loop.run(corr="c1", text="where do I live", publish=lambda m: None)
    assert "unconfirmed" in prov.system


async def test_confirmed_memory_not_labeled_unconfirmed(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    mem.remember("user lives in Athens", type="fact", status="confirmed")
    prov = _CaptureProvider()
    loop = AgentLoop(prov, ToolRegistry(), "BASE", max_iterations=1,
                     memory=mem, recall_top_k=5)
    await loop.run(corr="c1", text="where do I live", publish=lambda m: None)
    # Confirmed memories should not carry an "unconfirmed" label in the recall listing.
    # (MEMORY_GUIDANCE prose contains the word; we check the recall line only.)
    assert "- (fact, unconfirmed) user lives in Athens" not in prov.system
    assert "user lives in Athens" in prov.system
