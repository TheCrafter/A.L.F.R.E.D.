# Memory Formation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give ALFRED short-term conversational memory plus an automatic extraction pass that distills durable facts into the vault, replacing the unreliable "ask the chat model to call `remember`" approach.

**Architecture:** A brain-global in-RAM `WorkingMemory` buffer feeds recent messages into every turn. Messages aging out of the window are handed to an async `Extractor` (a separate single-purpose LLM call) that dedupes against existing memories and writes durable notes routed to `confirmed`/`provisional` by confidence×stakes. The vault foundation is extended with `status` + `update`; `protocol/` is untouched.

**Tech Stack:** Python 3.12 (managed by `uv`), pydantic-settings, FastAPI, pytest. Reuses the existing `ReasoningProvider`, `VaultMemory`, and flat-TOML config.

## Global Constraints

- Python 3.12; run all commands from `brain/` via `uv run …`.
- Strict typing — full type hints, no `Any` workarounds. Resolve types at the source.
- `protocol/` is frozen — do not touch it. This feature adds no wire messages.
- Commit messages: plain, conventional, scoped `feat(brain): …` / `test(brain): …`. **NO `Co-Authored-By: Claude` or "authored by Claude" trailer.**
- Run `uv run pytest -q` from `brain/` after each task; all tests pass before the task is complete.
- Tests use the existing `tests/conftest.py` autouse fixture (isolates `$ALFRED_HOME`) and `tests/test_memory_index.py::FakeEmbedder` for embedding.
- Trust vocabulary: a memory is `confirmed` (trusted) or `provisional` (held loosely). Legacy `"active"` is treated as confirmed when labeling.
- Async extraction is fire-and-forget and must NEVER raise into the turn or crash the server — the `Extractor` swallows and logs its own errors.

---

### Task 1: Memory layer — `status` + `update`

