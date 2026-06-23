# Memory Note Titles + Hub/Entity Linking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give vault notes readable, hex-free titles and connect them into an Obsidian graph via `[[wikilinks]]` to lightweight per-entity hub notes.

**Architecture:** Fact notes live in `memories/` (recall-indexed) with a filesystem-safe title as the filename and the id in frontmatter; they link up to entity hub notes in `entities/` (navigational, not indexed). The extraction pass titles each memory and tags the entities it concerns; we find-or-create hubs and embed the links. Obsidian backlinks/graph are automatic.

**Tech Stack:** Python 3.12 (`uv`), pyyaml, pytest. Reuses the existing `Vault`/`VaultMemory`/`Extractor`.

## Global Constraints

- Python 3.12; run all commands from `brain/` via `uv run …`.
- Strict typing — full hints, no `Any` workarounds.
- `protocol/` is frozen — do not touch it. No wire changes.
- Commit messages: plain, conventional, scoped `feat(brain): …` / `test(brain): …`. **NO `Co-Authored-By: Claude` / "authored by Claude" trailer.**
- Run `uv run pytest -q` from `brain/` after each task; all green before the task is complete.
- Tests reuse `tests/conftest.py` ($ALFRED_HOME isolation) and `tests/test_memory_index.py::FakeEmbedder`.
- Filenames must be Windows-safe: strip `\ / : * ? " < > |`. Hubs are case-insensitively deduped. `update()` never renames a note (link stability).
- The vault has been cleared; no legacy migration is required.

---

### Task 1: Titles, safe filenames, and `Related:` links in the vault

**Files:**
- Modify: `brain/src/alfred_brain/memory/record.py`
- Modify: `brain/src/alfred_brain/memory/vault.py`
- Modify: `brain/src/alfred_brain/memory/facade.py`
- Test: `brain/tests/test_memory_vault.py`, `brain/tests/test_memory_facade.py`

**Interfaces:**
- Produces: `MemoryRecord` gains `title: str = ""`, `links: list[str] = []`. `Vault.write(..., title="", links=None)`, `Vault.update(..., title=None, links=None)`, title-based safe filenames with collision suffixing, `read()` parsing title + `Related:` links. `VaultMemory.remember(..., title="", links=None)` / `update(..., title=None, links=None)`. `Memory` protocol `remember`/`update` gain `title`/`links`.
- Consumes: existing `_FRONTMATTER`, `_new_id`, `_now`, `_render`/`update` from the formation increment.

- [ ] **Step 1: Write failing tests**

In `brain/tests/test_memory_vault.py` add:

```python
def test_filename_is_safe_title_not_full_text(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("Dimitris is 32 and lives in Greece.",
                  title="Dimitris - age and location")
    assert rec.path.name == "Dimitris - age and location.md"
    assert rec.title == "Dimitris - age and location"


def test_illegal_filename_chars_stripped(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("x", title='a/b:c*d?e"f<g>h|i')
    assert not any(c in rec.path.name for c in '\\/:*?"<>|')


def test_filename_collision_gets_numeric_suffix(tmp_path):
    v = Vault(tmp_path / "vault")
    a = v.write("first", title="Same Title")
    b = v.write("second", title="Same Title")
    assert a.path.name == "Same Title.md"
    assert b.path.name == "Same Title 2.md"
    assert a.id != b.id


def test_empty_title_derives_from_text(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("alpha beta gamma delta epsilon zeta eta theta iota")
    assert rec.title == "alpha beta gamma delta epsilon zeta eta theta"


def test_links_render_and_round_trip(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("Dimitris is 32.", title="Dimitris age",
                  links=["Dimitris", "Greece"])
    raw = rec.path.read_text(encoding="utf-8")
    assert "Related: [[Dimitris]], [[Greece]]" in raw
    again = v.read(rec.path)
    assert again.text == "Dimitris is 32."   # Related line excluded from text
    assert again.links == ["Dimitris", "Greece"]
    assert again.title == "Dimitris age"


def test_no_links_no_related_line(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("plain fact", title="Plain")
    raw = rec.path.read_text(encoding="utf-8")
    assert "Related:" not in raw
    assert v.read(rec.path).links == []


def test_update_keeps_filename_stable(tmp_path):
    v = Vault(tmp_path / "vault")
    rec = v.write("old", title="Original Title")
    out = v.update(rec.id, text="new", title="Totally Different", links=["Greece"])
    assert out is not None
    assert out.path.name == "Original Title.md"   # NOT renamed
    assert out.title == "Totally Different"
    assert out.links == ["Greece"]
```

