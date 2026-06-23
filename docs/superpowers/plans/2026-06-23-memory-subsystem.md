# Memory Subsystem (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the brain a `Memory` facade over an Obsidian-compatible markdown vault with local semantic recall, wired into the agent loop so ALFRED remembers across turns and restarts.

**Architecture:** A `memory/` package in the brain. Markdown notes in `$ALFRED_HOME/vault/memories/` are the source of truth (one atomic note per memory, YAML frontmatter + body). An in-memory `fastembed` (CPU) vector index, rebuilt from the vault at startup, powers cosine top-k recall. `VaultMemory` composes vault + index behind a `Memory` protocol. `AgentLoop` auto-injects recalled memories into the per-turn system prompt; `remember`/`recall`/`forget` tools let the LLM store/look-up/delete. A `[memory]` config section drives it.

**Tech Stack:** Python 3.12, `uv`, `fastembed` (CPU/ONNX + numpy), `pyyaml`, FastAPI, pytest.

## Global Constraints

- Python 3.12, managed by `uv`; run from inside `brain/` with `uv run …`.
- The frozen `protocol/` WS contract is **never** touched (no new wire messages).
- **Markdown is the source of truth**; the vector index is derived and rebuilt from the vault at startup. No on-disk vector cache (deferred).
- Vault is **Obsidian-compatible**: one atomic note per memory, YAML frontmatter, `[[wikilinks]]` allowed; the vector index lives **outside** the vault (here: in memory only).
- Memory uses **local** embeddings (`fastembed`, CPU) — independent of the reasoning provider; it must work when Groq/Gemini is offline.
- The embedder is **injectable** so unit tests use a fast deterministic fake and never download a model.
- Foundation formation is **explicit only** (LLM calls `remember`); no reflection/auto-capture.
- Existing brain tests stay green; `$ALFRED_HOME` is isolated per-test by the existing autouse `conftest.py` fixture.
- Commits: conventional, scoped (`feat(brain): …`), **no** `Co-Authored-By` / "authored by Claude" trailer.
- Deferred (NOT in this plan): Mem0, scoped profiles, provisional/confirmed, reflection, review panel, on-disk vector cache, distinct `search`, memory-as-service.

---

### Task 1: Memory record + facade protocol

**Files:**
- Create: `brain/src/alfred_brain/memory/__init__.py`
- Create: `brain/src/alfred_brain/memory/record.py`
- Test: `brain/tests/test_memory_record.py`

**Interfaces:**
- Produces: `MemoryRecord` (dataclass: `id: str, text: str, type: str, tags: list[str], status: str, created: str, path: pathlib.Path`); `Memory` (runtime-checkable Protocol with `remember(text, *, type="note", tags=None) -> MemoryRecord`, `recall(query, *, k=5) -> list[MemoryRecord]`, `forget(id) -> bool`, `all() -> list[MemoryRecord]`).

- [ ] **Step 1: Write the failing test** — `brain/tests/test_memory_record.py`

```python
from pathlib import Path

from alfred_brain.memory import MemoryRecord


def test_record_holds_fields():
    r = MemoryRecord(id="a1", text="hi", type="note", tags=["x"],
                     status="active", created="2026-06-23T00:00:00Z", path=Path("p.md"))
    assert r.id == "a1"
    assert r.tags == ["x"]
    assert r.type == "note"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_memory_record.py -q`
Expected: FAIL — `alfred_brain.memory` does not exist.

- [ ] **Step 3: Create `record.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class MemoryRecord:
    id: str
    text: str
    type: str
    tags: list[str]
    status: str
    created: str  # RFC 3339
    path: Path


@runtime_checkable
class Memory(Protocol):
    def remember(self, text: str, *, type: str = "note",
                 tags: list[str] | None = None) -> MemoryRecord: ...
    def recall(self, query: str, *, k: int = 5) -> list[MemoryRecord]: ...
    def forget(self, id: str) -> bool: ...
    def all(self) -> list[MemoryRecord]: ...
```

- [ ] **Step 4: Create `memory/__init__.py`**