Extend the vault foundation so memories carry a routable trust status and can be updated in place (needed by extraction's ADD/UPDATE ops).

**Files:**
- Modify: `brain/src/alfred_brain/memory/record.py`
- Modify: `brain/src/alfred_brain/memory/vault.py`
- Modify: `brain/src/alfred_brain/memory/facade.py`
- Modify: `brain/src/alfred_brain/memory/tools.py`
- Test: `brain/tests/test_memory_vault.py`, `brain/tests/test_memory_facade.py`

**Interfaces:**
- Produces:
  - `MemoryRecord` gains `updated: str | None = None`.
  - `Memory` protocol: `remember(text, *, type="note", tags=None, status="confirmed") -> MemoryRecord`; new `update(id, *, text=None, type=None, tags=None, status=None) -> MemoryRecord | None`.
  - `VaultMemory.update(...)` and `Vault.update(id, *, text=None, type=None, tags=None, status=None) -> MemoryRecord | None`.
- Consumes: nothing new.

- [ ] **Step 1: Write failing tests**

In `brain/tests/test_memory_vault.py`, change the existing `again.status == "active"` assertion to `"confirmed"`, and add:

```python
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
```

In `brain/tests/test_memory_facade.py` add (the file imports `VaultMemory` and `FakeEmbedder`; match its existing style):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_memory_vault.py tests/test_memory_facade.py -q`
Expected: FAIL (`write()`/`update()` got unexpected keyword / `AttributeError: 'VaultMemory' object has no attribute 'update'`).

- [ ] **Step 3: Update `record.py`**

Add the `updated` field and extend the protocol:

```python
@dataclass
class MemoryRecord:
    id: str
    text: str
    type: str
    tags: list[str]
    status: str
    created: str  # RFC 3339
    path: Path
    updated: str | None = None


@runtime_checkable
class Memory(Protocol):
    def remember(self, text: str, *, type: str = "note",
                 tags: list[str] | None = None,
                 status: str = "confirmed") -> MemoryRecord: ...
    def recall(self, query: str, *, k: int = 5) -> list[MemoryRecord]: ...
    def update(self, id: str, *, text: str | None = None, type: str | None = None,
               tags: list[str] | None = None,
               status: str | None = None) -> MemoryRecord | None: ...
    def forget(self, id: str) -> bool: ...
    def all(self) -> list[MemoryRecord]: ...
```

- [ ] **Step 4: Update `vault.py`**

Change `write` to accept `status` (default `"confirmed"`), include `updated` in frontmatter only when set, teach `read` to load `updated`, and add `update`:

```python
    def write(self, text: str, *, type: str = "note",
              tags: list[str] | None = None,
              status: str = "confirmed") -> MemoryRecord:
        self._dir.mkdir(parents=True, exist_ok=True)
        rec = MemoryRecord(
            id=_new_id(), text=text, type=type, tags=list(tags or []),
            status=status, created=_now(),
            path=Path(),  # set below
        )
        rec.path = self._dir / f"{_slugify(text)}-{rec.id}.md"
        rec.path.write_text(self._render(rec), encoding="utf-8")
        return rec

    def _render(self, rec: MemoryRecord) -> str:
        meta = {"id": rec.id, "created": rec.created, "type": rec.type,
                "tags": rec.tags, "status": rec.status}
        if rec.updated:
            meta["updated"] = rec.updated
        front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
        return f"---\n{front}---\n\n{rec.text}\n"

    def update(self, id: str, *, text: str | None = None, type: str | None = None,
               tags: list[str] | None = None,
               status: str | None = None) -> MemoryRecord | None:
        for rec in self.all():
            if rec.id != id:
                continue
            if text is not None:
                rec.text = text
            if type is not None:
                rec.type = type
            if tags is not None:
                rec.tags = list(tags)
            if status is not None:
                rec.status = status
            rec.updated = _now()
            rec.path.write_text(self._render(rec), encoding="utf-8")
            return rec
        return None
```

Update `read` to populate `updated`:

```python
        return MemoryRecord(
            id=str(meta.get("id", "")), text=m.group(2).strip(),
            type=str(meta.get("type", "note")), tags=list(meta.get("tags") or []),
            status=str(meta.get("status", "active")),
            created=str(meta.get("created", "")), path=Path(path),
            updated=(str(meta["updated"]) if meta.get("updated") else None),
        )
```

(The `write` body that built the frontmatter inline is replaced by `_render`.)

- [ ] **Step 5: Update `facade.py`**

Thread `status` through `remember` and add `update` (rebuild the index entry when text changes):

```python
    def remember(self, text: str, *, type: str = "note",
                 tags: list[str] | None = None,
                 status: str = "confirmed") -> MemoryRecord:
        rec = self._vault.write(text, type=type, tags=tags, status=status)
        self._records[rec.id] = rec
        self._index.add(rec.id, rec.text)
        return rec

    def update(self, id: str, *, text: str | None = None, type: str | None = None,
               tags: list[str] | None = None,
               status: str | None = None) -> MemoryRecord | None:
        rec = self._vault.update(id, text=text, type=type, tags=tags, status=status)
        if rec is None:
            return None
        self._records[rec.id] = rec
        if text is not None:
            self._index.remove(rec.id)
            self._index.add(rec.id, rec.text)
        return rec
```

- [ ] **Step 6: Update `tools.py`**

Make explicit remembers `confirmed` (belt-and-suspenders even though it is the default):

```python
        rec = self._memory.remember(
            text,
            type=str(args.get("type", "note")),
            tags=list(args.get("tags") or []),
            status="confirmed",
        )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_memory_vault.py tests/test_memory_facade.py tests/test_memory_tools.py tests/test_memory_record.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add brain/src/alfred_brain/memory/ brain/tests/test_memory_vault.py brain/tests/test_memory_facade.py
git commit -m "feat(brain): memory status + in-place update (provisional/confirmed groundwork)"
```

---

### Task 2: Working memory (short-term buffer)

A brain-global, in-RAM rolling buffer of recent user/assistant messages.

**Files:**
- Create: `brain/src/alfred_brain/memory/working.py`
- Test: `brain/tests/test_memory_working.py`

**Interfaces:**
- Produces: `WorkingMemory(window=20)` with `append(role, text)`, `context() -> list[TurnMessage]`, `take_batch() -> list[TurnMessage]`, `drain() -> list[TurnMessage]`, `set_window(n)`.
- Consumes: `TurnMessage` from `providers.base`.

- [ ] **Step 1: Write failing tests**

Create `brain/tests/test_memory_working.py`:

```python
from alfred_brain.memory.working import WorkingMemory


def test_context_returns_recent_within_window():
    wm = WorkingMemory(window=4)
    for i in range(3):
        wm.append("user", f"u{i}")
    ctx = wm.context()
    assert [m.content for m in ctx] == ["u0", "u1", "u2"]
    assert all(m.role == "user" for m in ctx)


def test_overflow_moves_to_pending_and_batches():
    wm = WorkingMemory(window=4)  # batch_size = 2
    # 4 fit in the window; the 5th and 6th evict u0, u1 into pending
    for i in range(6):
        wm.append("user", f"u{i}")
    assert [m.content for m in wm.context()] == ["u2", "u3", "u4", "u5"]
    batch = wm.take_batch()
    assert [m.content for m in batch] == ["u0", "u1"]
    assert wm.take_batch() == []  # cleared


def test_take_batch_empty_below_batch_size():
    wm = WorkingMemory(window=4)  # batch_size = 2
    for i in range(5):  # one eviction -> pending has 1 < 2
        wm.append("user", f"u{i}")
    assert wm.take_batch() == []


def test_drain_returns_pending_plus_window_and_clears():
    wm = WorkingMemory(window=4)
    for i in range(6):
        wm.append("user", f"u{i}")
    drained = wm.drain()
    assert [m.content for m in drained] == ["u0", "u1", "u2", "u3", "u4", "u5"]
    assert wm.context() == [] and wm.take_batch() == []


def test_set_window_shrinks_into_pending():
    wm = WorkingMemory(window=10)
    for i in range(6):
        wm.append("user", f"u{i}")
    wm.set_window(2)
    assert [m.content for m in wm.context()] == ["u4", "u5"]
    # pending now has u0..u3 (4 >= batch_size 1) -> one batch available
    assert [m.content for m in wm.take_batch()] == ["u0", "u1", "u2", "u3"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_memory_working.py -q`
Expected: FAIL (`ModuleNotFoundError: ...memory.working`).

- [ ] **Step 3: Implement `working.py`**

```python
from __future__ import annotations

from collections import deque
from typing import Literal

from ..providers.base import TurnMessage


class WorkingMemory:
    """In-RAM rolling buffer of recent user/assistant messages (short-term memory).

    The most recent `window` messages are the conversation context fed to the
    model. Messages aging out of the window accumulate in `pending` and are handed
    to extraction in batches of `window // 2`.
    """

    def __init__(self, window: int = 20) -> None:
        self._window = max(2, window)
        self._recent: deque[TurnMessage] = deque()
        self._pending: list[TurnMessage] = []

    @property
    def _batch_size(self) -> int:
        return max(1, self._window // 2)

    def append(self, role: Literal["user", "assistant"], text: str) -> None:
        self._recent.append(TurnMessage(role=role, content=text))
        self._evict()

    def _evict(self) -> None:
        while len(self._recent) > self._window:
            self._pending.append(self._recent.popleft())

    def context(self) -> list[TurnMessage]:
        return list(self._recent)

    def take_batch(self) -> list[TurnMessage]:
        if len(self._pending) < self._batch_size:
            return []
        batch = self._pending
        self._pending = []
        return batch

    def drain(self) -> list[TurnMessage]:
        batch = self._pending + list(self._recent)
        self._pending = []
        self._recent.clear()
        return batch

    def set_window(self, n: int) -> None:
        self._window = max(2, n)
        self._evict()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_memory_working.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brain/src/alfred_brain/memory/working.py brain/tests/test_memory_working.py
git commit -m "feat(brain): WorkingMemory short-term rolling buffer"
```

---

### Task 3: Extraction pass

A separate single-purpose LLM call that distills durable facts from a batch and applies them via the `Memory` facade.

**Files:**
- Create: `brain/src/alfred_brain/memory/extraction.py`
- Test: `brain/tests/test_memory_extraction.py`

**Interfaces:**
- Produces: `ExtractOp` dataclass; `route_status(confidence, stakes) -> str`; `Extractor(provider, memory, *, recall_k=5)` with `set_provider(p)`, `set_recall_k(k)`, `async extract(batch) -> list[MemoryRecord]`.
- Consumes: `ReasoningProvider`, `TextChunk`, `TurnMessage` (providers.base); `Memory`, `MemoryRecord` (memory.record); Task 1's `remember(status=...)` and `update(...)`.

- [ ] **Step 1: Write failing tests**

Create `brain/tests/test_memory_extraction.py`:

```python
import pytest

from alfred_brain.memory import VaultMemory
from alfred_brain.memory.extraction import Extractor, route_status, _parse_ops
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_memory_extraction.py -q`
Expected: FAIL (`ModuleNotFoundError: ...memory.extraction`).

- [ ] **Step 3: Implement `extraction.py`**

```python
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from ..providers.base import ReasoningProvider, TextChunk, TurnMessage
from .record import Memory, MemoryRecord

logger = logging.getLogger(__name__)


@dataclass
class ExtractOp:
    action: Literal["add", "update"]
    text: str
    id: str | None = None
    type: str = "note"
    tags: list[str] = field(default_factory=list)
    confidence: Literal["high", "low"] = "low"
    stakes: Literal["low", "high"] = "low"


def route_status(confidence: str, stakes: str) -> str:
    return "confirmed" if confidence == "high" and stakes == "low" else "provisional"


EXTRACTION_SYSTEM = (
    "You extract durable, long-term memories from a conversation transcript. "
    "Keep ONLY lasting facts worth remembering across sessions: the user's "
    "identity, lasting preferences, ongoing projects, important people, and how "
    "the user wants the assistant to behave. Ignore greetings, one-off requests, "
    "and ephemeral chatter.\n\n"
    "You are given EXISTING memories (each with an id) and a TRANSCRIPT. For each "
    "durable fact:\n"
    "- If it refines or matches an existing memory, emit an \"update\" op with that "
    "id instead of duplicating it.\n"
    "- Otherwise emit an \"add\" op.\n"
    "- If the transcript confirms a tentative existing memory, \"update\" it with "
    "confidence \"high\".\n\n"
    "Set \"confidence\" (high|low) by how certain the fact is, and \"stakes\" "
    "(low|high) by how much acting on it wrongly would matter (security, money, "
    "identity, irreversible actions are high).\n\n"
    "Respond with ONLY a JSON object, no prose:\n"
    '{"operations": [{"action": "add", "text": "...", "type": "fact", '
    '"tags": [], "confidence": "high", "stakes": "low"}]}\n'
    "Use an empty operations list when nothing durable is present."
)


def _render(batch: list[TurnMessage]) -> str:
    lines = [f"{m.role}: {m.content.strip()}"
             for m in batch
             if m.role in ("user", "assistant") and m.content.strip()]
    return "\n".join(lines)


def _parse_ops(raw: str) -> list[ExtractOp]:
    """Tolerantly parse the model's JSON. Raises ValueError on failure."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found")
    data = json.loads(text[start:end + 1])
    ops: list[ExtractOp] = []
    for o in data.get("operations", []):
        if not isinstance(o, dict):
            continue
        action = o.get("action")
        body = str(o.get("text", "")).strip()
        if action not in ("add", "update") or not body:
            continue
        ops.append(ExtractOp(
            action=action, text=body,
            id=(str(o["id"]) if o.get("id") else None),
            type=str(o.get("type", "note")),
            tags=[str(t) for t in (o.get("tags") or [])],
            confidence="high" if o.get("confidence") == "high" else "low",
            stakes="high" if o.get("stakes") == "high" else "low",
        ))
    return ops


class Extractor:
    """Runs an LLM extraction pass over aged-out messages and writes memories."""

    def __init__(self, provider: ReasoningProvider, memory: Memory,
                 *, recall_k: int = 5) -> None:
        self._provider = provider
        self._memory = memory
        self._recall_k = recall_k
        self._lock = asyncio.Lock()

    def set_provider(self, provider: ReasoningProvider) -> None:
        self._provider = provider

    def set_recall_k(self, k: int) -> None:
        self._recall_k = k

    async def _call(self, transcript: str, existing: list[MemoryRecord]) -> str:
        existing_block = "\n".join(
            f"- [{r.id}] ({r.type}, {r.status}) {r.text}" for r in existing
        ) or "(none)"
        user = f"EXISTING memories:\n{existing_block}\n\nTRANSCRIPT:\n{transcript}"
        chunks: list[str] = []
        async for ev in self._provider.run_turn(
            [TurnMessage(role="user", content=user)], [], EXTRACTION_SYSTEM
        ):
            if isinstance(ev, TextChunk):
                chunks.append(ev.text)
        return "".join(chunks)

    async def extract(self, batch: list[TurnMessage]) -> list[MemoryRecord]:
        transcript = _render(batch)
        if not transcript:
            return []
        async with self._lock:
            try:
                existing = self._memory.recall(transcript, k=self._recall_k)
                raw = await self._call(transcript, existing)
                try:
                    ops = _parse_ops(raw)
                except ValueError:
                    raw = await self._call(transcript, existing)  # one retry
                    ops = _parse_ops(raw)
            except Exception:
                logger.exception("memory extraction failed")
                return []
            return self._apply(ops)

    def _apply(self, ops: list[ExtractOp]) -> list[MemoryRecord]:
        applied: list[MemoryRecord] = []
        for op in ops:
            try:
                status = route_status(op.confidence, op.stakes)
                if op.action == "add":
                    applied.append(self._memory.remember(
                        op.text, type=op.type, tags=op.tags, status=status))
                elif op.action == "update" and op.id:
                    rec = self._memory.update(
                        op.id, text=op.text, type=op.type, tags=op.tags,
                        status=status)
                    if rec is not None:
                        applied.append(rec)
            except Exception:
                logger.exception("applying extraction op failed: %s", op)
        return applied
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_memory_extraction.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brain/src/alfred_brain/memory/extraction.py brain/tests/test_memory_extraction.py
git commit -m "feat(brain): memory extraction pass (durable-fact distillation + dedup)"
```

---

### Task 4: Config keys

Add `window_messages`, `extract_model`, `extract_recall_k` to settings, the TOML section map, and the bootstrap template.

**Files:**
- Modify: `brain/src/alfred_brain/config/settings.py`
- Modify: `brain/src/alfred_brain/config/toml_source.py`
- Modify: `brain/src/alfred_brain/config/bootstrap.py`
- Test: `brain/tests/test_config_memory.py`

**Interfaces:**
- Produces: `Settings.memory_window_messages: int` (default 20, ge=2), `Settings.memory_extract_model: str` (default ""), `Settings.memory_extract_recall_k: int` (default 5, ge=1).
- Consumes: nothing new.

- [ ] **Step 1: Write failing tests**

Append to `brain/tests/test_config_memory.py` (match the file's existing imports/style):

```python
def test_formation_defaults(monkeypatch):
    for v in ("ALFRED_WINDOW_MESSAGES", "ALFRED_EXTRACT_MODEL", "ALFRED_EXTRACT_RECALL_K"):
        monkeypatch.delenv(v, raising=False)
    from alfred_brain.config import Settings
    s = Settings(_env_file=None)
    assert s.memory_window_messages == 20
    assert s.memory_extract_model == ""
    assert s.memory_extract_recall_k == 5


def test_formation_from_env(monkeypatch):
    monkeypatch.setenv("ALFRED_WINDOW_MESSAGES", "8")
    monkeypatch.setenv("ALFRED_EXTRACT_RECALL_K", "3")
    from alfred_brain.config import Settings
    s = Settings(_env_file=None)
    assert s.memory_window_messages == 8
    assert s.memory_extract_recall_k == 3


def test_formation_from_toml(tmp_path, monkeypatch):
    from alfred_brain.config.toml_source import read_flat_toml
    p = tmp_path / "config.toml"
    p.write_text("[memory]\nwindow_messages = 12\nextract_recall_k = 2\n", encoding="utf-8")
    flat = read_flat_toml(p)
    assert flat["memory_window_messages"] == 12
    assert flat["memory_extract_recall_k"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_config_memory.py -q`
Expected: FAIL (`AttributeError: ...memory_window_messages`).

- [ ] **Step 3: Update `settings.py`**

Add to `ENV_ALIASES`:

```python
    "memory_window_messages": "ALFRED_WINDOW_MESSAGES",
    "memory_extract_model": "ALFRED_EXTRACT_MODEL",
    "memory_extract_recall_k": "ALFRED_EXTRACT_RECALL_K",
```

Add fields after `memory_recall_top_k`:

```python
    memory_window_messages: int = Field(
        default=20, ge=2, validation_alias="ALFRED_WINDOW_MESSAGES")
    memory_extract_model: str = Field(default="", validation_alias="ALFRED_EXTRACT_MODEL")
    memory_extract_recall_k: int = Field(
        default=5, ge=1, validation_alias="ALFRED_EXTRACT_RECALL_K")
```

- [ ] **Step 4: Update `toml_source.py`**

Add to `SECTION_MAP`:

```python
    ("memory", "window_messages"): "memory_window_messages",
    ("memory", "extract_model"): "memory_extract_model",
    ("memory", "extract_recall_k"): "memory_extract_recall_k",
```

- [ ] **Step 5: Update `bootstrap.py` template `[memory]` block**

Replace the `[memory]` block in `render_template` with:

```python
    return f"""# ~/.alfred/config.toml — ALFRED brain config.
...
[memory]
# vault_dir = ""   # [*] default: $ALFRED_HOME/vault  (an Obsidian-compatible vault)
embed_model = "{g("ALFRED_EMBED_MODEL", "BAAI/bge-small-en-v1.5")}"   # [*] local CPU embedding model
recall_top_k = {g("ALFRED_RECALL_TOP_K", "5")}   # integer >= 1   (hot-reloadable)
window_messages = {g("ALFRED_WINDOW_MESSAGES", "20")}   # short-term: last N user/assistant messages   (hot-reloadable)
# extract_model = ""   # [*] model for the extraction pass; empty = use the active provider's model
extract_recall_k = {g("ALFRED_EXTRACT_RECALL_K", "5")}   # memories shown to the extractor for dedup   (hot-reloadable)
"""
```

(Keep the existing `[server]`/`[reasoning]`/`[persona]`/`[agent]`/`[logging]` blocks above unchanged — only the `[memory]` block grows.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_config_memory.py tests/test_config_bootstrap.py tests/test_config_toml.py -q`
Expected: PASS. (If `test_config_bootstrap.py` snapshots the template, update its expectation to include the new keys.)

- [ ] **Step 7: Commit**

```bash
git add brain/src/alfred_brain/config/ brain/tests/test_config_memory.py
git commit -m "feat(brain): config keys for memory formation (window + extract model/recall)"
```

---

### Task 5: Agent loop integration

Feed working-memory context into each turn, schedule extraction on overflow, capture the assistant reply, and replace the proactive nag with trust-labeled recall.

**Files:**
- Modify: `brain/src/alfred_brain/agent.py`
- Test: `brain/tests/test_agent_memory.py`

**Interfaces:**
- Consumes: `WorkingMemory` (Task 2), `Extractor` (Task 3), `MemoryRecord.status` (Task 1).
- Produces: `AgentLoop(..., working=None, extractor=None)`; trust-labeled system prompt; async extraction scheduling.

- [ ] **Step 1: Write failing tests**

Append to `brain/tests/test_agent_memory.py`:

```python
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
    assert "unconfirmed" not in prov.system
    assert "user lives in Athens" in prov.system
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_agent_memory.py -q`
Expected: FAIL (`AgentLoop() got an unexpected keyword argument 'working'`).

- [ ] **Step 3: Replace `MEMORY_GUIDANCE`**

```python
MEMORY_GUIDANCE = (
    "# Memory\n"
    "You have a persistent long-term memory; durable facts are saved automatically "
    "after the conversation — you do not need to call a tool to save them. Use the "
    "`remember` tool only when the user explicitly asks you to remember something. "
    "Relevant memories may be listed below. A memory marked 'unconfirmed' is not yet "
    "verified — treat it cautiously and confirm a high-stakes one with the user "
    "before relying on it."
)
```

- [ ] **Step 4: Extend `AgentLoop.__init__`**

```python
    def __init__(
        self,
        provider: ReasoningProvider,
        registry: ToolRegistry,
        system: str,
        max_iterations: int = 5,
        memory: "Memory | None" = None,
        recall_top_k: int = 5,
        working: "WorkingMemory | None" = None,
        extractor: "Extractor | None" = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._system = system
        self._max_iterations = max_iterations
        self._memory = memory
        self._recall_top_k = recall_top_k
        self._working = working
        self._extractor = extractor
        self._extract_tasks: set[asyncio.Task] = set()
```

Add imports near the top (use TYPE_CHECKING-free direct imports — no circularity, since these modules import only `providers.base` and `memory.record`):

```python
from .memory.working import WorkingMemory
from .memory.extraction import Extractor
```

- [ ] **Step 5: Rewrite the recall block + message assembly in `run`**

Replace the current `messages = [...]` / recall block with:

```python
        messages: list[TurnMessage] = []
        if self._working is not None:
            messages.extend(self._working.context())
        messages.append(TurnMessage(role="user", content=text))

        system = self._system
        if self._memory is not None:
            block = MEMORY_GUIDANCE
            hits = self._memory.recall(text, k=self._recall_top_k)
            if hits:
                lines = []
                for h in hits:
                    label = f"{h.type}, unconfirmed" if h.status == "provisional" else h.type
                    lines.append(f"- ({label}) {h.text}")
                block += "\n\nRelevant memories:\n" + "\n".join(lines)
            system = f"{self._system}\n\n{block}"

        assistant_parts: list[str] = []
```

- [ ] **Step 6: Capture assistant text + schedule extraction**

In the `TextChunk` branch, accumulate text:

```python
                    elif isinstance(ev, TextChunk):
                        assistant_parts.append(ev.text)
                        emit(AgentMessage(
                            v=1, id=new_id(), ts=now_ts(), type="agent.message",
                            corr=corr, text=ev.text, final=ev.final,
                        ))
```

After the `for _ in range(self._max_iterations):` loop completes and before `emit(AgentTurnComplete(... "completed"))`, add:

```python
            if self._working is not None:
                self._working.append("user", text)
                self._working.append("assistant", "".join(assistant_parts))
                if self._extractor is not None:
                    batch = self._working.take_batch()
                    if batch:
                        task = asyncio.create_task(self._extractor.extract(batch))
                        self._extract_tasks.add(task)
                        task.add_done_callback(self._extract_tasks.discard)
```

(This sits inside the `try`, so a cancelled/errored turn skips capture and scheduling.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_agent_memory.py tests/test_agent_loop.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add brain/src/alfred_brain/agent.py brain/tests/test_agent_memory.py
git commit -m "feat(brain): agent uses short-term memory + auto-extraction + trust-labeled recall"
```

---

### Task 6: Server wiring + shutdown flush

Construct and inject `WorkingMemory` + `Extractor`, keep the extractor's provider synced with the model picker, hot-reload window/recall_k, and flush on shutdown.

**Files:**
- Modify: `brain/src/alfred_brain/server.py`
- Test: `brain/tests/test_memory_wiring.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 4, 5.
- Produces: a fully wired brain where automatic memory formation runs end-to-end.

- [ ] **Step 1: Write failing tests**

Append to `brain/tests/test_memory_wiring.py` (use FastAPI `TestClient` as the existing tests in this repo do; the autouse conftest fixture isolates `$ALFRED_HOME`):

```python
from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.server import create_app


def test_app_wires_working_memory_and_extractor():
    app = create_app(Settings(_env_file=None))
    agent = app.state.agent
    assert agent._working is not None
    assert agent._extractor is not None


def test_shutdown_flushes_working_memory(monkeypatch):
    app = create_app(Settings(_env_file=None))
    agent = app.state.agent
    drained = {"called": False}

    async def fake_extract(batch):
        drained["called"] = True
        return []

    agent._extractor.extract = fake_extract  # type: ignore[method-assign]
    agent._working.append("user", "leftover fact")
    with TestClient(app):
        pass  # entering+exiting triggers startup/shutdown
    assert drained["called"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_memory_wiring.py -q`
Expected: FAIL (`AttributeError: 'AgentLoop' object has no attribute '_working'` is already satisfied by Task 5, so the failing assertion is the wiring: `agent._working is None`, and the shutdown hook does not exist yet).

- [ ] **Step 3: Wire construction in `create_app`**

Add imports:

```python
from .memory.working import WorkingMemory
from .memory.extraction import Extractor
```

After `memory` is constructed and the tools are registered, before building `agent`:

```python
    def _extraction_provider(s: Settings, active: ReasoningProvider) -> ReasoningProvider:
        if not s.memory_extract_model:
            return active
        try:
            return build_explicit(s, s.provider, s.memory_extract_model)
        except ValueError:
            logging.getLogger("alfred_brain").warning(
                "extract_model set but provider unavailable; using active provider")
            return active

    working = WorkingMemory(window=settings.memory_window_messages)
    extractor = Extractor(_extraction_provider(settings, provider), memory,
                          recall_k=settings.memory_extract_recall_k)
    agent = AgentLoop(provider, registry, system_prompt(settings.persona_intensity),
                      settings.max_tool_iterations,
                      memory=memory, recall_top_k=settings.memory_recall_top_k,
                      working=working, extractor=extractor)
```

(Replace the existing `agent = AgentLoop(...)` line.)

- [ ] **Step 4: Keep the extractor provider synced on model switch**

In `_apply_hot`, inside the `HOT_PROVIDER_FIELDS` block right after `agent.set_provider(new_provider)`:

```python
            if not new.memory_extract_model:
                extractor.set_provider(new_provider)
```

Add hot-reload for the two memory knobs (after the `memory_recall_top_k` block):

```python
        if old.memory_window_messages != new.memory_window_messages:
            working.set_window(new.memory_window_messages)
            changed.append("memory_window_messages")
        if old.memory_extract_recall_k != new.memory_extract_recall_k:
            extractor.set_recall_k(new.memory_extract_recall_k)
            changed.append("memory_extract_recall_k")
```

In the `POST /models` handler, after `agent.set_provider(new_provider)`:

```python
        if not state["settings"].memory_extract_model:
            extractor.set_provider(new_provider)
```

- [ ] **Step 5: Add the shutdown flush**

After `app = FastAPI(title="ALFRED brain")` wiring (anywhere after `working`/`extractor` exist, e.g. just before `return app`):

```python
    @app.on_event("shutdown")
    async def _flush_memory() -> None:
        await extractor.extract(working.drain())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_memory_wiring.py -q`
Expected: PASS.

- [ ] **Step 7: Run the full suite**

Run: `cd brain && uv run pytest -q`
Expected: all pass (no regressions). Fix any test that asserted the old `status == "active"` default or the removed proactive-guidance text.

- [ ] **Step 8: Commit**

```bash
git add brain/src/alfred_brain/server.py brain/tests/test_memory_wiring.py
git commit -m "feat(brain): wire short-term memory + extraction into the server (with shutdown flush)"
```

---

## Post-plan: docs

- [ ] Update `AGENTS.md` Phase-2 status note to mention formation (short-term buffer + extraction, provisional/confirmed) is implemented; review panel still deferred.
- [ ] Commit: `docs: note memory formation in Phase 2 status`.
