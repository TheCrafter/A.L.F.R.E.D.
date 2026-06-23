# ALFRED — Memory Subsystem Design (Foundation Slice)

- **Date:** 2026-06-23
- **Status:** Approved design (brainstormed). Awaiting implementation plan.
- **Iteration:** MARK I (second spec of the iteration; Config was the first).
- **Scope:** The foundation slice of Memory — a `Memory` facade over an
  Obsidian-compatible markdown vault with local semantic recall, wired into the
  agent loop. The crown jewel, built lean first.

---

## 1. Context & motivation

Memory is ALFRED's defining capability (architecture spec §4.5): it learns the
user's world and gets more useful over time. The full §4.5 vision (Mem0 engine,
scoped profiles, provisional/confirmed formation, reflection, review panel) is
several increments. This spec builds the **durable, swappable core** first:

- a **`Memory` facade** (the swap-point — the brain only ever talks to this),
- an **Obsidian-compatible markdown vault** as the source of truth,
- **local semantic recall** (CPU embeddings, no cloud, no GPU),
- **hybrid integration**: relevant memories auto-injected into the system prompt
  each turn, plus `remember`/`recall`/`forget` tools the LLM can call.

Result: ALFRED visibly remembers across turns and restarts, with every later
engine experiment (Mem0, a memory service) a clean drop-in behind the facade.

## 2. Goals / non-goals

**Goals**
- `Memory` facade: `remember`, `recall`, `forget`, `all`.
- Markdown vault at `$ALFRED_HOME/vault` (from the config `[memory]` section),
  **one atomic note per memory**, YAML frontmatter, `[[wikilinks]]` — a valid
  Obsidian vault (open the folder, it just works).
- **Markdown is the source of truth**; vectors are a derived, rebuildable index.
- Local semantic retrieval via **`fastembed`** (CPU/ONNX), cosine top-k.
- Auto-inject recalled memories into the per-turn system prompt + the three tools.
- Memory works **independently of the reasoning provider** (local embeddings), so
  it functions even when Groq/Gemini is throttled/offline.

**Non-goals (deferred to later Memory increments)**
- **Mem0** or any external memory engine.
- **Scoped core profiles** (`vault/profile/*.md`) and the context router.
- **Provisional/confirmed** status policy and confidence×stakes routing.
- **Reflection / auto-capture** (distilling memories from conversation). Foundation
  formation is explicit only.
- **Memory review panel** (UI) and its protocol messages — the frozen `protocol/`
  contract is untouched by this spec.
- **On-disk vector cache** — the index is in-memory, rebuilt from the vault at
  startup (see §4). Persisting vectors is a later optimization.
- **`search`** as a distinct exact/filter operation — folded into `recall` for now.
- Promotion to a standalone service — facade-isolated so this is a future,
  brain-free extraction (architecture §9 trigger).

## 3. Storage model

`$ALFRED_HOME/vault/` **is** an Obsidian vault. Layout:
```
vault/
  memories/
    prefers-terse-replies-01j9x8.md
    acme-corp-renewal-01j9xa.md
```

**One memory = one note.** Filename: `<slug>-<shortid>.md` (slug from the first
words of the text, kebab-cased; short id suffix avoids collisions). Format:
```markdown
---
id: 01j9x8z3k7
created: 2026-06-23T18:40:00Z
type: note
tags: [example]
status: active
---

<the memory text>
```
- `type`: a free string, suggested values `fact | preference | project | note`
  (not strictly validated — kept flexible for the foundation).
- `tags`: optional list (Obsidian-readable).
- `status`: `active` (the foundation only writes active; the provisional/confirmed
  lifecycle is deferred).
- Body may contain `[[wikilinks]]` to other memories (relations show in Obsidian's
  graph). The foundation does not auto-create links; the LLM may include them.

Frontmatter is read/written with `pyyaml` (YAML is what Obsidian expects). The
vault is the **single source of truth**: the index is always reconstructable from
it.

## 4. Retrieval

- **Embedder:** `fastembed` with `bge-small-en-v1.5` (default; configurable),
  CPU/ONNX, 384-dim. No GPU, no cloud key. Model (~130 MB) downloaded once on
  first use.
- **Index:** in-memory — a list of `(id, vector, record)` built at startup by
  embedding every note in the vault. Updated incrementally on `remember`
  (embed + append) and `forget` (drop). Rebuilt from the vault on each startup
  (markdown is truth). Disk-caching the vectors is a deferred optimization.
- **`recall(query, k)`:** embed the query, cosine-similarity against the index,
  return the top-k records (highest first). Empty vault → empty list.
- The embedder is **injectable** (constructor dependency) so tests use a fast
  deterministic fake and never download a model; a gated integration test
  exercises real `fastembed`.

## 5. Facade interface

```python
@dataclass
class MemoryRecord:
    id: str
    text: str
    type: str
    tags: list[str]
    status: str
    created: str          # RFC 3339
    path: Path

class Memory(Protocol):
    def remember(self, text: str, *, type: str = "note",
                 tags: list[str] | None = None) -> MemoryRecord: ...
    def recall(self, query: str, *, k: int = 5) -> list[MemoryRecord]: ...
    def forget(self, id: str) -> bool: ...      # False if id unknown
    def all(self) -> list[MemoryRecord]: ...    # for reindex / maintenance
```

