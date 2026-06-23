# Memory Review Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Desktop-UI panel to review memories — see all, confirm provisional ones, re-tag, delete — updating live as extraction writes facts, over new WebSocket protocol messages.

**Architecture:** First `protocol/` contract change since Phase 0 (7 additive v1 messages + a `MemoryItem` object). The brain answers list/edit/delete and broadcasts `memory.formed`/`memory.removed` through the existing `EventBus`; the desktop UI gains a store slice + a `MemoryPanel`. Contract-first throughout — both sides import generated types.

**Tech Stack:** JSON Schema → datamodel-codegen (Pydantic) + json2ts (TS); Python 3.12/`uv` (brain); Node/`pnpm` + vitest (desktop-ui).

## Global Constraints

- **Contract-first:** never hand-edit `protocol/gen/`. The schema is the source of truth; regenerate with `cd protocol && uv run python scripts/codegen.py`. The schema edit + regenerated `gen/` + fixtures are **one atomic commit** (Task 1).
- **Wire invariants:** every message carries the envelope `{v:1, id, ts}`; optional fields are **omitted when absent, never null** (Python: `model_dump(mode="json", exclude_none=True)` via the brain's `dump()`; TS: `field?: T`). `type` is the discriminator.
- **Toolchains:** Tasks 1–3 run from `brain/` or `protocol/` with `uv run …`. Task 1 also runs the protocol TS checks. Tasks 4–5 run from `desktop-ui/` with `pnpm exec vitest run` and `pnpm exec tsc --noEmit`.
- Strict typing both languages; no `any`. Commit messages plain, conventional, scoped (`feat(protocol|brain|desktop-ui): …`); **NO `Co-Authored-By: Claude` / "authored by Claude" trailer.**
- Status values on the wire are exactly `provisional` | `confirmed`.

---

### Task 1: Protocol contract change (schema + codegen + fixtures)

**Files:**
- Modify: `protocol/schema/protocol.schema.json`
- Regenerate (do not hand-edit): `protocol/gen/python/alfred_protocol/models.py`, `protocol/gen/typescript/index.ts`
- Create: `protocol/fixtures/memory_list_request.json`, `…/memory_list_response.json`, `…/memory_edit.json`, `…/memory_delete.json`, `…/memory_ack.json`, `…/memory_formed.json`, `…/memory_removed.json`

**Interfaces:**
- Produces (generated, importable): Python `MemoryItem, MemoryListRequest, MemoryListResponse, MemoryEdit, MemoryDelete, MemoryAck, MemoryFormed, MemoryRemoved` from `alfred_protocol`; matching TS interfaces from `@alfred/protocol`, all in the `Message` union.

- [ ] **Step 1: Add `MemoryItem` to `$defs`**

In `protocol/schema/protocol.schema.json`, add to `$defs` (alongside `Channel`/`RiskTier`):

```json
"MemoryItem": {
  "title": "MemoryItem",
  "type": "object",
  "properties": {
    "id":      { "type": "string" },
    "text":    { "type": "string" },
    "title":   { "type": "string" },
    "type":    { "type": "string" },
    "tags":    { "type": "array", "items": { "type": "string" } },
    "status":  { "type": "string", "enum": ["provisional", "confirmed"] },
    "created": { "type": "string", "format": "date-time" },
    "updated": { "type": "string", "format": "date-time" },
    "links":   { "type": "array", "items": { "type": "string" } }
  },
  "required": ["id", "text", "title", "type", "tags", "status", "created", "links"]
}
```

- [ ] **Step 2: Add the 7 message `$defs`**

Add each to `$defs`:

```json
"MemoryListRequest": {
  "title": "MemoryListRequest",
  "allOf": [ { "$ref": "#/$defs/Envelope" }, {
    "type": "object",
    "properties": {
      "type": { "const": "memory.list_request" },
      "status": { "type": "string", "enum": ["provisional", "confirmed"], "description": "Optional status filter." }
    },
    "required": ["type"]
  } ]
},
"MemoryListResponse": {
  "title": "MemoryListResponse",
  "allOf": [ { "$ref": "#/$defs/Envelope" }, {
    "type": "object",
    "properties": {
      "type": { "const": "memory.list_response" },
      "corr": { "type": "string" },
      "items": { "type": "array", "items": { "$ref": "#/$defs/MemoryItem" } }
    },
    "required": ["type", "corr", "items"]
  } ]
},
"MemoryEdit": {
  "title": "MemoryEdit",
  "allOf": [ { "$ref": "#/$defs/Envelope" }, {
    "type": "object",
    "properties": {
      "type": { "const": "memory.edit" },
      "mem_id": { "type": "string", "description": "Target memory id (envelope id is the message id)." },
      "status": { "type": "string", "enum": ["provisional", "confirmed"] },
      "tags": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["type", "mem_id"]
  } ]
},
"MemoryDelete": {
  "title": "MemoryDelete",
  "allOf": [ { "$ref": "#/$defs/Envelope" }, {
    "type": "object",
    "properties": {
      "type": { "const": "memory.delete" },
      "mem_id": { "type": "string", "description": "Target memory id." }
    },
    "required": ["type", "mem_id"]
  } ]
},
"MemoryAck": {
  "title": "MemoryAck",
  "allOf": [ { "$ref": "#/$defs/Envelope" }, {
    "type": "object",
    "properties": {
      "type": { "const": "memory.ack" },
      "corr": { "type": "string" },
      "ok": { "type": "boolean" },
      "error": { "type": "string", "description": "Why the op failed, when ok is false." }
    },
    "required": ["type", "corr", "ok"]
  } ]
},
"MemoryFormed": {
  "title": "MemoryFormed",
  "allOf": [ { "$ref": "#/$defs/Envelope" }, {
    "type": "object",
    "properties": {
      "type": { "const": "memory.formed" },
      "item": { "$ref": "#/$defs/MemoryItem" },
      "op": { "type": "string", "enum": ["add", "update"] }
    },
    "required": ["type", "item", "op"]
  } ]
},
"MemoryRemoved": {
  "title": "MemoryRemoved",
  "allOf": [ { "$ref": "#/$defs/Envelope" }, {
    "type": "object",
    "properties": {
      "type": { "const": "memory.removed" },
      "mem_id": { "type": "string", "description": "Id of the removed memory." }
    },
    "required": ["type", "mem_id"]
  } ]
}
```

Add the 7 refs to the top-level `oneOf` (after `Error` or anywhere in the list):

```json
{ "$ref": "#/$defs/MemoryListRequest" },
{ "$ref": "#/$defs/MemoryListResponse" },
{ "$ref": "#/$defs/MemoryEdit" },
{ "$ref": "#/$defs/MemoryDelete" },
{ "$ref": "#/$defs/MemoryAck" },
{ "$ref": "#/$defs/MemoryFormed" },
{ "$ref": "#/$defs/MemoryRemoved" }
```

- [ ] **Step 3: Regenerate types**

Run: `cd protocol && uv run python scripts/codegen.py`
Expected: rewrites `gen/python/alfred_protocol/models.py` and `gen/typescript/index.ts` with the new classes/interfaces. Do not edit the output by hand.

- [ ] **Step 4: Add fixtures**

Create each file (use the envelope shape from existing fixtures). `protocol/fixtures/memory_item` is embedded inside the response/formed fixtures.

`memory_list_request.json`:
```json
{ "v": 1, "id": "a0000000-0000-0000-0000-000000000001", "ts": "2026-06-24T20:11:00Z", "type": "memory.list_request" }
```
`memory_list_response.json`:
```json
{ "v": 1, "id": "a0000000-0000-0000-0000-000000000002", "ts": "2026-06-24T20:11:00Z", "type": "memory.list_response", "corr": "a0000000-0000-0000-0000-000000000001", "items": [ { "id": "6bc59450e3e3", "text": "User is 32 and lives in Greece.", "title": "Age and location", "type": "fact", "tags": [], "status": "confirmed", "created": "2026-06-24T20:11:00Z", "links": ["Dimitris", "Greece"] } ] }
```
`memory_edit.json` (note: the **envelope** `id` is the message id; the **target memory** id is `mem_id` — they cannot both be `id` at the top level, which is why the schema uses `mem_id`):
```json
{ "v": 1, "id": "a0000000-0000-0000-0000-000000000003", "ts": "2026-06-24T20:11:00Z", "type": "memory.edit", "mem_id": "6bc59450e3e3", "status": "confirmed" }
```
`memory_delete.json`:
```json
{ "v": 1, "id": "a0000000-0000-0000-0000-000000000004", "ts": "2026-06-24T20:11:00Z", "type": "memory.delete", "mem_id": "6bc59450e3e3" }
```
`memory_ack.json`:
```json
{ "v": 1, "id": "a0000000-0000-0000-0000-000000000005", "ts": "2026-06-24T20:11:00Z", "type": "memory.ack", "corr": "a0000000-0000-0000-0000-000000000003", "ok": true }
```
`memory_formed.json`:
```json
{ "v": 1, "id": "a0000000-0000-0000-0000-000000000006", "ts": "2026-06-24T20:11:00Z", "type": "memory.formed", "op": "add", "item": { "id": "6bc59450e3e3", "text": "User is 32 and lives in Greece.", "title": "Age and location", "type": "fact", "tags": [], "status": "confirmed", "created": "2026-06-24T20:11:00Z", "links": ["Dimitris", "Greece"] } }
```
`memory_removed.json`:
```json
{ "v": 1, "id": "a0000000-0000-0000-0000-000000000007", "ts": "2026-06-24T20:11:00Z", "type": "memory.removed", "mem_id": "6bc59450e3e3" }
```

- [ ] **Step 5: Check fixture test discovery**

Run: `cd protocol && uv run pytest tests/python/test_schema_valid.py -v`
If the test enumerates fixtures explicitly (a hardcoded list) rather than globbing `fixtures/*.json`, add the 7 new fixture names to that list. Same for `tests/python/test_roundtrip.py` and the TS `tests/typescript/roundtrip.test.ts`.

- [ ] **Step 6: Run the full protocol suite (both languages)**

Run: `cd protocol && uv run pytest -v`
Run: `cd protocol && pnpm exec vitest run`
Run: `cd protocol && pnpm exec tsc --noEmit`
Expected: all pass; each fixture validates against the schema and round-trips through Pydantic + TS; conformance holds.

- [ ] **Step 7: Commit (atomic contract change)**

```bash
git add protocol/schema/protocol.schema.json protocol/gen protocol/fixtures
git commit -m "feat(protocol): memory review messages (list/edit/delete/ack/formed/removed + MemoryItem)"
```

---

### Task 2: Brain — list/edit/delete handlers + acks + broadcasts

**Files:**
- Modify: `brain/src/alfred_brain/server.py`
- Test: `brain/tests/test_memory_panel_ws.py` (new)

**Interfaces:**
- Consumes: Task 1's `MemoryItem, MemoryListResponse, MemoryEdit, MemoryDelete, MemoryAck, MemoryFormed, MemoryRemoved` from `alfred_protocol`; `VaultMemory.all/update/forget`.
- Produces: a `memory_item(rec) -> MemoryItem` helper; WS handling for `memory.list_request` / `memory.edit` / `memory.delete`.

- [ ] **Step 1: Write failing tests**

Create `brain/tests/test_memory_panel_ws.py` (model it on `tests/test_server_ws.py`; use the same `client.hello` handshake helper that file uses — read it first to match the connect pattern). Tests to include:

```python
# Pseudocode shape — match the repo's existing WS test harness (FastAPI TestClient
# websocket_connect, send client.hello, read server.hello, then exercise memory.*).
#
# 1. test_list_request_returns_items:
#    seed create_app with an injected memory containing 2 records (one provisional,
#    one confirmed); connect; send memory.list_request; expect memory.list_response
#    with 2 items, newest-first by created.
# 2. test_list_request_status_filter:
#    send memory.list_request with status="provisional"; expect only provisional items.
# 3. test_edit_confirms_and_acks_and_broadcasts:
#    send memory.edit {mem_id, status:"confirmed"}; expect a memory.ack{ok:true} AND a
#    memory.formed{op:"update"} whose item.status == "confirmed".
# 4. test_edit_unknown_id_nacks:
#    memory.edit for a missing id -> memory.ack{ok:false, error set}; no memory.formed.
# 5. test_delete_forgets_acks_and_broadcasts:
#    memory.delete {mem_id} -> memory.ack{ok:true} AND memory.removed{mem_id}; the record
#    is gone from memory.all().
```

Inject a fake/real `VaultMemory` (FakeEmbedder) via `create_app(settings, memory=…)`.

- [ ] **Step 2: Run to verify they fail**

Run: `cd brain && uv run pytest tests/test_memory_panel_ws.py -q`
Expected: FAIL (server replies `unknown_type` for `memory.list_request`).

- [ ] **Step 3: Add imports + `memory_item` helper**

In `server.py`, extend the `alfred_protocol` import with the new classes, and add near the top of `create_app` (or module level):

```python
from alfred_protocol import (
    CommandAck, Error, KillSwitchAck, ServerHello, StatusResponse,
    MemoryItem, MemoryListResponse, MemoryAck, MemoryFormed, MemoryRemoved,
)

def memory_item(rec) -> MemoryItem:
    status = rec.status if rec.status in ("provisional", "confirmed") else "confirmed"
    return MemoryItem(
        id=rec.id, text=rec.text, title=rec.title, type=rec.type,
        tags=list(rec.tags), status=status, created=rec.created,
        updated=rec.updated, links=list(rec.links),
    )
```

- [ ] **Step 4: Add the three WS handler branches**

Inside the `ws()` message loop in `create_app`, add branches alongside the existing `command.submit` / `kill_switch.activate` / `status.request` cases:

```python
                elif kind == "memory.list_request":
                    want = msg.get("status")
                    recs = sorted(memory.all(), key=lambda r: r.created, reverse=True)
                    items = [memory_item(r) for r in recs
                             if want is None or r.status == want]
                    q.put_nowait(dump(MemoryListResponse(
                        v=1, id=new_id(), ts=now_ts(), type="memory.list_response",
                        corr=mid, items=items)))
                elif kind == "memory.edit":
                    rec = memory.update(
                        msg.get("mem_id", ""),
                        status=msg.get("status"), tags=msg.get("tags"))
                    if rec is None:
                        q.put_nowait(dump(MemoryAck(
                            v=1, id=new_id(), ts=now_ts(), type="memory.ack",
                            corr=mid, ok=False, error="memory not found")))
                    else:
                        q.put_nowait(dump(MemoryAck(
                            v=1, id=new_id(), ts=now_ts(), type="memory.ack",
                            corr=mid, ok=True)))
                        bus.publish(dump(MemoryFormed(
                            v=1, id=new_id(), ts=now_ts(), type="memory.formed",
                            item=memory_item(rec), op="update")))
                elif kind == "memory.delete":
                    ok = memory.forget(msg.get("mem_id", ""))
                    q.put_nowait(dump(MemoryAck(
                        v=1, id=new_id(), ts=now_ts(), type="memory.ack",
                        corr=mid, ok=ok, **({} if ok else {"error": "memory not found"}))))
                    if ok:
                        bus.publish(dump(MemoryRemoved(
                            v=1, id=new_id(), ts=now_ts(), type="memory.removed",
                            mem_id=msg.get("mem_id", ""))))
```

(`memory` is the facade already in `create_app` scope; `bus`, `dump`, `new_id`, `now_ts`, `mid` are already in scope in the loop.)

- [ ] **Step 5: Run to verify pass**

Run: `cd brain && uv run pytest tests/test_memory_panel_ws.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/src/alfred_brain/server.py brain/tests/test_memory_panel_ws.py
git commit -m "feat(brain): memory panel WS handlers (list/edit/delete + ack + broadcast)"
```

---

### Task 3: Brain — live push on formation (extractor + tool)

**Files:**
- Modify: `brain/src/alfred_brain/memory/extraction.py`, `brain/src/alfred_brain/memory/tools.py`, `brain/src/alfred_brain/server.py`
- Test: `brain/tests/test_memory_extraction.py`, `brain/tests/test_memory_tools.py`

**Interfaces:**
- Produces: `Extractor(..., on_formed=None)` and `RememberTool(memory, on_formed=None)` where `on_formed: Callable[[MemoryRecord, str], None] | None`; `create_app` wires both to broadcast `memory.formed`.

- [ ] **Step 1: Write failing tests**

In `tests/test_memory_extraction.py` add:

```python
async def test_extract_calls_on_formed_per_applied_op(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    seen = []
    prov = _FakeProvider(
        '{"operations": [{"action": "add", "text": "Dimitris is 32.", '
        '"title": "Dimitris age", "confidence": "high", "stakes": "low", '
        '"entities": [{"name": "Dimitris", "type": "person"}]}]}')
    await Extractor(prov, mem, on_formed=lambda rec, op: seen.append((rec.title, op))).extract(_batch())
    assert seen == [("Dimitris age", "add")]
```

In `tests/test_memory_tools.py` add:

```python
async def test_remember_tool_calls_on_formed(tmp_path):
    from alfred_brain.memory import VaultMemory
    from tests.test_memory_index import FakeEmbedder
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    seen = []
    tool = RememberTool(mem, on_formed=lambda rec, op: seen.append(op))
    await tool.run({"text": "a fact", "title": "Fact"})
    assert seen == ["add"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd brain && uv run pytest tests/test_memory_extraction.py tests/test_memory_tools.py -q`
Expected: FAIL (`Extractor`/`RememberTool` got unexpected keyword `on_formed`).

- [ ] **Step 3: Add `on_formed` to `Extractor`**

In `extraction.py`, extend `__init__` and call it in `_apply`:

```python
    def __init__(self, provider: ReasoningProvider, memory: Memory,
                 *, recall_k: int = 5,
                 on_formed: "Callable[[MemoryRecord, str], None] | None" = None) -> None:
        self._provider = provider
        self._memory = memory
        self._recall_k = recall_k
        self._on_formed = on_formed
        self._lock = asyncio.Lock()
```

(Add `from typing import Callable` if not present.) In `_apply`, after a successful add/update append, emit:

```python
                if op.action == "add":
                    rec = self._memory.remember(
                        op.text, type=op.type, tags=op.tags, status=status,
                        title=op.title, links=links)
                    applied.append(rec)
                    if self._on_formed is not None:
                        self._on_formed(rec, "add")
                elif op.action == "update" and op.id:
                    rec = self._memory.update(
                        op.id, text=op.text, type=op.type, tags=op.tags,
                        status=status, title=(op.title or None), links=(links or None))
                    if rec is not None:
                        applied.append(rec)
                        if self._on_formed is not None:
                            self._on_formed(rec, "update")
```

- [ ] **Step 4: Add `on_formed` to `RememberTool`**

In `tools.py`:

```python
    def __init__(self, memory: Memory,
                 on_formed: "Callable[[object, str], None] | None" = None) -> None:
        self._memory = memory
        self._on_formed = on_formed
```

(Add `from typing import Callable`.) At the end of `run`, after `rec = self._memory.remember(...)`:

```python
        if self._on_formed is not None:
            self._on_formed(rec, "add")
        return f"Remembered ({rec.type}) as {rec.id}."
```

- [ ] **Step 5: Wire the broadcast in `create_app`**

In `server.py`, after `bus` and `memory` exist and before/with the `Extractor` construction, define and pass the callback:

```python
    def _broadcast_formed(rec, op: str) -> None:
        bus.publish(dump(MemoryFormed(
            v=1, id=new_id(), ts=now_ts(), type="memory.formed",
            item=memory_item(rec), op=op)))

    registry.register(RememberTool(memory, on_formed=_broadcast_formed))
    registry.register(RecallTool(memory))
    registry.register(ForgetTool(memory))
    # … extractor construction gains on_formed=_broadcast_formed:
    extractor = Extractor(_extraction_provider(settings, provider), memory,
                          recall_k=settings.memory_extract_recall_k,
                          on_formed=_broadcast_formed)
```

(Replace the existing `RememberTool(memory)` registration and the existing `Extractor(...)` construction with these.)

- [ ] **Step 6: Run to verify pass + full brain suite**

Run: `cd brain && uv run pytest tests/test_memory_extraction.py tests/test_memory_tools.py -q`
Then: `cd brain && uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add brain/src/alfred_brain/memory/extraction.py brain/src/alfred_brain/memory/tools.py brain/src/alfred_brain/server.py brain/tests/test_memory_extraction.py brain/tests/test_memory_tools.py
git commit -m "feat(brain): broadcast memory.formed live from extraction + remember tool"
```

---

### Task 4: Desktop UI — client send helpers + store memory slice

**Files:**
- Modify: `desktop-ui/src/protocol/client.ts`, `desktop-ui/src/store/store.ts`
- Create: `desktop-ui/src/store/memories.ts`
- Test: `desktop-ui/src/store/memories.test.ts` (new), extend `desktop-ui/src/protocol/client.send.test.ts`

**Interfaces:**
- Produces: `ProtocolClient.requestMemoryList(status?)`, `.editMemory(memId, {status?, tags?})`, `.deleteMemory(memId)`; `applyMemoryMessage(state, msg)`; store `memories`, `memoryFilter`, `confirmMemory`, `retagMemory`, `removeMemory`, `setMemoryFilter`.
- Consumes: Task 1's `MemoryItem` and message types from `@alfred/protocol`.

- [ ] **Step 1: Write failing tests**

Create `desktop-ui/src/store/memories.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { applyMemoryMessage, type MemoryState } from "./memories";
import type { Message } from "@alfred/protocol";

const item = (id: string, status: "provisional" | "confirmed") => ({
  id, text: "t", title: "T", type: "fact", tags: [], status,
  created: "2026-06-24T20:11:00Z", links: [],
});

describe("applyMemoryMessage", () => {
  it("replaces on list_response", () => {
    const msg = { v: 1, id: "m1", ts: "x", type: "memory.list_response", corr: "c",
      items: [item("a", "confirmed")] } as unknown as Message;
    const next = applyMemoryMessage({}, msg);
    expect(Object.keys(next)).toEqual(["a"]);
  });
  it("upserts on formed", () => {
    const msg = { v: 1, id: "m2", ts: "x", type: "memory.formed", op: "add",
      item: item("b", "provisional") } as unknown as Message;
    const next = applyMemoryMessage({}, msg);
    expect(next.b.status).toBe("provisional");
  });
  it("deletes on removed", () => {
    const start: MemoryState = { a: item("a", "confirmed") };
    const msg = { v: 1, id: "m3", ts: "x", type: "memory.removed", mem_id: "a" } as unknown as Message;
    expect(applyMemoryMessage(start, msg)).toEqual({});
  });
  it("ignores unrelated messages", () => {
    const start: MemoryState = { a: item("a", "confirmed") };
    const msg = { type: "agent.message" } as unknown as Message;
    expect(applyMemoryMessage(start, msg)).toBe(start);
  });
});
```

In `desktop-ui/src/protocol/client.send.test.ts` add (match its existing harness that captures sent frames):

```typescript
it("editMemory sends a memory.edit with mem_id + patch", () => {
  // … using the test's fake socket, call client.editMemory("abc", { status: "confirmed" })
  // assert the last sent frame: { type: "memory.edit", mem_id: "abc", status: "confirmed", v:1, id, ts }
});
it("deleteMemory sends a memory.delete with mem_id", () => { /* … mem_id: "abc" */ });
it("requestMemoryList sends a memory.list_request", () => { /* optional status omitted when absent */ });
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd desktop-ui && pnpm exec vitest run src/store/memories.test.ts src/protocol/client.send.test.ts`
Expected: FAIL (`memories` module missing; `editMemory` undefined).

- [ ] **Step 3: Create `store/memories.ts`**

```typescript
import type { Message, MemoryItem } from "@alfred/protocol";

export type MemoryState = Record<string, MemoryItem>;

export function applyMemoryMessage(state: MemoryState, msg: Message): MemoryState {
  switch (msg.type) {
    case "memory.list_response": {
      const next: MemoryState = {};
      for (const it of msg.items) next[it.id] = it;
      return next;
    }
    case "memory.formed":
      return { ...state, [msg.item.id]: msg.item };
    case "memory.removed": {
      if (!(msg.mem_id in state)) return state;
      const next = { ...state };
      delete next[msg.mem_id];
      return next;
    }
    default:
      return state;
  }
}
```

- [ ] **Step 4: Add send helpers to `ProtocolClient`**

In `client.ts`, alongside `submitCommand`/`activateKillSwitch`:

```typescript
  requestMemoryList(status?: "provisional" | "confirmed"): string {
    const msg: Message = {
      ...this.envelope(),
      type: "memory.list_request",
      ...(status ? { status } : {}),
    };
    this.sendMessage(msg);
    return msg.id;
  }

  editMemory(memId: string, patch: { status?: "provisional" | "confirmed"; tags?: string[] }): string {
    const msg: Message = {
      ...this.envelope(),
      type: "memory.edit",
      mem_id: memId,
      ...(patch.status ? { status: patch.status } : {}),
      ...(patch.tags ? { tags: patch.tags } : {}),
    };
    this.sendMessage(msg);
    return msg.id;
  }

  deleteMemory(memId: string): string {
    const msg: Message = { ...this.envelope(), type: "memory.delete", mem_id: memId };
    this.sendMessage(msg);
    return msg.id;
  }
```

- [ ] **Step 5: Wire the store slice**

In `store.ts`: extend `AppState` and the store. Add to the interface:

```typescript
  memories: MemoryState;
  memoryFilter: "all" | "provisional";
  confirmMemory: (id: string) => void;
  retagMemory: (id: string, tags: string[]) => void;
  removeMemory: (id: string) => void;
  setMemoryFilter: (f: "all" | "provisional") => void;
```

Import `applyMemoryMessage, type MemoryState` from `./memories`. Initialize `memories: {}`, `memoryFilter: "all"`. In `connect()`:

```typescript
      c.on("phase", (e) => {
        const dropped = e.phase === "reconnecting" || e.phase === "closed";
        set({ /* …existing… */ });
        if (e.phase === "ready") c.requestMemoryList();   // populate panel on connect
      });
      c.on("message", (m) => set({
        turns: applyMessage(get().turns, m),
        memories: applyMemoryMessage(get().memories, m),
      }));
```

Add the actions:

```typescript
    confirmMemory: (id) => client?.editMemory(id, { status: "confirmed" }),
    retagMemory: (id, tags) => client?.editMemory(id, { tags }),
    removeMemory: (id) => client?.deleteMemory(id),
    setMemoryFilter: (f) => set({ memoryFilter: f }),
```

- [ ] **Step 6: Run to verify pass + typecheck**

Run: `cd desktop-ui && pnpm exec vitest run src/store/memories.test.ts src/protocol/client.send.test.ts`
Run: `cd desktop-ui && pnpm exec tsc --noEmit`
Expected: PASS / no type errors.

- [ ] **Step 7: Commit**

```bash
git add desktop-ui/src/protocol/client.ts desktop-ui/src/store/store.ts desktop-ui/src/store/memories.ts desktop-ui/src/store/memories.test.ts desktop-ui/src/protocol/client.send.test.ts
git commit -m "feat(desktop-ui): memory store slice + WS send helpers (list/edit/delete)"
```

---

### Task 5: Desktop UI — the MemoryPanel component

**Files:**
- Create: `desktop-ui/src/components/MemoryPanel.tsx`, `desktop-ui/src/components/MemoryPanel.test.tsx`
- Modify: `desktop-ui/src/App.tsx`

**Interfaces:**
- Consumes: store `memories`, `memoryFilter`, `confirmMemory`, `retagMemory`, `removeMemory`, `setMemoryFilter`.

- [ ] **Step 1: Write failing test**

Create `desktop-ui/src/components/MemoryPanel.test.tsx` (match the RTL setup used by `EventStream.test.tsx` — read it first for the render/store pattern):

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryPanel } from "./MemoryPanel";

