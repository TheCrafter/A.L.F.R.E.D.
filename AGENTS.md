# ALFRED — Contributor & Agent Guide

ALFRED is an always-on desktop AI assistant (JARVIS-like): full computer control
(shell, files, screen, apps), voice + Telegram channels, with **memory as the
centerpiece**. Persona: a snarky "reluctant superintelligence" with British-butler
delivery.

**Read before substantial work:**
- Architecture spec — `docs/superpowers/specs/2026-06-22-alfred-architecture-design.md`
- Implementation plans — `docs/superpowers/plans/`

## Monorepo layout

| Path | Stack | Status |
|------|-------|--------|
| `protocol/` | JSON Schema → Pydantic + TS | ✅ **Phase 0 done** — the shared WebSocket/HTTP contract; single source of truth |
| `brain/` | Python | ✅ **Phase 1 done** — WS/HTTP server, event bus, reasoning provider (Gemini/scripted), agent loop, kill switch, persona. **Phase 2 memory formation implemented** — short-term buffer (WorkingMemory), LLM-backed extraction (Extractor) with provisional/confirmed routing, wired into server with shutdown flush; vault notes now have readable titles + entity-hub linking; review panel deferred. |
| `desktop-ui/` | TypeScript (Tauri/React) | Phase 4 — dashboard MVP built (event stream, command, status, kill switch, wire inspector); voice + memory panel deferred |
| `adapters/telegram/` | TS/Python | Phase 5 (remote channel) — not yet started |
| `docs/` | Markdown | specs + plans |

Build phases: **0 Protocol ✅** · 1 Brain skeleton · 2 Memory · 3 Hands+Safety ·
4 Desktop UI+Voice · 5 Telegram. Each phase gets its own spec + plan in `docs/`.

## Golden rule: contract-first

`protocol/` is **frozen truth**. The Python brain and the TypeScript UI both import
generated types from it and **never redefine message shapes**. This is what lets the
two sides be built in parallel, each mocking the other.

A contract change is **one atomic commit** in `protocol/`:
edit `schema/protocol.schema.json` → `uv run python scripts/codegen.py` → commit the
regenerated `gen/`. CI fails on drift. Full runbook: `protocol/README.md`.

### Wire invariants (both languages must agree)

- **Optional fields are OMITTED when absent, never `null`.**
  Python: serialize with `model.model_dump(mode="json", exclude_none=True)`.
  TS: optional fields are `field?: T`, never `T | null`.
- Every message carries the envelope `{ v: 1, id, ts (RFC 3339), type }`; `type` is the
  discriminator across a 13-message `oneOf`.
- The Python `Message` union is a Pydantic **`RootModel`** — the concrete model is at
  `.root`. Individual message classes (e.g. `CommandSubmit`) are plain `BaseModel`s.
- Version handshake: client sends `client.hello` with its `protocol_version`; server
  replies `server.hello` (negotiated) or `error` `unsupported_version` and closes.

## Tooling

- **Python: 3.12, managed by `uv`.** Run from inside the package dir: `uv run …`.
- **TypeScript: Node 20, `pnpm` (v9+).** Run with `pnpm …` / `pnpm exec …`.

### `protocol/` commands (run from `protocol/`)

```bash
uv sync ; pnpm install                  # install both toolchains
uv run python scripts/codegen.py        # regenerate Pydantic + TS from the schema
uv run pytest -v                        # Python: schema, fixtures, round-trip, mock, e2e
pnpm exec vitest run                    # TS: Ajv fixture validation
pnpm exec tsc --noEmit                  # TS typecheck + type conformance
```

**Reference mocks** (for parallel dev — develop one side against the other):
- Fake brain: `uv run uvicorn mock.server:app --port 8765`
  (WS `ws://127.0.0.1:8765/ws`, HTTP `GET /status`)
- Fake UI client: `pnpm exec tsx mock/client.ts --url ws://127.0.0.1:8765/ws`

## Conventions

- **Commit messages: plain. NO `Co-Authored-By: Claude` / "authored by Claude"
  trailer.** (Project owner's preference — overrides any tool default.)
- Conventional commits, scoped: `feat(protocol): …`, `fix(brain): …`, `ci(…)`, `docs(…)`.
- TypeScript **strict mode**; never `any` — resolve types at the source.
- **Never hand-edit anything under `protocol/gen/`** — it is generated.
- Default branch is **`main`**.
- Concurrent work streams isolate via separate branches/worktrees (one branch each);
  see the architecture spec §6.