The foundation implementation (`VaultMemory`) composes a vault reader/writer and
the embedding index. The brain depends only on the `Memory` protocol.

## 6. Agent-loop integration

`AgentLoop` gains a `memory: Memory` dependency (`create_app` builds the concrete
`VaultMemory` and injects it; a `set_memory` mirrors the other hot setters).

**Per-turn recall → prompt.** At the start of `run`, before the provider loop:
```python
hits = self._memory.recall(text, k=recall_top_k)
system = self._system if not hits else self._system + "\n\n# Relevant memories\n" + render(hits)
```
`render` lists each hit as `- ({type}) {text}`. The augmented system is used for
that whole turn (across tool iterations). No hits → base system unchanged.

**Tools** (registered alongside `echo`, thin wrappers over the facade):
- `remember(text, type?, tags?)` → stores a memory; returns its id/summary. Risk: `sensitive` (writes).
- `recall(query, k?)` → returns matching memories (so the LLM can look things up deliberately, beyond the auto-injection). Risk: `safe`.
- `forget(id)` → deletes a memory (ids come from prior recall output). Risk: `sensitive`.

A short line is added to the persona system prompt so the model knows it has a
durable memory and should `remember` salient, durable facts the user shares.

## 7. Formation (foundation)

**Explicit only.** Memories are created when the LLM calls `remember` — typically
because the user said "remember…", or the model judged a fact durable enough to
store during a turn. No background reflection/auto-capture (deferred). This keeps
formation predictable and within the existing tool-calling loop.

## 8. Configuration

A `[memory]` section is added to the config (`config.toml`), loaded by the config
subsystem (flattened to flat `Settings` fields, env-aliased, documented in the
bootstrap template):

| TOML | field | default | env |
|------|-------|---------|-----|
| `[memory] vault_dir` | `memory_vault_dir` | `$ALFRED_HOME/vault` | `ALFRED_VAULT_DIR` |
| `[memory] embed_model` | `memory_embed_model` | `bge-small-en-v1.5` | `ALFRED_EMBED_MODEL` |
| `[memory] recall_top_k` | `memory_recall_top_k` | `5` | `ALFRED_RECALL_TOP_K` |

`vault_dir` and `embed_model` are startup-only (relocating the vault or changing
the embedder requires a restart + re-index); `recall_top_k` is hot-reloadable
(applied to `AgentLoop` on `/config/reload`, like the other hot fields). The
config subsystem's `SECTION_MAP`, bootstrap template, `ENV_ALIASES`, and
`STARTUP_ONLY`/hot reload sets are extended for these three fields.

## 9. Code shape

A `memory/` package in the brain — one responsibility per file:
- `memory/record.py` — `MemoryRecord` dataclass + `Memory` protocol.
- `memory/vault.py` — markdown + frontmatter read/write, slug/id generation,
  list/delete notes (the source of truth).
- `memory/index.py` — `fastembed` embedder wrapper + in-memory vector store +
  cosine top-k; injectable embedder.
- `memory/facade.py` — `VaultMemory` composing vault + index (implements `Memory`).
- `memory/tools.py` — `RememberTool` / `RecallTool` / `ForgetTool` over the facade.

Wiring: `create_app` builds `VaultMemory(settings)`, registers the three tools,
and injects the facade into `AgentLoop`. `__main__` already establishes
`$ALFRED_HOME`.

## 10. Testing

Unit tests with a **temp `$ALFRED_HOME`/vault** (the existing autouse conftest
fixture) and a **fake deterministic embedder** (no model download, offline):
- vault: `remember` writes a well-formed Obsidian note (frontmatter + body);
  round-trips through read; `forget` deletes the file; slugs are filesystem-safe
  and collision-resistant.
- index/recall: with a fake embedder, `recall` returns the most-similar records
  in order; empty vault → `[]`; `forget` removes a record from results.
- facade: `remember` then `recall` finds it; `all()` lists everything; rebuild
  from vault reproduces the index.
- tools: `RememberTool` creates a memory; `RecallTool` returns hits; `ForgetTool`
  deletes; risk tiers correct.
- agent loop: a turn recalls and the recalled text appears in the system prompt
  passed to the provider (assert via a fake provider capturing `system`); no hits
  → base system unchanged.
- config: the three `[memory]` fields load, flatten, and validate; `recall_top_k`
  bounds (≥1).
- A gated (`@pytest.mark.integration`, skipped without opt-in) smoke test exercises
  real `fastembed` end-to-end.

Existing brain tests stay green.

## 11. Dependencies

- `fastembed` (CPU/ONNX embeddings; pulls `onnxruntime`, `numpy`). ~130 MB model
  downloaded on first real use (not in unit tests — embedder is faked).
- `pyyaml` (frontmatter read/write).

## 12. Deferred / future (recap)

Mem0 engine · scoped profiles + context router · provisional/confirmed + reflection
· review panel (+ protocol messages) · on-disk vector cache · distinct `search` ·
promotion to a standalone memory service.