// The panel reads from the store hook; the repo's tests typically inject a store.
// Follow EventStream.test.tsx's approach (a test store / provider). Assertions:
// 1. renders a card per memory with its title + status badge.
// 2. clicking Confirm on a provisional card calls confirmMemory(id).
// 3. clicking Delete calls removeMemory(id).
// 4. the "provisional" filter hides confirmed cards.
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd desktop-ui && pnpm exec vitest run src/components/MemoryPanel.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `MemoryPanel.tsx`**

Render from the store; newest-first; filter; per-card Confirm (provisional only) / Delete and a status badge styled like `RiskBadge`.

```tsx
import { useStore } from "../store/store";
import type { MemoryItem } from "@alfred/protocol";

const STATUS_STYLE: Record<string, string> = {
  confirmed: "text-safe border-safe/40",
  provisional: "text-amber border-amber/40",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${STATUS_STYLE[status] ?? "text-hud-dim border-hud-dim/40"}`}>
      {status}
    </span>
  );
}

function MemoryCard({ item }: { item: MemoryItem }) {
  const confirmMemory = useStore((s) => s.confirmMemory);
  const removeMemory = useStore((s) => s.removeMemory);
  return (
    <div className="rounded border border-hud-dim/30 bg-panel/60 p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm text-hud">{item.title}</span>
        <StatusBadge status={item.status} />
      </div>
      <p className="mt-1 text-xs text-hud-dim">{item.text}</p>
      {item.links.length > 0 && (
        <p className="mt-1 text-[10px] uppercase tracking-wider text-hud-dim">
          {item.links.join(" · ")}
        </p>
      )}
      <div className="mt-2 flex gap-2">
        {item.status === "provisional" && (
          <button className="text-[10px] uppercase tracking-wider text-safe"
                  onClick={() => confirmMemory(item.id)}>Confirm</button>
        )}
        <button className="text-[10px] uppercase tracking-wider text-danger"
                onClick={() => removeMemory(item.id)}>Delete</button>
      </div>
    </div>
  );
}

