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