In `brain/tests/test_memory_facade.py` add:

```python
def test_remember_with_title_and_links(tmp_path):
    from alfred_brain.memory import VaultMemory
    from tests.test_memory_index import FakeEmbedder
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    rec = mem.remember("Dimitris is 32.", title="Dimitris age",
                       links=["Dimitris"])
    assert rec.title == "Dimitris age" and rec.links == ["Dimitris"]
    assert rec.path.name == "Dimitris age.md"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_memory_vault.py tests/test_memory_facade.py -q`
Expected: FAIL (`write()` got unexpected keyword `title`; no collision/`Related` handling).

- [ ] **Step 3: Update `record.py`**

Add the two fields and extend the protocol's `remember`/`update`:

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
    title: str = ""
    links: list[str] = field(default_factory=list)
```

(Add `from dataclasses import dataclass, field` if `field` isn't already imported.)

```python
    def remember(self, text: str, *, type: str = "note",
                 tags: list[str] | None = None, status: str = "confirmed",
                 title: str = "", links: list[str] | None = None) -> MemoryRecord: ...
    def update(self, id: str, *, text: str | None = None, type: str | None = None,
               tags: list[str] | None = None, status: str | None = None,
               title: str | None = None,
               links: list[str] | None = None) -> MemoryRecord | None: ...
```

- [ ] **Step 4: Update `vault.py`**

Add module-level helpers (near `_slugify`):

```python
_ILLEGAL = re.compile(r'[\\/:*?"<>|]')
_RELATED = re.compile(r"\n+Related:\s*(.+)$", re.DOTALL)


def _safe_filename(title: str) -> str:
    name = _ILLEGAL.sub("", title)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80].strip() or "memory"


def _derive_title(text: str) -> str:
    return " ".join(text.split()[:8])[:60].strip() or "memory"


def _split_body(body: str) -> tuple[str, list[str]]:
    m = _RELATED.search(body)
    if not m:
        return body, []
    text = body[: m.start()].strip()
    links = re.findall(r"\[\[(.+?)\]\]", m.group(1))
    return text, links
```

Replace `write`, `_render`, `read`, `update` with title/links-aware versions:

```python
    def write(self, text: str, *, type: str = "note",
              tags: list[str] | None = None, status: str = "confirmed",
              title: str = "", links: list[str] | None = None) -> MemoryRecord:
        self._dir.mkdir(parents=True, exist_ok=True)
        rec = MemoryRecord(
            id=_new_id(), text=text, type=type, tags=list(tags or []),
            status=status, created=_now(), path=Path(),
            title=(title.strip() or _derive_title(text)), links=list(links or []),
        )
        rec.path = self._unique_path(rec.title)
        rec.path.write_text(self._render(rec), encoding="utf-8")
        return rec

    def _unique_path(self, title: str) -> Path:
        base = _safe_filename(title)
        path = self._dir / f"{base}.md"
        n = 2
        while path.exists():
            path = self._dir / f"{base} {n}.md"
            n += 1
        return path

    def _render(self, rec: MemoryRecord) -> str:
        meta = {"id": rec.id, "created": rec.created, "type": rec.type,
                "tags": rec.tags, "status": rec.status, "title": rec.title}
        if rec.updated:
            meta["updated"] = rec.updated
        front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
        body = rec.text
        if rec.links:
            body += "\n\nRelated: " + ", ".join(f"[[{l}]]" for l in rec.links)
        return f"---\n{front}---\n\n{body}\n"

    def read(self, path: Path) -> MemoryRecord:
        raw = Path(path).read_text(encoding="utf-8")
        m = _FRONTMATTER.match(raw)
        if not m:
            raise ValueError(f"not a memory note (no frontmatter): {path}")
        meta = yaml.safe_load(m.group(1)) or {}
        text, links = _split_body(m.group(2).strip())
        return MemoryRecord(
            id=str(meta.get("id", "")), text=text,
            type=str(meta.get("type", "note")), tags=list(meta.get("tags") or []),
            status=str(meta.get("status", "active")),
            created=str(meta.get("created", "")), path=Path(path),
            updated=(str(meta["updated"]) if meta.get("updated") else None),
            title=str(meta.get("title", "")), links=links,
        )

    def update(self, id: str, *, text: str | None = None, type: str | None = None,
               tags: list[str] | None = None, status: str | None = None,
               title: str | None = None,
               links: list[str] | None = None) -> MemoryRecord | None:
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
            if title is not None:
                rec.title = title
            if links is not None:
                rec.links = list(links)
            rec.updated = _now()
            rec.path.write_text(self._render(rec), encoding="utf-8")  # same path
            return rec
        return None
