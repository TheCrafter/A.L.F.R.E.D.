# Memory Formation (Short-Term + Extraction) — Design

Status: approved (brainstorm) · 2026-06-23
Builds on: `2026-06-23-memory-subsystem-design.md` (the durable foundation) and
architecture §4.5 (formation, provisional/confirmed, reflection).

## 1. Problem

The memory foundation captures facts **explicitly only** — a memory is written
only when the chat model decides to call the `remember` tool mid-turn. That is
unreliable: the user said *"Hey Alfred. My name is Dimitris, I created you."* and
nothing was stored, because the (small, fast) chat model simply didn't call the
tool. Capture must not depend on the chat model's moment-to-moment whim.

Separately, ALFRED has **no short-term memory at all**. The agent loop starts each
turn from scratch:

```python
messages: list[TurnMessage] = [TurnMessage(role="user", content=text)]
```

So it cannot remember what was said two messages ago.

## 2. Solution overview

Two layers, mirroring human short-term / long-term memory:

- **Working memory (short-term):** an in-RAM rolling buffer of recent
  user/assistant messages, held in the brain and fed into every turn. Makes
  ALFRED conversational.
- **Formation (long-term):** when messages age out of the window, a dedicated
  **extraction pass** — a separate, single-purpose LLM call — reads them, dedupes
  against existing memories, and writes durable atomic notes to the vault. This
  decouples *capturing* from *conversing*.

The window both **provides short-term context** and **defines the extraction
batch**: messages leaving the window are exactly what extraction reads, so nothing
is lost — a message is either promoted to a durable memory or it was ephemeral.

Trigger shape is analogous to `/compact` (threshold on recent messages → separate
LLM pass), but the product differs: `/compact` keeps a running *summary* to
continue a session; formation writes permanent *facts* to the vault and **drops**
the raw messages.

## 3. Scope

**In scope**
- Working-memory buffer (in-RAM, brain-global, single ongoing conversation).
- Async extraction pass on window overflow + flush on graceful shutdown.
- Dedup / update against existing memories (ADD / UPDATE; no autonomous delete).
- Provisional/confirmed trust policy via confidence×stakes routing.
- Trust-labeled recall injection; remove the unreliable "proactively call
  remember" prompt nag.
- Config keys + bootstrap template + TOML section map.

**Non-goals (still deferred, per §4.5)**
- Mem0 or any external memory engine.
- Scoped core profiles + context router.
- The Memory **review panel** UI and its `protocol/` messages (the frozen contract
  is untouched by this spec). The `status` data is written now so the panel has
  something to show later.
- The daily "urgent ping" notification.
- On-disk vector cache; running embeddings in a thread pool.
- A rolling natural-language summary of dropped messages (we drop, not summarize).

## 4. Components & interfaces

### 4.1 Working memory — `brain/src/alfred_brain/memory/working.py`

In-RAM buffer of conversational messages. Stores only `user` / `assistant` text
messages (intra-turn tool plumbing stays local to the agent loop and is never
buffered).

```python
class WorkingMemory:
    def __init__(self, window: int = 20) -> None: ...

    def append(self, role: Literal["user", "assistant"], text: str) -> None:
        """Append a message; messages aging out of `window` move to pending."""

    def context(self) -> list[TurnMessage]:
        """The recent window (≤ `window` messages) to feed the model."""

    def take_batch(self) -> list[TurnMessage]:
        """If pending ≥ batch_size, return & clear the pending batch; else []."""

    def drain(self) -> list[TurnMessage]:
        """Return & clear ALL un-extracted messages (pending + window). For flush."""

    def set_window(self, n: int) -> None:  # hot-reload
        ...
```

- Internally: `_recent` (deque, max `window`) + `_pending` (list). When `append`
  overflows `_recent`, the evicted message is pushed to `_pending`.
- `batch_size = max(1, window // 2)` (derived, internal — not a config knob).
- `take_batch()` returns `[]` until `_pending` reaches `batch_size`, then returns
  and clears it. This amortizes extraction (one call per ~`batch_size` aged-out
  messages) instead of one call per turn.

### 4.2 Extraction — `brain/src/alfred_brain/memory/extraction.py`

