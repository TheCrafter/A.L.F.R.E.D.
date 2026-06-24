# Memory: Entity GC + Canonical Identity + Sensitive Handling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Reference-counted entity-hub cleanup on delete, a configured canonical user identity for linking, and extraction that stores (never refuses) sensitive facts as tagged provisional memories — and stops auto-promoting provisional ones.

**Architecture:** Brain-only. GC lives in the facade (it holds all records for reference counting) + a vault `delete_entity`. Identity + sensitive/no-promote behavior are extraction-prompt changes plus a deterministic provisional safety net. No `protocol/`, no UI, no wire changes.

**Tech Stack:** Python 3.12 (`uv`), pytest.

## Global Constraints

- Python 3.12; run from `brain/` via `uv run …`. `uv run pytest -q` green after each task.
- Strict typing, no `Any`. `protocol/` frozen — untouched. No wire/UI changes.
- Commit messages plain, conventional, scoped `feat(brain): …`; **NO `Co-Authored-By` / "authored by Claude" trailer.**
- Entity hubs are Obsidian-only (not in recall, `all()`, or the panel) — GC is pure vault cleanup, emits no events.
- Tests reuse `tests/conftest.py` ($ALFRED_HOME isolation) and `tests/test_memory_index.py::FakeEmbedder`.

---

### Task 1: Config `user_name`

**Files:** Modify `brain/src/alfred_brain/config/settings.py`, `config/toml_source.py`, `config/bootstrap.py`. Test: `brain/tests/test_config_memory.py`.

**Interfaces:** Produces `Settings.memory_user_name: str = ""` (env `ALFRED_USER_NAME`, TOML `[memory] user_name`).

- [ ] **Step 1: Failing test** — append to `tests/test_config_memory.py`:

```python
def test_user_name_default_empty(monkeypatch):
    monkeypatch.delenv("ALFRED_USER_NAME", raising=False)
    from alfred_brain.config import Settings
    assert Settings(_env_file=None).memory_user_name == ""


def test_user_name_from_env(monkeypatch):
    monkeypatch.setenv("ALFRED_USER_NAME", "Dimitris")
    from alfred_brain.config import Settings
    assert Settings(_env_file=None).memory_user_name == "Dimitris"


def test_user_name_from_toml(tmp_path):
    from alfred_brain.config.toml_source import read_flat_toml
    p = tmp_path / "config.toml"
    p.write_text("[memory]\nuser_name = \"Dimitris\"\n", encoding="utf-8")
    assert read_flat_toml(p)["memory_user_name"] == "Dimitris"
```

- [ ] **Step 2: Run → fail** — `cd brain && uv run pytest tests/test_config_memory.py -q` (AttributeError).

- [ ] **Step 3: `settings.py`** — add alias + field:

```python
    "memory_user_name": "ALFRED_USER_NAME",
```
```python
    memory_user_name: str = Field(default="", validation_alias="ALFRED_USER_NAME")
```

- [ ] **Step 4: `toml_source.py`** — add to `SECTION_MAP`:

```python
    ("memory", "user_name"): "memory_user_name",
```

- [ ] **Step 5: `bootstrap.py`** — add to the `[memory]` template block:

```python
# user_name = ""   # [*] your name, so memories about you link to [[name]] instead of a generic 'User'
```

- [ ] **Step 6: Run → pass** — `cd brain && uv run pytest tests/test_config_memory.py tests/test_config_bootstrap.py -q`. (If the bootstrap test snapshots the template, update it.)

- [ ] **Step 7: Commit** — `git add brain/src/alfred_brain/config brain/tests/test_config_memory.py && git commit -m "feat(brain): config user_name for canonical memory identity"`

---

### Task 2: Reference-counted entity GC

**Files:** Modify `brain/src/alfred_brain/memory/vault.py`, `memory/facade.py`. Test: `brain/tests/test_memory_facade.py`, `brain/tests/test_memory_vault.py`.

**Interfaces:** Produces `Vault.delete_entity(stem) -> bool`; `VaultMemory.forget`/`update` GC orphaned hubs via a private `_gc_entity(stem)`.

- [ ] **Step 1: Failing tests**

`tests/test_memory_vault.py`:

```python
def test_delete_entity_unlinks(tmp_path):
    v = Vault(tmp_path / "vault")
    v.ensure_entity("Berlin", "place")
    assert v.delete_entity("Berlin") is True
    assert not (tmp_path / "vault" / "entities" / "Berlin.md").exists()
    assert v.delete_entity("Berlin") is False  # already gone
```

`tests/test_memory_facade.py`:

```python
def _mem(tmp_path):
    from alfred_brain.memory import VaultMemory
    from tests.test_memory_index import FakeEmbedder
    return VaultMemory(tmp_path / "vault", FakeEmbedder())


def test_forget_gcs_orphan_entity(tmp_path):
    mem = _mem(tmp_path)
    stem = mem.ensure_entity("Berlin", "place")
    rec = mem.remember("User may move to Berlin.", title="Berlin move", links=[stem])
    mem.forget(rec.id)
    assert ("Berlin", "place") not in mem.list_entities()  # orphan removed


def test_forget_keeps_shared_entity(tmp_path):
    mem = _mem(tmp_path)
    d = mem.ensure_entity("Dimitris", "person")
    a = mem.remember("Fact A about user.", title="A", links=[d])
    mem.remember("Fact B about user.", title="B", links=[d])
    mem.forget(a.id)
    assert ("Dimitris", "person") in mem.list_entities()  # still referenced by B


def test_update_gcs_dropped_orphan_link(tmp_path):
    mem = _mem(tmp_path)
    old = mem.ensure_entity("Berlin", "place")
    new = mem.ensure_entity("Athens", "place")
    rec = mem.remember("User may move to Berlin.", title="Move", links=[old])
    mem.update(rec.id, text="User will move to Athens.", links=[new])
    ents = dict(mem.list_entities())
    assert "Berlin" not in ents      # dropped + orphaned -> GC'd
    assert "Athens" in ents
```

- [ ] **Step 2: Run → fail** — `cd brain && uv run pytest tests/test_memory_vault.py tests/test_memory_facade.py -q`.

- [ ] **Step 3: `vault.py` — `delete_entity`**

```python
    def delete_entity(self, stem: str) -> bool:
        path = self._entities / f"{stem}.md"
        if not path.exists():
            return False
        path.unlink()
        return True
```

- [ ] **Step 4: `facade.py` — GC helper + forget + update**

```python
    def _gc_entity(self, stem: str) -> None:
        if any(stem in rec.links for rec in self._records.values()):
            return
        self._vault.delete_entity(stem)

    def forget(self, id: str) -> bool:
        rec = self._records.get(id)
        if not self._vault.delete(id):
            return False
        self._records.pop(id, None)
        self._index.remove(id)
        for stem in (rec.links if rec else []):
            self._gc_entity(stem)
        return True

    def update(self, id: str, *, text: str | None = None, type: str | None = None,
               tags: list[str] | None = None, status: str | None = None,
               title: str | None = None,
               links: list[str] | None = None) -> MemoryRecord | None:
        old = self._records.get(id)
        old_links = list(old.links) if old else []
        rec = self._vault.update(id, text=text, type=type, tags=tags,
                                 status=status, title=title, links=links)
        if rec is None:
            return None
        self._records[rec.id] = rec
        if text is not None:
            self._index.remove(rec.id)
            self._index.add(rec.id, rec.text)
        if links is not None:
            for stem in old_links:
                if stem not in rec.links:
                    self._gc_entity(stem)
        return rec
```

(Replace the existing `forget`/`update`. The `_gc_entity` check runs AFTER `_records` is updated, so it reflects the post-change link set.)

- [ ] **Step 5: Run → pass** — `cd brain && uv run pytest tests/test_memory_vault.py tests/test_memory_facade.py -q`.

- [ ] **Step 6: Commit** — `git add brain/src/alfred_brain/memory/vault.py brain/src/alfred_brain/memory/facade.py brain/tests/test_memory_vault.py brain/tests/test_memory_facade.py && git commit -m "feat(brain): reference-counted entity-hub GC on memory delete/relink"`

---

### Task 3: Extraction — identity, no-refuse/sensitive, no-auto-promote

**Files:** Modify `brain/src/alfred_brain/memory/extraction.py`, `brain/src/alfred_brain/server.py`. Test: `brain/tests/test_memory_extraction.py`.

**Interfaces:** Consumes Task 1's `memory_user_name`. Produces `Extractor(…, user_name="")` whose system prompt carries the identity line; `_apply` forces `provisional` for `sensitive`-tagged ops; updated `EXTRACTION_SYSTEM`.

- [ ] **Step 1: Failing tests** — append to `tests/test_memory_extraction.py`:

```python
def test_extraction_system_no_autopromote_and_no_refuse():
    from alfred_brain.memory.extraction import EXTRACTION_SYSTEM
    low = EXTRACTION_SYSTEM.lower()
    assert "never refuse" in low
    assert "sensitive" in low
    # the old auto-promote instruction is gone
    assert "confirms a tentative existing memory" not in EXTRACTION_SYSTEM
```

The remaining tests are `async def` to match the file's existing style (a `_Capture` provider whose `run_turn` records the `system` it received; `_FakeProvider` and `_batch()` already exist in the file):

```python
async def test_user_name_adds_identity_instruction(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())

    class _Capture:
        name = "cap"
        def __init__(self): self.system = None
        async def run_turn(self, messages, tools, system):
            self.system = system
            yield TextChunk('{"operations": []}', final=True)

    prov = _Capture()
    await Extractor(prov, mem, user_name="Dimitris").extract(_batch())
    assert "Dimitris" in prov.system
    assert "User" in prov.system  # phrased as: never use a generic 'User' entity


async def test_no_user_name_no_identity_instruction(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())

    class _Capture:
        name = "cap"
        def __init__(self): self.system = None
        async def run_turn(self, messages, tools, system):
            self.system = system
            yield TextChunk('{"operations": []}', final=True)

    prov = _Capture()
    await Extractor(prov, mem).extract(_batch())   # no user_name
    assert "named" not in prov.system.lower() or "the user is named" not in prov.system.lower()


async def test_sensitive_tag_forces_provisional(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    prov = _FakeProvider(
        '{"operations": [{"action": "add", "text": "User IBAN is GR16 0110.", '
        '"title": "User IBAN", "tags": ["sensitive"], '
        '"confidence": "high", "stakes": "low"}]}')   # model wrongly said low stakes
    applied = await Extractor(prov, mem).extract(_batch())
    assert applied[0].status == "provisional"
    assert "sensitive" in applied[0].tags
```