```

- [ ] **Step 5: Update `facade.py`**

```python
    def remember(self, text: str, *, type: str = "note",
                 tags: list[str] | None = None, status: str = "confirmed",
                 title: str = "", links: list[str] | None = None) -> MemoryRecord:
        rec = self._vault.write(text, type=type, tags=tags, status=status,
                                title=title, links=links)
        self._records[rec.id] = rec
        self._index.add(rec.id, rec.text)
        return rec

    def update(self, id: str, *, text: str | None = None, type: str | None = None,
               tags: list[str] | None = None, status: str | None = None,
               title: str | None = None,
               links: list[str] | None = None) -> MemoryRecord | None:
        rec = self._vault.update(id, text=text, type=type, tags=tags,
                                 status=status, title=title, links=links)
        if rec is None:
            return None
        self._records[rec.id] = rec
        if text is not None:
            self._index.remove(rec.id)
            self._index.add(rec.id, rec.text)
        return rec
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_memory_vault.py tests/test_memory_facade.py tests/test_memory_tools.py tests/test_memory_record.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add brain/src/alfred_brain/memory/record.py brain/src/alfred_brain/memory/vault.py brain/src/alfred_brain/memory/facade.py brain/tests/test_memory_vault.py brain/tests/test_memory_facade.py
git commit -m "feat(brain): readable note titles + Related links in the vault"
```

---

### Task 2: Entity hub notes

**Files:**
- Modify: `brain/src/alfred_brain/memory/record.py` (protocol)
- Modify: `brain/src/alfred_brain/memory/vault.py`
- Modify: `brain/src/alfred_brain/memory/facade.py`
- Test: `brain/tests/test_memory_vault.py`, `brain/tests/test_memory_facade.py`

**Interfaces:**
- Produces: `Vault.ensure_entity(name, type="topic") -> str`, `Vault.list_entities() -> list[tuple[str, str]]`; same on `VaultMemory`; `Memory` protocol gains both. Hubs written to `entities/`, excluded from `all()`/recall.
- Consumes: Task 1's `_safe_filename`, `_FRONTMATTER`, `_now`.

- [ ] **Step 1: Write failing tests**

In `brain/tests/test_memory_vault.py` add:

```python
def test_ensure_entity_creates_hub(tmp_path):
    v = Vault(tmp_path / "vault")
    stem = v.ensure_entity("Dimitris", "person")
    assert stem == "Dimitris"
    hub = (tmp_path / "vault" / "entities" / "Dimitris.md")
    assert hub.exists()
    raw = hub.read_text(encoding="utf-8")
    assert "type: person" in raw and "# Dimitris" in raw


def test_ensure_entity_is_case_insensitive_dedup(tmp_path):
    v = Vault(tmp_path / "vault")
    a = v.ensure_entity("Dimitris", "person")
    b = v.ensure_entity("dimitris", "person")
    assert a == b == "Dimitris"   # reuses first-seen spelling
    hubs = list((tmp_path / "vault" / "entities").glob("*.md"))
    assert len(hubs) == 1


