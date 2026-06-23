# Memory Review Panel — Design

Status: approved (brainstorm) · 2026-06-24
Builds on: memory foundation + formation + titles/linking increments.
Architecture spec §4.5 ("Review: pull-based in the Desktop UI's Memory panel").

## 1. Goal

A Desktop-UI panel to review the memories ALFRED forms: see every memory with its
trust status, **confirm** provisional ones, **re-tag** or **delete** them, with the
list updating **live** as extraction writes facts. This closes the
provisional/confirmed loop (architecture §4.5) and is the mitigation for
"memory poisoning" (§10) — a wrong auto-extracted fact is now visible and removable.

Full text editing is intentionally **out of scope** — reword a memory in Obsidian.
(Caveat: Obsidian edits don't live-sync into the running brain — it reads the vault
at startup and holds an in-memory index — so a reworded fact reflects after the next
brain restart. Panel actions go through the brain and are instant.)

## 2. The protocol change (first since Phase 0)

This is an atomic `protocol/` contract change: edit `schema/protocol.schema.json` →
`uv run python scripts/codegen.py` → commit the regenerated `gen/`. Additive only —
new message types within protocol **v1** (old clients simply never send them; the
handshake/version negotiation is unchanged). The `oneOf` discriminator grows 13 → 20.

### 2.1 Reusable object — `MemoryItem`

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

`updated` is optional and **omitted when absent** (wire invariant: never `null`).

### 2.2 New messages (each `allOf [Envelope, {…}]`)

| Type | Dir | Fields (beyond envelope `v,id,ts,type`) | Required |
|------|-----|------------------------------------------|----------|
| `memory.list_request` | C→S | `status?` (filter) | `type` |
| `memory.list_response` | S→C | `corr`, `items: MemoryItem[]` | `type, corr, items` |
| `memory.edit` | C→S | `id`, `status?`, `tags?: string[]` | `type, id` |
| `memory.delete` | C→S | `id` | `type, id` |
| `memory.ack` | S→C | `corr`, `ok: boolean`, `error?` | `type, corr, ok` |
| `memory.formed` | S→C push | `item: MemoryItem`, `op: "add"\|"update"` | `type, item, op` |
| `memory.removed` | S→C push | `id` | `type, id` |

Confirming = `memory.edit` with `status:"confirmed"`. Re-tagging = `memory.edit` with
`tags`. `memory.edit` carries only `status`/`tags` (no text/title — those are Obsidian's).

## 3. Brain changes

- **Serialization helper** `memory_item(rec: MemoryRecord) -> dict`: maps a record to
  the `MemoryItem` shape, using `model_dump(mode="json", exclude_none=True)` semantics
  (omit `updated` when `None`).
- **WS handler** (`server.py` `ws()` loop) gains three request cases:
  - `memory.list_request` → reply `memory.list_response` with `memory.all()` items
    (filtered by `status` when provided), sorted newest-first by `created`.
  - `memory.edit` → `memory.update(id, status=…, tags=…)`; on success reply
    `memory.ack{ok:true}` **and** `bus.publish(memory.formed{op:"update"})`; on unknown
    id reply `memory.ack{ok:false, error:"not found"}`.
  - `memory.delete` → `memory.forget(id)`; reply `memory.ack`; on success
    `bus.publish(memory.removed{id})`.
- **Live push on formation:** `Extractor` gains an optional
  `on_formed: Callable[[MemoryRecord, str], None]`; `_apply` calls it per applied op
  (`"add"`/`"update"`). `RememberTool` gains the same callback. `create_app` wires both
  to `lambda rec, op: bus.publish(dump(MemoryFormed(... memory_item(rec), op)))`, so
  async extraction and explicit remembers both broadcast to every connected UI.
- All broadcasts use the existing `EventBus` (single-threaded asyncio publish), so they
  reach every subscriber's send queue.

## 4. Desktop-UI changes

- **Generated types** flow from codegen; the UI's Ajv validator gets fixtures for the
  new messages (contract-first — no hand-defined shapes).
- **Store slice** (`store.ts`): `memories: Record<string, MemoryItem>` plus a
  `memoryFilter` ("all" | "provisional"). Reducers for incoming
  `memory.list_response` (replace), `memory.formed` (upsert by id),
  `memory.removed` (delete by id).
- **Client send helpers** (`protocol/client.ts` or a new `protocol/memory.ts`):
  `requestMemoryList(status?)`, `editMemory(id, {status?, tags?})`, `deleteMemory(id)` —
  each builds an enveloped message and sends over the WS.
- **`MemoryPanel.tsx`** (new component, placed in the dashboard per `DESIGN.md`'s HUD
  system): cards newest-first, each showing `title`, the fact `text`, an entity-link row
  (`Dimitris · Greece`), and a **status badge** (`confirmed`/`provisional`, styled like
  the existing `RiskBadge`). Per card: **Confirm** (provisional only → `editMemory(id,
  {status:"confirmed"})`), a **tag editor** (→ `editMemory(id,{tags})`), **Delete** (→
  `deleteMemory(id)`). A header filter toggle (all / provisional). On mount it calls
  `requestMemoryList()`; thereafter it renders from the store, which updates live from
  `memory.formed`/`memory.removed`.

## 5. Testing

- **protocol/**: Ajv (TS) + Pydantic (PY) fixtures for all 7 new messages — valid
  examples round-trip; `updated` omitted-when-absent; bad `status`/`op` enum rejected.
  Codegen drift check passes (CI).
- **brain**: `memory_item` shape (incl. `updated` omitted); WS `memory.list_request`
  returns items filtered + newest-first; `memory.edit` confirms/retags and acks +
  broadcasts `memory.formed`; unknown id → `ack{ok:false}`; `memory.delete` forgets +
  broadcasts `memory.removed`; extraction with an `on_formed` spy broadcasts per op;
  `RememberTool` broadcasts.
- **desktop-ui**: store reducers (list replace, formed upsert, removed delete); send
  helpers build valid enveloped messages; `MemoryPanel` renders cards, fires the right
  message on Confirm/retag/Delete, and live-updates on a pushed `memory.formed`.

## 6. Files

- `protocol/schema/protocol.schema.json` (+ `gen/` regenerated), protocol fixtures.
- `brain/src/alfred_brain/server.py` (handlers + wiring + `memory_item`),
  `memory/extraction.py` (`on_formed`), `memory/tools.py` (`on_formed`).
- `desktop-ui/src/store/store.ts`, `desktop-ui/src/protocol/memory.ts` (new),
  `desktop-ui/src/components/MemoryPanel.tsx` (new) + wiring into `App.tsx`.

## 7. Deferred / future

Two-way Obsidian sync · full text editing in-panel · the daily "urgent" ping for
provisional items · semantic search box in the panel · pagination (fine to render all
memories until the vault is large).
