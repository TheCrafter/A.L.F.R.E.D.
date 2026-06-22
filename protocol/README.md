# ALFRED Protocol

The single source of truth for every message crossing the ALFRED brain
boundary (WebSocket + HTTP). The schema lives in `schema/protocol.schema.json`;
generated Pydantic and TypeScript types live in `gen/` and are committed.

## Layout
- `schema/` — canonical JSON Schema (draft 2020-12)
- `gen/` — generated Pydantic + TS (committed; never hand-edit)
- `fixtures/` — one canonical JSON example per message
- `mock/` — reference fake-brain server + fake-UI client
- `tests/` — round-trip + schema + mock tests

## Commands

Run everything from `protocol/`.

```bash
uv sync                                   # install Python deps
pnpm install                              # install Node deps

uv run python scripts/codegen.py          # regenerate Pydantic + TS from schema
uv run python scripts/codegen.py --python # Python only
uv run python scripts/codegen.py --typescript

uv run pytest -v                          # Python: schema, fixtures, round-trip, mock
pnpm exec tsc --noEmit                    # TS: typecheck + conformance
pnpm exec vitest run                      # TS: Ajv fixture validation
```

After changing `schema/protocol.schema.json`, **always** re-run codegen and
commit the regenerated `gen/` files. CI fails if committed output drifts from
the schema.

## Versioning & handshake

- Every message carries `v` (protocol major version, currently `1`).
- On WebSocket connect, the client sends `client.hello` with the highest
  `protocol_version` it supports. The server replies `server.hello` with the
  negotiated version, or an `error` with `code: "unsupported_version"` and
  closes. Bump the version by changing the `Envelope.v` const and the message
  surface in `schema/protocol.schema.json`, then regenerating.
- Messages are **forward-compatible**: receivers ignore unknown fields, so new
  optional fields can be added without a major bump.

## Running the reference mock

The mock is a contract-valid *fake brain* — no reasoning. Use it to develop the
UI before the real brain exists.

```bash
# Terminal 1 — fake brain
cd protocol
uv run uvicorn mock.server:app --port 8765

# Terminal 2 — fake UI (validates the whole stream, exits 0 on success)
cd protocol
pnpm exec tsx mock/client.ts --url ws://127.0.0.1:8765/ws
```

`GET http://127.0.0.1:8765/status` returns a `status.response`.

## Parallel development runbook

Phase 0 is the contract. Brain and UI now develop in separate worktrees/sessions:

**Brain session (`brain/`, Python):**
```python
from alfred_protocol import Message, CommandSubmit, ServerHello  # generated Pydantic
```
Add `protocol` as a path dependency in `brain/pyproject.toml`
(`alfred-protocol = { path = "../protocol", editable = true }`). Build the real
WebSocket server against these models; test against the fixtures in
`protocol/fixtures/`.

- **Serialize with `exclude_none=True`.** Optional protocol fields (e.g. `reason`, `scope_override`, `corr`) are *omitted when absent*, never sent as `null` — the schema types them as strings, not nullable. When dumping a Pydantic model to send on the wire, use `model.model_dump(mode="json", exclude_none=True)`, exactly as `protocol/mock/server.py` does.

**UI session (`desktop-ui/`, TypeScript):**
```typescript
import type { Message, AgentMessage } from "@alfred/protocol"; // generated TS types
```
Point the UI's WebSocket at the **mock server** (`ws://127.0.0.1:8765/ws`) for
live development until the real brain lands. Validate inbound messages with the
same schema + Ajv pattern shown in `mock/client.ts`.

**Contract changes** are one atomic commit in `protocol/`: edit the schema,
`uv run python scripts/codegen.py`, commit `gen/`. Both sessions pull and pick
up the new types; CI guards against drift.

## Phase 0 acceptance checklist
- [x] Schema is the single source of truth (draft 2020-12).
- [x] Codegen → committed Pydantic + TS; CI fails on drift.
- [x] One golden fixture per message; validated in both languages.
- [x] Pydantic round-trip + Ajv runtime validation pass.
- [x] Reference mock server + client prove the contract over a real socket.
- [x] Version handshake + negotiation defined and tested.