def test_entities_excluded_from_facts(tmp_path):
    v = Vault(tmp_path / "vault")
    v.write("a fact", title="Fact A")
    v.ensure_entity("Dimitris", "person")
    assert [r.title for r in v.all()] == ["Fact A"]   # hub not in all()


def test_list_entities(tmp_path):
    v = Vault(tmp_path / "vault")
    v.ensure_entity("Dimitris", "person")
    v.ensure_entity("Greece", "place")
    assert sorted(v.list_entities()) == [("Dimitris", "person"), ("Greece", "place")]
```

In `brain/tests/test_memory_facade.py` add:

```python
def test_facade_ensure_and_list_entities(tmp_path):
    from alfred_brain.memory import VaultMemory
    from tests.test_memory_index import FakeEmbedder
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    assert mem.ensure_entity("Alfred", "project") == "Alfred"
    assert mem.list_entities() == [("Alfred", "project")]
    # hubs are not facts -> not recalled / not in all()
    assert mem.all() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_memory_vault.py tests/test_memory_facade.py -q`
Expected: FAIL (`Vault` has no attribute `ensure_entity`).

- [ ] **Step 3: Update `record.py` protocol**

Add to the `Memory` protocol:

```python
    def ensure_entity(self, name: str, type: str = "topic") -> str: ...
    def list_entities(self) -> list[tuple[str, str]]: ...
```

- [ ] **Step 4: Update `vault.py`**

In `__init__`, add the entities dir:

```python
    def __init__(self, vault_dir: Path) -> None:
        self._dir = Path(vault_dir) / "memories"
        self._entities = Path(vault_dir) / "entities"
```

Add the two methods:

```python
    def ensure_entity(self, name: str, type: str = "topic") -> str:
        name = name.strip()
        stem = _safe_filename(name)
        self._entities.mkdir(parents=True, exist_ok=True)
        key = stem.casefold()
        for p in self._entities.glob("*.md"):
            if p.stem.casefold() == key:
                return p.stem
        front = yaml.safe_dump({"type": type, "created": _now()},
                               sort_keys=False, allow_unicode=True)
        (self._entities / f"{stem}.md").write_text(
            f"---\n{front}---\n\n# {name}\n", encoding="utf-8")
        return stem

    def list_entities(self) -> list[tuple[str, str]]:
        if not self._entities.is_dir():
            return []
        out: list[tuple[str, str]] = []
        for p in sorted(self._entities.glob("*.md")):
            m = _FRONTMATTER.match(p.read_text(encoding="utf-8"))
            meta = (yaml.safe_load(m.group(1)) if m else {}) or {}
            out.append((p.stem, str(meta.get("type", "topic"))))
        return out
```

- [ ] **Step 5: Update `facade.py`**

```python
    def ensure_entity(self, name: str, type: str = "topic") -> str:
        return self._vault.ensure_entity(name, type)

    def list_entities(self) -> list[tuple[str, str]]:
        return self._vault.list_entities()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_memory_vault.py tests/test_memory_facade.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add brain/src/alfred_brain/memory/record.py brain/src/alfred_brain/memory/vault.py brain/src/alfred_brain/memory/facade.py brain/tests/test_memory_vault.py brain/tests/test_memory_facade.py
git commit -m "feat(brain): entity hub notes (ensure_entity + list_entities)"
```

---

### Task 3: Extraction emits titles + entities and links them

**Files:**
- Modify: `brain/src/alfred_brain/memory/extraction.py`
- Test: `brain/tests/test_memory_extraction.py`

**Interfaces:**
- Produces: `EntityRef(name, type="topic")`; `ExtractOp` gains `title: str = ""`, `entities: list[EntityRef] = []`; `_parse_ops` parses both; `_apply` ensures hubs and writes title + `[[links]]`; the extractor passes known entities into the prompt.
- Consumes: Task 1 (`remember`/`update` title/links) + Task 2 (`ensure_entity`, `list_entities`).

- [ ] **Step 1: Write failing tests**

In `brain/tests/test_memory_extraction.py` add (the file already defines `_FakeProvider`, `VaultMemory`, `FakeEmbedder`, `_batch`):

```python
from alfred_brain.memory.extraction import EntityRef


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
```

(Ensure `TextChunk` is imported in the test module — it already is.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_memory_extraction.py -q`
Expected: FAIL (`cannot import name 'EntityRef'`; `ExtractOp` has no `title`).

