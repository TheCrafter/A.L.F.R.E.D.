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


# ---------------------------------------------------------------------------
# New tests for Fix 1 (drain_extractions) and Fix 2 (empty assistant guard)
# ---------------------------------------------------------------------------


class _SlowSpyExtractor:
    """Extractor spy that sets a flag after one event loop tick."""

    def __init__(self):
        self.extracted = False

    async def extract(self, batch):
        await asyncio.sleep(0)  # yield to let other tasks run
        self.extracted = True
        return []


async def test_drain_extractions_awaits_pending_task():
    """AgentLoop.drain_extractions() must await in-flight extraction tasks."""
    wm = WorkingMemory(window=2)  # batch_size=1: overflow on 3rd append
    spy = _SlowSpyExtractor()
    loop = AgentLoop(_CaptureProvider(), ToolRegistry(), "BASE", max_iterations=1,
                     working=wm, extractor=spy)
    # Drive enough turns to trigger take_batch
    for i in range(3):
        await loop.run(corr=f"c{i}", text=f"msg {i}", publish=lambda m: None)
    # At this point an extraction task is scheduled but may not have completed
    assert len(loop._extract_tasks) > 0 or spy.extracted, "pre-condition: task was scheduled"
    await loop.drain_extractions()
    assert spy.extracted, "drain_extractions must have awaited the extraction task"
    assert len(loop._extract_tasks) == 0, "_extract_tasks must be empty after drain"


class _SilentProvider:
    """Provider that yields nothing — simulates an empty assistant reply."""
    name = "silent"

    async def run_turn(self, messages, tools, system):
        return
        yield  # make it a generator without yielding anything


async def test_empty_assistant_reply_not_appended():
    """A turn that produces no text must NOT store an empty assistant message."""
    wm = WorkingMemory(window=10)
    loop = AgentLoop(_SilentProvider(), ToolRegistry(), "BASE", max_iterations=1,
                     working=wm)
    await loop.run(corr="c1", text="hello", publish=lambda m: None)
    ctx = wm.context()
    # User message must be present
    user_msgs = [m for m in ctx if m.role == "user"]
    assert user_msgs, "user message must be in working memory"
    # No assistant message with empty content
    empty_assistant = [m for m in ctx if m.role == "assistant" and not (m.content or "").strip()]
    assert not empty_assistant, "empty assistant message must not be appended"


async def test_concurrent_turns_produce_coherent_messages():
    """Running two turns concurrently must not corrupt working memory.

    The post-turn block is synchronous (no await between appends), so in
    asyncio's single-threaded event loop it executes atomically.  This test
    documents that invariant: messages captured across context + drained batch
    must all be valid non-empty whole messages.
    """
    wm = WorkingMemory(window=4)

    class _SingleChunkProvider:
        name = "single"
        async def run_turn(self, messages, tools, system):
            yield TextChunk("reply", final=True)

    captured_batches: list[list] = []

    class _BatchSpy:
        async def extract(self, batch):
            captured_batches.append(list(batch))
            return []

    loop = AgentLoop(_SingleChunkProvider(), ToolRegistry(), "BASE", max_iterations=1,
                     working=wm, extractor=_BatchSpy())

    await asyncio.gather(
        loop.run(corr="c1", text="turn one", publish=lambda m: None),
        loop.run(corr="c2", text="turn two", publish=lambda m: None),
    )
    await asyncio.sleep(0)  # drain any scheduled extraction tasks

    # Collect all messages across context + captured batches
    all_messages = list(wm.context())
    for batch in captured_batches:
        all_messages.extend(batch)

    # Every message must have a non-empty role and content
    for msg in all_messages:
        assert msg.role in ("user", "assistant"), f"unexpected role: {msg.role}"
        assert (msg.content or "").strip(), f"empty content for role={msg.role}: {msg!r}"