```python
@dataclass
class ExtractOp:
    action: Literal["add", "update"]
    text: str
    id: str | None = None                       # required for "update"
    type: str = "note"
    tags: list[str] = field(default_factory=list)
    confidence: Literal["high", "low"] = "low"
    stakes: Literal["low", "high"] = "low"

def route_status(confidence: str, stakes: str) -> Literal["provisional", "confirmed"]:
    return "confirmed" if confidence == "high" and stakes == "low" else "provisional"

class Extractor:
    def __init__(self, provider: ReasoningProvider, memory: Memory,
                 *, recall_k: int = 5) -> None: ...

    def set_provider(self, provider: ReasoningProvider) -> None: ...

    async def extract(self, batch: list[TurnMessage]) -> list[MemoryRecord]:
        """Run one extraction pass over a batch; apply ops; return applied records.
        Never raises — logs and returns [] on any failure."""
```

Algorithm:
1. Render the batch as a transcript string. If empty → return `[]`.
2. `existing = memory.recall(transcript, k=recall_k)` — candidates for dedup.
3. Build the extraction prompt (system + one user message) embedding the
   transcript and the existing memories (with their ids/types/status).
4. `provider.run_turn(messages, tools=[], system=EXTRACTION_SYSTEM)`; collect the
   final text. **No tools** — output is JSON in the message body (avoids the
   `tool_use_failed` flakiness; provider-agnostic).