export function MemoryPanel() {
  const memories = useStore((s) => s.memories);
  const filter = useStore((s) => s.memoryFilter);
  const setFilter = useStore((s) => s.setMemoryFilter);
  const items = Object.values(memories)
    .filter((m) => filter === "all" || m.status === "provisional")
    .sort((a, b) => b.created.localeCompare(a.created));

  return (
    <section className="flex min-h-0 flex-col gap-2 border-l border-hud-dim/30 bg-panel/40 p-3">
      <header className="flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-widest text-hud-dim">Memory</h2>
        <div className="flex gap-1">
          {(["all", "provisional"] as const).map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={`text-[10px] uppercase tracking-wider ${filter === f ? "text-hud" : "text-hud-dim"}`}>
              {f}
            </button>
          ))}
        </div>
      </header>
      <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
        {items.length === 0
          ? <p className="text-xs text-hud-dim">No memories yet.</p>
          : items.map((m) => <MemoryCard key={m.id} item={m} />)}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Mount in `App.tsx`**

Put the panel in the right sidebar beside `StatusPanel` (wrap them in a column so both fit):

```tsx
import { MemoryPanel } from "./components/MemoryPanel";
// …
          <div className="flex w-80 min-h-0 flex-col">
            <StatusPanel />
            <MemoryPanel />
          </div>
```

(Replace the bare `<StatusPanel />` in the right side of the flex row with this column.)

- [ ] **Step 5: Run to verify pass + typecheck + full UI suite**

Run: `cd desktop-ui && pnpm exec vitest run`
Run: `cd desktop-ui && pnpm exec tsc --noEmit`
Expected: all pass; no type errors.

- [ ] **Step 6: Commit**

```bash
git add desktop-ui/src/components/MemoryPanel.tsx desktop-ui/src/components/MemoryPanel.test.tsx desktop-ui/src/App.tsx
git commit -m "feat(desktop-ui): MemoryPanel — review/confirm/retag/delete with live updates"
```

---

## Post-plan: docs

- [ ] Update `AGENTS.md` (desktop-ui row / Phase 2) noting the memory review panel exists. Commit `docs: note memory review panel`.