- [ ] **Step 3: Update `extraction.py`**

Add `EntityRef`, the allowed types, and extend `ExtractOp`:

```python
_ENTITY_TYPES = {"person", "place", "org", "project", "topic"}


@dataclass
class EntityRef:
    name: str
    type: str = "topic"


@dataclass
class ExtractOp:
    action: Literal["add", "update"]
    text: str
    id: str | None = None
    type: str = "note"
    tags: list[str] = field(default_factory=list)
    confidence: Literal["high", "low"] = "low"
    stakes: Literal["low", "high"] = "low"
    title: str = ""
    entities: list[EntityRef] = field(default_factory=list)
```

In `_parse_ops`, build entities and read title inside the per-op loop, before constructing the `ExtractOp`:

```python
        entities: list[EntityRef] = []
        for e in (o.get("entities") or []):
            if not isinstance(e, dict):
                continue
            ename = str(e.get("name", "")).strip()
            if not ename:
                continue
            etype = str(e.get("type", "topic"))
            entities.append(EntityRef(ename, etype if etype in _ENTITY_TYPES else "topic"))
        ops.append(ExtractOp(
            action=action, text=body,
            id=(str(o["id"]) if o.get("id") else None),
            type=str(o.get("type", "note")),
            tags=[str(t) for t in (o.get("tags") or [])],
            confidence="high" if o.get("confidence") == "high" else "low",
            stakes="high" if o.get("stakes") == "high" else "low",
            title=str(o.get("title", "")).strip(),
            entities=entities,
        ))
```

Replace `EXTRACTION_SYSTEM` with a version that requests titles + entities (keep the durable-fact / dedup guidance; add the two new requirements and the new JSON shape):

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
    "- If the transcript confirms a tentative existing memory, \"update\" it with "
    "confidence \"high\".\n\n"
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

Update `_call` to accept and surface known entities, and `extract` to fetch them:

```python
    async def _call(self, transcript: str, existing: list[MemoryRecord],
                    known: list[tuple[str, str]]) -> str:
        existing_block = "\n".join(
            f"- [{r.id}] ({r.type}, {r.status}) {r.text}" for r in existing
        ) or "(none)"
        known_block = ", ".join(f"{n} ({t})" for n, t in known) or "(none)"
        user = (f"KNOWN entities: {known_block}\n\n"
                f"EXISTING memories:\n{existing_block}\n\n"
                f"TRANSCRIPT:\n{transcript}")
        chunks: list[str] = []
        async for ev in self._provider.run_turn(
            [TurnMessage(role="user", content=user)], [], EXTRACTION_SYSTEM
        ):
            if isinstance(ev, TextChunk):
                chunks.append(ev.text)
        return "".join(chunks)
```

In `extract`, fetch `known` and thread it through both `_call` invocations:

```python
            try:
                existing = self._memory.recall(transcript, k=self._recall_k)
                known = self._memory.list_entities()
                raw = await self._call(transcript, existing, known)
                try:
                    ops = _parse_ops(raw)
                except ValueError:
                    raw = await self._call(transcript, existing, known)  # one retry
                    ops = _parse_ops(raw)
```

Update `_apply` to resolve entities into hub links and pass title/links through:

```python
    def _apply(self, ops: list[ExtractOp]) -> list[MemoryRecord]:
        applied: list[MemoryRecord] = []
        for op in ops:
            try:
                status = route_status(op.confidence, op.stakes)
                links = [self._memory.ensure_entity(e.name, e.type)
                         for e in op.entities if e.name.strip()]
                if op.action == "add":
                    applied.append(self._memory.remember(
                        op.text, type=op.type, tags=op.tags, status=status,
                        title=op.title, links=links))
                elif op.action == "update" and op.id:
                    rec = self._memory.update(
                        op.id, text=op.text, type=op.type, tags=op.tags,
                        status=status, title=(op.title or None),
                        links=(links or None))
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
git commit -m "feat(brain): extraction titles memories + links them to entity hubs"
```

---

### Task 4: Explicit `remember` tool gains title + entities

**Files:**
- Modify: `brain/src/alfred_brain/memory/tools.py`
- Test: `brain/tests/test_memory_tools.py`

**Interfaces:**
- Produces: `RememberTool` accepts optional `title` (string) and `entities` (array of `{name, type}`); creates hubs and writes title + links; `status="confirmed"`.
- Consumes: Tasks 1 + 2.

- [ ] **Step 1: Write failing tests**

In `brain/tests/test_memory_tools.py` add (match the file's existing fixtures/style):

```python
async def test_remember_tool_with_title_and_entities(tmp_path):
    from alfred_brain.memory import VaultMemory
    from tests.test_memory_index import FakeEmbedder
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    tool = RememberTool(mem)
    await tool.run({"text": "Dimitris created Alfred.", "title": "Dimitris created Alfred",
                    "entities": [{"name": "Dimitris", "type": "person"},
                                 {"name": "Alfred", "type": "project"}]})
    rec = mem.all()[0]
    assert rec.title == "Dimitris created Alfred"
    assert rec.links == ["Dimitris", "Alfred"]
    assert sorted(mem.list_entities()) == [("Alfred", "project"), ("Dimitris", "person")]


async def test_remember_tool_without_title_derives_one(tmp_path):
    from alfred_brain.memory import VaultMemory
    from tests.test_memory_index import FakeEmbedder
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    await RememberTool(mem).run({"text": "one two three four five six seven eight nine"})
    rec = mem.all()[0]
    assert rec.title == "one two three four five six seven eight"
    assert rec.links == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_memory_tools.py -q`
Expected: FAIL (`title`/`entities` ignored; `rec.title` empty / `links` missing).

- [ ] **Step 3: Update `tools.py`**

Extend `RememberTool.parameters`:

```python
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The memory to store."},
            "type": {"type": "string",
                     "description": "fact | preference | project | note",
                     "default": "note"},
            "tags": {"type": "array", "items": {"type": "string"},
                     "description": "Optional tags."},
            "title": {"type": "string",
                      "description": "Short note title (<= 6 words). Optional."},
            "entities": {"type": "array", "items": {
                "type": "object",
                "properties": {"name": {"type": "string"},
                               "type": {"type": "string"}}},
                "description": "People/places/projects/topics this concerns. Optional."},
        },
        "required": ["text"],
    }
```

Update `run`:

```python
    async def run(self, args: dict) -> str:
        text = str(args.get("text", "")).strip()
        if not text:
            return "Error: text is required."
        links: list[str] = []
        for e in (args.get("entities") or []):
            if isinstance(e, dict):
                name = str(e.get("name", "")).strip()
                if name:
                    links.append(self._memory.ensure_entity(
                        name, str(e.get("type", "topic"))))
        rec = self._memory.remember(
            text,
            type=str(args.get("type", "note")),
            tags=list(args.get("tags") or []),
            status="confirmed",
            title=str(args.get("title", "")).strip(),
            links=links,
        )
        return f"Remembered ({rec.type}) as {rec.id}."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_memory_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `cd brain && uv run pytest -q`
Expected: all pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add brain/src/alfred_brain/memory/tools.py brain/tests/test_memory_tools.py
git commit -m "feat(brain): remember tool accepts title + entity links"
```

---

## Post-plan: docs

- [ ] Note in `AGENTS.md` (Phase 2 line) that vault notes now have readable titles + entity-hub linking. Commit `docs: note titled notes + entity hubs`.