- [ ] **Step 2: Run → fail** — `cd brain && uv run pytest tests/test_memory_extraction.py -q`.

- [ ] **Step 3: Rewrite `EXTRACTION_SYSTEM`** (remove the auto-promote line; add no-refuse/sensitive):

```python
EXTRACTION_SYSTEM = (
    "You extract durable, long-term memories from a conversation transcript. "
    "Keep ONLY lasting facts worth remembering across sessions: the user's "
    "identity, lasting preferences, ongoing projects, important people, and how "
    "the user wants the assistant to behave. Ignore greetings, one-off requests, "
    "and ephemeral chatter.\n\n"
    "You are given KNOWN entities, EXISTING memories (each with an id), and a "
    "TRANSCRIPT. For each durable fact:\n"
    "- If it refines or matches an existing memory, emit an \"update\" op with that "
    "id instead of duplicating it; otherwise emit an \"add\" op.\n"
    "- Give it a concise \"title\" (<= 6 words) that reads well as a note name.\n"
    "- List the \"entities\" it concerns as {name, type} with type one of "
    "person|place|org|project|topic. REUSE a KNOWN entity's exact name when it "
    "refers to the same thing, so notes link to the same hub.\n"
    "- Do NOT raise an existing memory's confidence or change its status unless the "
    "user EXPLICITLY restates or reaffirms that fact in THIS transcript.\n"
    "- Never refuse to store a durable fact. If a fact is sensitive (passwords, "
    "credentials, account/IBAN numbers, financial or private identifiers), still "
    "store it: set stakes \"high\" and add the tag \"sensitive\".\n\n"
    "Set \"confidence\" (high|low) by certainty, and \"stakes\" (low|high) by how "
    "much acting on it wrongly would matter (security, money, identity, "
    "irreversible actions are high).\n\n"
    "Respond with ONLY a JSON object, no prose:\n"
    '{"operations": [{"action": "add", "text": "...", "title": "...", '
    '"type": "fact", "tags": [], "confidence": "high", "stakes": "low", '
    '"entities": [{"name": "...", "type": "person"}]}]}\n'
    "Use an empty operations list when nothing durable is present."
)
```

- [ ] **Step 4: `Extractor` — `user_name` + per-call system prompt**

In `__init__` add the kwarg and store it:

```python
    def __init__(self, provider: ReasoningProvider, memory: Memory,
                 *, recall_k: int = 5,
                 on_formed: "Callable[[MemoryRecord, str], None] | None" = None,
                 user_name: str = "") -> None:
        self._provider = provider
        self._memory = memory
        self._recall_k = recall_k
        self._on_formed = on_formed
        self._user_name = user_name
        self._lock = asyncio.Lock()
```

Add a helper and use it in `_call` (replace the `EXTRACTION_SYSTEM` arg passed to `run_turn` with `self._system_prompt()`):

```python
    def _system_prompt(self) -> str:
        if not self._user_name:
            return EXTRACTION_SYSTEM
        return (
            EXTRACTION_SYSTEM
            + f"\n\nThe user is named {self._user_name}. Link facts about the user "
            f"to the [[{self._user_name}]] entity (type person); never use a "
            "generic 'User' entity."
        )
```

In `_call`, change `..., [], EXTRACTION_SYSTEM` to `..., [], self._system_prompt()`.

- [ ] **Step 5: `_apply` — sensitive→provisional net**

```python
                status = route_status(op.confidence, op.stakes)
                if "sensitive" in op.tags:
                    status = "provisional"
```

(Insert right after the existing `status = route_status(...)` line; the rest of `_apply` unchanged.)

- [ ] **Step 6: `server.py` — pass `user_name`**

In the `Extractor(...)` construction, add `user_name=settings.memory_user_name` (keep the existing `recall_k=…`, `on_formed=…` args):

```python
    extractor = Extractor(_extraction_provider(settings, provider), memory,
                          recall_k=settings.memory_extract_recall_k,
                          on_formed=_broadcast_formed,
                          user_name=settings.memory_user_name)
```

- [ ] **Step 7: Run → pass + full suite** — `cd brain && uv run pytest tests/test_memory_extraction.py -q` then `cd brain && uv run pytest -q`.

- [ ] **Step 8: Commit** — `git add brain/src/alfred_brain/memory/extraction.py brain/src/alfred_brain/server.py brain/tests/test_memory_extraction.py && git commit -m "feat(brain): extraction identity + store-sensitive-as-provisional + no auto-promote"`

---

## Post-plan

- [ ] Set `[memory] user_name = "Dimitris"` in the dev `~/.alfred/config.toml` and restart the brain (operational, not committed).