```python
from .record import Memory, MemoryRecord

__all__ = ["Memory", "MemoryRecord"]
```

- [ ] **Step 5: Run the test**

Run: `cd brain && uv run pytest tests/test_memory_record.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/src/alfred_brain/memory/__init__.py brain/src/alfred_brain/memory/record.py brain/tests/test_memory_record.py
git commit -m "feat(brain): memory record + facade protocol"
```

---

### Task 2: Vault — Obsidian markdown read/write

**Files:**
- Modify: `brain/pyproject.toml` (add `pyyaml`)
- Create: `brain/src/alfred_brain/memory/vault.py`
- Test: `brain/tests/test_memory_vault.py`

**Interfaces:**
- Consumes: `MemoryRecord` (Task 1).
- Produces: `Vault(vault_dir: pathlib.Path)` with `write(text, *, type="note", tags=None) -> MemoryRecord`, `read(path) -> MemoryRecord`, `all() -> list[MemoryRecord]`, `delete(id) -> bool`. Notes live in `<vault_dir>/memories/<slug>-<id>.md`. Also `_slugify(text) -> str` and `_new_id() -> str` helpers.

- [ ] **Step 1: Add the dependency**

Edit `brain/pyproject.toml` `dependencies` list, adding after `"groq>=0.11,<1",`:
```toml
    "pyyaml>=6.0",
```
Run: `cd brain && uv sync`
Expected: installs `pyyaml`.

- [ ] **Step 2: Write the failing test** — `brain/tests/test_memory_vault.py`

```python
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
    assert again.status == "active"


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
```