5. Parse JSON tolerantly: strip ``` fences, extract the first balanced `{...}`,
   `json.loads`. On parse failure, retry the call **once**; then give up → `[]`.
6. Apply each op:
   - `add` → `memory.remember(text, type=..., tags=..., status=route_status(...))`
   - `update <id>` → `memory.update(id, text=..., type=..., tags=..., status=...)`
     (silently skipped if the id no longer exists).
   - Confirmation: when the batch re-affirms an existing `provisional` memory, the
     model emits `update <id>` with the corrected text and `status` flips to
     `confirmed` via routing (the prompt instructs this explicitly).
7. Serialize passes with an `asyncio.Lock` so concurrent batches don't race the
   facade's non-async writes/index mutation.

`EXTRACTION_SYSTEM` instructs the model to: extract only **durable** facts (user
identity, lasting preferences, ongoing projects, important people, how the user
wants ALFRED to behave); ignore ephemeral chatter; output a JSON object
`{"operations": [ ... ]}`; reuse an existing id via `update` instead of adding a
duplicate; assign `confidence`/`stakes` honestly; emit an empty list when there is
nothing durable.

### 4.3 Facade extensions — `memory/facade.py`, `memory/record.py`, `memory/vault.py`

- `MemoryRecord`: add `updated: str | None = None` (RFC 3339, set on update).
- `Memory` protocol: extend `remember` with `status: str = "confirmed"`; add
  `update(id, *, text=None, type=None, tags=None, status=None) -> MemoryRecord | None`.
- `VaultMemory.remember(...)`: pass `status` through to the vault; default
  `"confirmed"` (explicit remembers are confirmed).
- `VaultMemory.update(...)`: rewrite the note **in place** at its existing path
  (filename/slug unchanged to preserve the id), updating frontmatter
  (`status`, `type`, `tags`, `updated`) and body (`text`); refresh `_records` and
  re-embed in the index if `text` changed. Returns `None` if id unknown.
- `Vault`: `write(..., status="confirmed")`; new `update(id, ...)` that rewrites the
  note file and returns the refreshed `MemoryRecord`.

### 4.4 Agent loop — `brain/src/alfred_brain/agent.py`

- Hold a `WorkingMemory` and an `Extractor` (injected; optional, like `memory`).
- Build the turn prompt as `working.context() + [user message]` instead of just
  the user message.
- After the turn completes successfully: `working.append("user", text)` and
  `working.append("assistant", <final assistant text>)`; then
  `batch = working.take_batch()`; if non-empty, `asyncio.create_task(extractor.extract(batch))`
  (fire-and-forget; extractor swallows its own errors).
- **Recall injection becomes trust-labeled.** Replace `MEMORY_GUIDANCE` (the
  unreliable "proactively call `remember`" nag) with concise guidance that:
  - confirmed memories are rendered `- ({type}) {text}`;
  - provisional memories are rendered `- ({type}, unconfirmed) {text}`;
  - includes the line: *"Treat 'unconfirmed' memories cautiously; verify a
    high-stakes one with the user before relying on it."*
  A memory is labeled unconfirmed only if `status == "provisional"`; any other
  value (including the foundation's legacy `"active"`) is treated as confirmed.
- The explicit `remember`/`recall`/`forget` tools stay. `RememberTool` writes with
  `status="confirmed"`.

### 4.5 Server wiring — `brain/src/alfred_brain/server.py`

- Construct `WorkingMemory(window=settings.memory_window_messages)` and
  `Extractor(provider, memory, recall_k=settings.memory_extract_recall_k)`; inject
  both into the `AgentLoop`.
- **Extraction provider:** if `settings.memory_extract_model` is empty, the
  extractor reuses the active chat provider — when the model picker switches the
  chat provider, call `extractor.set_provider(...)` alongside `agent.set_provider(...)`.
  If `memory_extract_model` is set, build a dedicated provider for it at startup
  (and on reload) and do **not** sync it to the picker.
- **Shutdown flush:** on app shutdown, `await extractor.extract(working.drain())`
  so the un-extracted tail is captured.
- Hot-reload (`POST /config/reload`) applies `window_messages` (via
  `working.set_window`) and `extract_recall_k`. `extract_model` change rebuilds the
  extraction provider.

## 5. Data flow (per turn)

1. User message arrives.
2. `messages = working.context() + [user]`; build `system` with trust-labeled
   recalled memories.
3. Provider answers (chat + explicit tools available).
4. Reply streamed to the UI.
5. `working.append("user", text)`, `working.append("assistant", reply)`.
6. `batch = working.take_batch()` → if non-empty, schedule `extractor.extract(batch)`
   asynchronously (never blocks the next turn).
7. Extraction recalls existing memories, calls the extraction model, parses ops,
   applies ADD/UPDATE with routed status.
8. On graceful shutdown: `extractor.extract(working.drain())`.

## 6. Trust policy

| | low stakes | high stakes |
|---|---|---|
| **high confidence** | `confirmed` | `provisional` |
| **low confidence** | `provisional` | `provisional` |

- Explicit "remember that…" → always `confirmed`.
- Provisional memories are still recalled and used, but labeled `unconfirmed` in
  context so ALFRED holds them loosely and verifies high-stakes ones before relying
  on them.
- Confirmation path (now): re-extraction / user re-affirmation → `UPDATE` to
  `confirmed`. Review-panel confirmation is deferred; the `status` data is written
  now regardless.

## 7. Configuration

New `[memory]` keys (`~/.alfred/config.toml`), with env + flat-TOML support:

| TOML | Settings field | Env | Default | Reload |
|------|----------------|-----|---------|--------|
| `window_messages` | `memory_window_messages` | `ALFRED_WINDOW_MESSAGES` | `20` | hot |
| `extract_model` | `memory_extract_model` | `ALFRED_EXTRACT_MODEL` | `""` (use active) | restart provider |
| `extract_recall_k` | `memory_extract_recall_k` | `ALFRED_EXTRACT_RECALL_K` | `5` | hot |

- `memory_window_messages: int = Field(20, ge=2)`.
- `memory_extract_model: str = ""` (empty → reuse the active provider/model).
- `memory_extract_recall_k: int = Field(5, ge=1)`.
- Add the three to `ENV_ALIASES`, `SECTION_MAP` (`memory` section), and the
  bootstrap template `[memory]` block with value comments.

## 8. Testing

- **working.py:** window eviction; only user/assistant counted; `take_batch`
  returns `[]` until `batch_size`, then the batch; `drain` returns pending+window
  and clears; `set_window`.
- **extraction.py:** `route_status` truth table; tolerant JSON parse (fenced,
  surrounding prose, trailing junk); one-retry-then-empty on bad JSON; applies
  ADD (with routed status) and UPDATE; skips UPDATE of unknown id; empty batch →
  `[]`; provider error → `[]` (no raise). Use a fake provider yielding canned text
  and a real `VaultMemory` over a temp dir (or a fake Memory).
- **facade/vault:** `update` rewrites in place, preserves id, refreshes index when
  text changes, `updated` set; `remember(status=...)` persists status; unknown id →
  `None`.
- **agent.py:** prompt includes `working.context()`; overflow schedules extraction
  (inject a spy extractor); provisional memories rendered `unconfirmed`, confirmed
  rendered plainly; the proactive-nag text is gone.
- **config:** new keys load from TOML and env with correct precedence.
- **server:** extractor provider synced on model switch; shutdown flush calls
  `extract(drain())`; `extract_model` override builds a dedicated provider.

## 9. Files

- Create: `memory/working.py`, `memory/extraction.py` (+ tests).
- Modify: `memory/record.py` (`updated`, protocol), `memory/vault.py` (`status`,
  `update`), `memory/facade.py` (`status`, `update`), `memory/tools.py`
  (`RememberTool` → `status="confirmed"`), `agent.py` (working memory, extraction
  scheduling, trust-labeled recall, drop the nag), `server.py` (wiring + flush +
  reload), `config/settings.py`, `config/toml_source.py`, `config/bootstrap.py`.
- Untouched: `protocol/` (frozen).
