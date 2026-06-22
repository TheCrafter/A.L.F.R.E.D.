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
(Filled in by later tasks.)