- [ ] **Step 3: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_memory_vault.py -q`
Expected: FAIL — `alfred_brain.memory.vault` does not exist.

- [ ] **Step 4: Create `vault.py`**

```python
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .record import MemoryRecord

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _slugify(text: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-").split("-")
    slug = "-".join(w for w in words if w)[:40].strip("-")
    return slug or "memory"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Vault:
    """Reads/writes memories as Obsidian-compatible markdown notes.

    Layout: <vault_dir>/memories/<slug>-<id>.md  (frontmatter + body).
    The vault is the source of truth for the Memory subsystem.
    """

    def __init__(self, vault_dir: Path) -> None:
        self._dir = Path(vault_dir) / "memories"

    def write(self, text: str, *, type: str = "note",
              tags: list[str] | None = None) -> MemoryRecord:
        self._dir.mkdir(parents=True, exist_ok=True)
        rec = MemoryRecord(
            id=_new_id(), text=text, type=type, tags=list(tags or []),
            status="active", created=_now(),
            path=Path(),  # set below
        )
        rec.path = self._dir / f"{_slugify(text)}-{rec.id}.md"
        front = yaml.safe_dump(
            {"id": rec.id, "created": rec.created, "type": rec.type,
             "tags": rec.tags, "status": rec.status},
            sort_keys=False, allow_unicode=True,
        )
        rec.path.write_text(f"---\n{front}---\n\n{text}\n", encoding="utf-8")
        return rec

    def read(self, path: Path) -> MemoryRecord:
        raw = Path(path).read_text(encoding="utf-8")
        m = _FRONTMATTER.match(raw)
        if not m:
            raise ValueError(f"not a memory note (no frontmatter): {path}")
        meta = yaml.safe_load(m.group(1)) or {}
        return MemoryRecord(
            id=str(meta.get("id", "")), text=m.group(2).strip(),
            type=str(meta.get("type", "note")), tags=list(meta.get("tags") or []),
            status=str(meta.get("status", "active")),
            created=str(meta.get("created", "")), path=Path(path),
        )

    def all(self) -> list[MemoryRecord]:
        if not self._dir.is_dir():
            return []
        return [self.read(p) for p in sorted(self._dir.glob("*.md"))]

    def delete(self, id: str) -> bool:
        for rec in self.all():
            if rec.id == id:
                rec.path.unlink()
                return True
        return False
```

- [ ] **Step 5: Run the test**

Run: `cd brain && uv run pytest tests/test_memory_vault.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/pyproject.toml brain/uv.lock brain/src/alfred_brain/memory/vault.py brain/tests/test_memory_vault.py
git commit -m "feat(brain): memory vault — Obsidian markdown notes (frontmatter + body)"
```

---

### Task 3: Embedding index (fastembed + cosine top-k)

**Files:**
- Modify: `brain/pyproject.toml` (add `fastembed`)
- Create: `brain/src/alfred_brain/memory/index.py`
- Test: `brain/tests/test_memory_index.py`

**Interfaces:**
- Produces: `Embedder` (Protocol: `embed(texts: list[str]) -> list[list[float]]`); `FastEmbedEmbedder(model_name="BAAI/bge-small-en-v1.5")` implementing it; `VectorIndex(embedder: Embedder)` with `add(id, text)`, `remove(id) -> bool`, `search(query, k) -> list[tuple[str, float]]` (id, score; highest first), `clear()`, `__len__`.

- [ ] **Step 1: Add the dependency**

Edit `brain/pyproject.toml` `dependencies`, adding after `"pyyaml>=6.0",`:
```toml
    "fastembed>=0.3,<1",
```
Run: `cd brain && uv sync`
Expected: installs `fastembed` (+ `onnxruntime`, `numpy`).

- [ ] **Step 2: Write the failing test** — `brain/tests/test_memory_index.py`

```python
from alfred_brain.memory.index import VectorIndex


class FakeEmbedder:
    """Deterministic, offline: vector = per-word counts over a tiny vocab,
    so cosine similarity tracks word overlap."""
    VOCAB = ["alpha", "beta", "gamma", "delta"]

    def embed(self, texts):
        out = []
        for t in texts:
            tl = t.lower()
            out.append([float(tl.count(w)) for w in self.VOCAB])
        return out


def test_search_ranks_by_similarity():
    idx = VectorIndex(FakeEmbedder())
    idx.add("a", "alpha alpha")
    idx.add("b", "beta")
    idx.add("c", "gamma delta")
    hits = idx.search("alpha", k=2)
    assert hits[0][0] == "a"            # most similar to "alpha"
    assert len(hits) == 2
    assert all(isinstance(score, float) for _, score in hits)


def test_empty_index_returns_nothing():
    assert VectorIndex(FakeEmbedder()).search("alpha", k=5) == []


def test_remove_drops_from_results():
    idx = VectorIndex(FakeEmbedder())
    idx.add("a", "alpha")
    assert idx.remove("a") is True
    assert idx.search("alpha", k=5) == []
    assert idx.remove("a") is False


def test_zero_vector_query_is_safe():
    idx = VectorIndex(FakeEmbedder())
    idx.add("a", "alpha")
    # query has no vocab words -> zero vector -> no crash, score 0
    assert idx.search("zzz", k=5)[0][0] == "a"
```

- [ ] **Step 3: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_memory_index.py -q`
Expected: FAIL — `alfred_brain.memory.index` does not exist.

- [ ] **Step 4: Create `index.py`**

```python
from __future__ import annotations

from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedEmbedder:
    """Local CPU embeddings via fastembed (ONNX).

    The model is loaded lazily on the FIRST embed() call, never in __init__ — so
    constructing the brain (create_app) with an empty vault does no model load or
    download. This keeps the test suite fast/offline (empty index -> no embed).
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self._model_name = model_name
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        return [v.tolist() for v in self._model.embed(texts)]


def _cosine(q: np.ndarray, m: np.ndarray) -> np.ndarray:
    qn = np.linalg.norm(q)
    mn = np.linalg.norm(m, axis=1)
    denom = mn * qn
    sims = np.zeros(m.shape[0], dtype=float)
    nz = denom > 0
    sims[nz] = (m[nz] @ q) / denom[nz]
    return sims


class VectorIndex:
    """In-memory vector store. Rebuilt from the vault at startup."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._ids: list[str] = []
        self._vectors: list[list[float]] = []

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, id: str, text: str) -> None:
        self._ids.append(id)
        self._vectors.append(self._embedder.embed([text])[0])

    def remove(self, id: str) -> bool:
        try:
            i = self._ids.index(id)
        except ValueError:
            return False
        self._ids.pop(i)
        self._vectors.pop(i)
        return True

    def clear(self) -> None:
        self._ids.clear()
        self._vectors.clear()

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        if not self._ids:
            return []
        q = np.asarray(self._embedder.embed([query])[0], dtype=float)
        m = np.asarray(self._vectors, dtype=float)
        sims = _cosine(q, m)
        order = np.argsort(-sims)[:k]
        return [(self._ids[i], float(sims[i])) for i in order]
```

- [ ] **Step 5: Run the test**

Run: `cd brain && uv run pytest tests/test_memory_index.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/pyproject.toml brain/uv.lock brain/src/alfred_brain/memory/index.py brain/tests/test_memory_index.py
git commit -m "feat(brain): in-memory vector index with fastembed + cosine top-k"
```

---

### Task 4: VaultMemory facade

**Files:**
- Create: `brain/src/alfred_brain/memory/facade.py`
- Modify: `brain/src/alfred_brain/memory/__init__.py` (export `VaultMemory`)
- Test: `brain/tests/test_memory_facade.py`

**Interfaces:**
- Consumes: `Vault` (Task 2), `VectorIndex`/`Embedder` (Task 3), `MemoryRecord`/`Memory` (Task 1).
- Produces: `VaultMemory(vault_dir: pathlib.Path, embedder: Embedder)` implementing `Memory` (`remember`, `recall`, `forget`, `all`). Builds its index from the existing vault on construction.

- [ ] **Step 1: Write the failing test** — `brain/tests/test_memory_facade.py`

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_memory_facade.py -q`
Expected: FAIL — `VaultMemory` not importable.

- [ ] **Step 3: Create `facade.py`**

```python
from __future__ import annotations

from pathlib import Path

from .index import Embedder, VectorIndex
from .record import MemoryRecord
from .vault import Vault


class VaultMemory:
    """Memory implementation: markdown vault (source of truth) + in-memory index.

    The index is rebuilt from the vault on construction, so it always reflects
    the markdown on disk.
    """

    def __init__(self, vault_dir: Path, embedder: Embedder) -> None:
        self._vault = Vault(vault_dir)
        self._index = VectorIndex(embedder)
        self._records: dict[str, MemoryRecord] = {}
        for rec in self._vault.all():
            self._records[rec.id] = rec
            self._index.add(rec.id, rec.text)

    def remember(self, text: str, *, type: str = "note",
                 tags: list[str] | None = None) -> MemoryRecord:
        rec = self._vault.write(text, type=type, tags=tags)
        self._records[rec.id] = rec
        self._index.add(rec.id, rec.text)
        return rec

    def recall(self, query: str, *, k: int = 5) -> list[MemoryRecord]:
        return [self._records[i] for i, _ in self._index.search(query, k)
                if i in self._records]

    def forget(self, id: str) -> bool:
        if not self._vault.delete(id):
            return False
        self._records.pop(id, None)
        self._index.remove(id)
        return True

    def all(self) -> list[MemoryRecord]:
        return list(self._records.values())
```

- [ ] **Step 4: Export from `memory/__init__.py`**

```python
from .facade import VaultMemory
from .record import Memory, MemoryRecord

__all__ = ["Memory", "MemoryRecord", "VaultMemory"]
```

- [ ] **Step 5: Run the test**

Run: `cd brain && uv run pytest tests/test_memory_facade.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/src/alfred_brain/memory/facade.py brain/src/alfred_brain/memory/__init__.py brain/tests/test_memory_facade.py
git commit -m "feat(brain): VaultMemory facade (vault + index, rebuilt from disk)"
```

---

### Task 5: Memory tools (remember / recall / forget)

**Files:**
- Create: `brain/src/alfred_brain/memory/tools.py`
- Test: `brain/tests/test_memory_tools.py`

**Interfaces:**
- Consumes: `Memory` facade (Tasks 1/4), `RiskTier` from `alfred_protocol`, the `Tool` shape (`name`, `description`, `risk`, `parameters: dict`, `async run(args: dict) -> str`).
- Produces: `RememberTool(memory)`, `RecallTool(memory)`, `ForgetTool(memory)` — each a `Tool`. `RecallTool.run` returns lines of `"<id>: (<type>) <text>"` so the LLM gets ids it can pass to `forget`.

- [ ] **Step 1: Write the failing test** — `brain/tests/test_memory_tools.py`

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_memory_tools.py -q`
Expected: FAIL — `alfred_brain.memory.tools` does not exist.

- [ ] **Step 3: Create `tools.py`**

```python
from __future__ import annotations

from alfred_protocol import RiskTier

from .record import Memory


class RememberTool:
    name = "remember"
    description = ("Store a durable memory the user wants kept (facts, preferences, "
                   "project knowledge). Use when the user says to remember something "
                   "or shares a lasting fact.")
    risk = RiskTier.sensitive
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The memory to store."},
            "type": {"type": "string",
                     "description": "fact | preference | project | note",
                     "default": "note"},
            "tags": {"type": "array", "items": {"type": "string"},
                     "description": "Optional tags."},
        },
        "required": ["text"],
    }

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    async def run(self, args: dict) -> str:
        rec = self._memory.remember(
            str(args.get("text", "")),
            type=str(args.get("type", "note")),
            tags=list(args.get("tags") or []),
        )
        return f"Remembered ({rec.type}) as {rec.id}."


class RecallTool:
    name = "recall"
    description = "Search stored memories for anything relevant to a query."
    risk = RiskTier.safe
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look up."},
            "k": {"type": "integer", "description": "Max results (default 5)."},
        },
        "required": ["query"],
    }

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    async def run(self, args: dict) -> str:
        k = int(args.get("k", 5))
        hits = self._memory.recall(str(args.get("query", "")), k=k)
        if not hits:
            return "No relevant memories."
        return "\n".join(f"{h.id}: ({h.type}) {h.text}" for h in hits)


class ForgetTool:
    name = "forget"
    description = "Delete a stored memory by its id (ids come from recall results)."
    risk = RiskTier.sensitive
    parameters = {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "The memory id to delete."}},
        "required": ["id"],
    }

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    async def run(self, args: dict) -> str:
        ok = self._memory.forget(str(args.get("id", "")))
        return "Forgotten." if ok else "No memory with that id."
```

- [ ] **Step 4: Run the test**

Run: `cd brain && uv run pytest tests/test_memory_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brain/src/alfred_brain/memory/tools.py brain/tests/test_memory_tools.py
git commit -m "feat(brain): memory tools — remember / recall / forget"
```

---

### Task 6: Config `[memory]` section

**Files:**
- Modify: `brain/src/alfred_brain/config/settings.py` (3 fields + `ENV_ALIASES`)
- Modify: `brain/src/alfred_brain/config/toml_source.py` (`SECTION_MAP`)
- Modify: `brain/src/alfred_brain/config/bootstrap.py` (template `[memory]` block)
- Test: `brain/tests/test_config_memory.py`

**Interfaces:**
- Produces: `Settings.memory_vault_dir: str | None` (default `None` → resolved to `$ALFRED_HOME/vault` by callers), `Settings.memory_embed_model: str` (default `"BAAI/bge-small-en-v1.5"`), `Settings.memory_recall_top_k: int` (default `5`, `ge=1`). Env aliases `ALFRED_VAULT_DIR`, `ALFRED_EMBED_MODEL`, `ALFRED_RECALL_TOP_K`.

- [ ] **Step 1: Write the failing test** — `brain/tests/test_config_memory.py`

```python
import pytest
from pydantic import ValidationError

from alfred_brain.config import Settings
from alfred_brain.config.bootstrap import render_template


def test_memory_defaults():
    s = Settings(_env_file=None)
    assert s.memory_vault_dir is None
    assert s.memory_embed_model == "BAAI/bge-small-en-v1.5"
    assert s.memory_recall_top_k == 5


def test_memory_from_toml(tmp_path, monkeypatch):
    home = tmp_path / "alfred-home"
    home.mkdir(parents=True)
    (home / "config.toml").write_text(
        "[memory]\nrecall_top_k = 9\nembed_model = \"x\"\n", encoding="utf-8")
    monkeypatch.setenv("ALFRED_HOME", str(home))
    s = Settings(_env_file=None)
    assert s.memory_recall_top_k == 9
    assert s.memory_embed_model == "x"


def test_recall_top_k_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(memory_recall_top_k=0, _env_file=None)


def test_template_documents_memory_section():
    body = render_template({})
    assert "[memory]" in body
    assert "recall_top_k" in body
    assert "embed_model" in body
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_config_memory.py -q`
Expected: FAIL — `memory_*` fields and `[memory]` template missing.

- [ ] **Step 3: Add the fields to `settings.py`**

In `ENV_ALIASES`, add after `"log_level": "ALFRED_LOG_LEVEL",`:
```python
    "memory_vault_dir": "ALFRED_VAULT_DIR",
    "memory_embed_model": "ALFRED_EMBED_MODEL",
    "memory_recall_top_k": "ALFRED_RECALL_TOP_K",
```
In the `Settings` class, add after the `log_level` field:
```python
    memory_vault_dir: str | None = Field(default=None, validation_alias="ALFRED_VAULT_DIR")
    memory_embed_model: str = Field(
        default="BAAI/bge-small-en-v1.5", validation_alias="ALFRED_EMBED_MODEL")
    memory_recall_top_k: int = Field(
        default=5, ge=1, validation_alias="ALFRED_RECALL_TOP_K")
```

- [ ] **Step 4: Add the mapping to `toml_source.py`**

In `SECTION_MAP`, add after `("logging", "level"): "log_level",`:
```python
    ("memory", "vault_dir"): "memory_vault_dir",
    ("memory", "embed_model"): "memory_embed_model",
    ("memory", "recall_top_k"): "memory_recall_top_k",
```

- [ ] **Step 5: Add the `[memory]` block to the template in `bootstrap.py`**

In `render_template`, append a `[memory]` section to the returned string, just before the closing `[logging]` section (or after it). Replace the `[logging]` block at the end of the f-string with:
```python
[logging]
level = "{g("ALFRED_LOG_LEVEL", "INFO")}"   # DEBUG | INFO | WARNING | ERROR | CRITICAL   (hot-reloadable)

[memory]
# vault_dir = ""   # [*] default: $ALFRED_HOME/vault  (an Obsidian-compatible vault)
embed_model = "{g("ALFRED_EMBED_MODEL", "BAAI/bge-small-en-v1.5")}"   # [*] local CPU embedding model
recall_top_k = {g("ALFRED_RECALL_TOP_K", "5")}   # integer >= 1   (hot-reloadable)
"""
```
(`vault_dir` is left commented so the default applies; an empty string would be skipped by the flattening source anyway.)

- [ ] **Step 6: Run the test**

Run: `cd brain && uv run pytest tests/test_config_memory.py -q`
Expected: PASS.

- [ ] **Step 7: Run the full config suite (no regressions)**

Run: `cd brain && uv run pytest tests/test_config.py tests/test_config_toml.py tests/test_config_bootstrap.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add brain/src/alfred_brain/config/settings.py brain/src/alfred_brain/config/toml_source.py brain/src/alfred_brain/config/bootstrap.py brain/tests/test_config_memory.py
git commit -m "feat(brain): [memory] config section (vault_dir, embed_model, recall_top_k)"
```

---

### Task 7: Wire memory into the agent loop + server

**Files:**
- Modify: `brain/src/alfred_brain/agent.py` (memory dependency + per-turn recall + setter)
- Modify: `brain/src/alfred_brain/server.py` (build VaultMemory, register tools, inject; reload recall_top_k)
- Test: `brain/tests/test_agent_memory.py`, `brain/tests/test_memory_wiring.py`

**Interfaces:**
- Consumes: `VaultMemory` (Task 4), the three tools (Task 5), `Settings.memory_*` (Task 6), `AgentLoop` (existing), `FastEmbedEmbedder` (Task 3).
- Produces: `AgentLoop(..., memory: Memory | None = None, recall_top_k: int = 5)` with `set_recall_top_k(n)`; `run` augments the system prompt with recalled memories when `memory` is set. `create_app` builds memory, registers tools, injects into the agent, and applies `recall_top_k` on `/config/reload`.

- [ ] **Step 1: Write the failing tests**

`brain/tests/test_agent_memory.py`:
```python
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
```

`brain/tests/test_memory_wiring.py`:
```python
from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.memory import VaultMemory
from alfred_brain.server import create_app
from tests.test_memory_index import FakeEmbedder


def test_memory_tools_registered_and_reload_applies_top_k(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "home"))
    # inject a fake-embedder memory so the test stays offline/deterministic
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    app = create_app(Settings(provider="scripted", _env_file=None), memory=mem)
    # memory tools are available to the agent
    assert app.state.agent._registry.has("remember")
    assert app.state.agent._registry.has("recall")
    assert app.state.agent._registry.has("forget")

    # recall_top_k is hot-reloadable
    home = tmp_path / "home"
    (home / "config.toml").write_text(
        "[memory]\nrecall_top_k = 3\n", encoding="utf-8")
    TestClient(app).post("/config/reload")
    assert app.state.agent._recall_top_k == 3
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd brain && uv run pytest tests/test_agent_memory.py tests/test_memory_wiring.py -q`
Expected: FAIL — `AgentLoop` has no `memory`/`recall_top_k`; tools not registered.

- [ ] **Step 3: Update `AgentLoop` in `agent.py`**

Change `__init__` to accept memory + recall_top_k (keep them optional so existing construction sites are unaffected):
```python
    def __init__(
        self,
        provider: ReasoningProvider,
        registry: ToolRegistry,
        system: str,
        max_iterations: int = 5,
        memory: "Memory | None" = None,
        recall_top_k: int = 5,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._system = system
        self._max_iterations = max_iterations
        self._memory = memory
        self._recall_top_k = recall_top_k
```
Add the import at the top of `agent.py` (alongside the other imports):
```python
from .memory import Memory
```
Add a setter next to `set_max_iterations`:
```python
    def set_recall_top_k(self, n: int) -> None:
        self._recall_top_k = n
```
At the start of `run`, build the effective system from recalled memories. Replace the line `messages: list[TurnMessage] = [TurnMessage(role="user", content=text)]` and the first `async for ev in self._provider.run_turn(messages, self._registry.specs(), self._system)` so the turn uses an augmented system computed once:
```python
        messages: list[TurnMessage] = [TurnMessage(role="user", content=text)]
        system = self._system
        if self._memory is not None:
            block = ("# Memory\nYou have a persistent memory; use the remember "
                     "tool to store durable facts the user shares.")
            hits = self._memory.recall(text, k=self._recall_top_k)
            if hits:
                block += "\nRelevant memories:\n" + "\n".join(
                    f"- ({h.type}) {h.text}" for h in hits)
            system = f"{self._system}\n\n{block}"
        try:
            for _ in range(self._max_iterations):
                tool_results: list[tuple[ToolCallRequest, str]] = []
                async for ev in self._provider.run_turn(
                    messages, self._registry.specs(), system
                ):
```
(The rest of `run` is unchanged — it now references the local `system`.)

- [ ] **Step 4: Wire it in `server.py`**

Add imports (alongside the others):
```python
from .memory import VaultMemory
from .memory.index import FastEmbedEmbedder
from .memory.tools import ForgetTool, RecallTool, RememberTool
from .config import home  # if not already imported via .config
```
Change the `create_app` signature to accept an injectable memory (mirroring the existing `provider` injection), so tests can pass a fake-embedder-backed memory and stay offline:
```python
def create_app(settings: Settings, provider: ReasoningProvider | None = None,
               memory: "Memory | None" = None) -> FastAPI:
```
Add `from .memory import Memory` to the imports for that annotation.

In `create_app`, after `registry.register(EchoTool())` and before building `agent`, build memory (if not injected) and register its tools:
```python
    if memory is None:
        vault_dir = settings.memory_vault_dir or str(home() / "vault")
        memory = VaultMemory(vault_dir, FastEmbedEmbedder(settings.memory_embed_model))
    registry.register(RememberTool(memory))
    registry.register(RecallTool(memory))
    registry.register(ForgetTool(memory))
```
(The real `FastEmbedEmbedder` is lazy, so building it with an empty vault loads no model — existing `create_app` tests stay fast.)
Change the `agent = AgentLoop(...)` construction to inject memory + top-k:
```python
    agent = AgentLoop(provider, registry, system_prompt(settings.persona_intensity),
                      settings.max_tool_iterations,
                      memory=memory, recall_top_k=settings.memory_recall_top_k)
```
In `_apply_hot`, after the `max_tool_iterations` block, apply `recall_top_k`:
```python
        if old.memory_recall_top_k != new.memory_recall_top_k:
            agent.set_recall_top_k(new.memory_recall_top_k)
            changed.append("memory_recall_top_k")
```

- [ ] **Step 5: Run the tests**

Run: `cd brain && uv run pytest tests/test_agent_memory.py tests/test_memory_wiring.py -q`
Expected: PASS.

- [ ] **Step 6: Run the FULL suite (last task — everything green)**

Run: `cd brain && uv run pytest -q`
Expected: PASS (all prior brain tests + the new memory suites; the 2 live-smoke integration tests stay skipped).

- [ ] **Step 7: Update docs**

In `brain/README.md`, add to the run/config section a line:
```markdown
Memory: ALFRED stores durable facts as Obsidian-compatible markdown in
`$ALFRED_HOME/vault/` (open the folder in Obsidian to browse). Recall is local
(fastembed, CPU) and auto-injected each turn; the `remember`/`recall`/`forget`
tools let ALFRED manage it. Tune `[memory] recall_top_k` / `embed_model` in config.
```

- [ ] **Step 8: Commit**

```bash
git add brain/src/alfred_brain/agent.py brain/src/alfred_brain/server.py brain/README.md brain/tests/test_agent_memory.py brain/tests/test_memory_wiring.py
git commit -m "feat(brain): wire memory into the agent loop (recall injection + tools + reload)"
```

---

## Self-Review

**Spec coverage:**
- §3 storage model (Obsidian atomic notes, frontmatter, source of truth) → Task 2. ✅
- §4 retrieval (fastembed CPU, in-memory index, cosine top-k, rebuild) → Tasks 3, 4. ✅
- §5 facade (`remember`/`recall`/`forget`/`all`, `MemoryRecord`) → Tasks 1, 4. ✅
- §6 agent-loop integration (recall→prompt, three tools) → Tasks 5, 7. ✅
- §7 formation (explicit via `remember` tool) → Task 5 (tool) + Task 7 (wiring). ✅
- §8 config `[memory]` (vault_dir/embed_model/recall_top_k, hot/startup) → Tasks 6, 7. ✅
- §9 code shape (record/vault/index/facade/tools) → Tasks 1–5. ✅
- §10 testing (temp vault, fake embedder, gated real fastembed) → fake embedder in Task 3, reused throughout; live model never loaded in unit tests. ✅
- §11 deps (`fastembed`, `pyyaml`) → Tasks 2, 3. ✅

**Placeholder scan:** none — every step carries concrete code/commands.

**Type consistency:** `MemoryRecord` fields (Task 1) are used identically in vault/facade/tools; `Vault` API (`write/read/all/delete`) consistent across Tasks 2/4; `VectorIndex` (`add/remove/search/clear/__len__`) consistent Tasks 3/4; `Embedder.embed(list[str])->list[list[float]]` consistent Tasks 3/4 and the `FakeEmbedder` test double; `VaultMemory(vault_dir, embedder)` signature consistent Tasks 4/5/7; `AgentLoop(..., memory=None, recall_top_k=5)` + `set_recall_top_k` consistent Tasks 7. `recall(query, *, k=)` keyword-only across facade/tools/agent.

**Note on a deferred-minor carried in:** the gated live smoke test for real `fastembed` is optional and not authored as a separate task (the fake embedder covers behavior); add one under `@pytest.mark.integration` if desired during execution.
