# ALFRED Desktop UI

The JARVIS dashboard — a Tauri + React client of the ALFRED brain over the frozen
`protocol/` contract. Renders the live event stream, sends commands, shows status,
and exposes a kill switch. Voice and the memory panel are deferred.

## Develop

```bash
# 1. Start the mock brain (from ../protocol)
uv run uvicorn mock.server:app --port 8765

# 2. Run the dashboard (from desktop-ui)
pnpm install
pnpm dev            # browser renderer at http://localhost:1420 (/status proxied to the mock)
pnpm tauri dev      # native window (requires the Rust toolchain)
```

Point at the real brain later by changing the URL in the connection bar — same contract.

## Test

```bash
pnpm test           # unit + component suites
pnpm typecheck      # tsc --noEmit, strict
# end-to-end against a running mock brain:
ALFRED_MOCK_WS=ws://127.0.0.1:8765/ws pnpm exec vitest run src/protocol/integration.test.ts
```

## Contract

Types come from `@alfred/protocol` and the schema from `@alfred/protocol-schema`
(aliases into the frozen `../protocol/`). Never redefine a message shape; a needed
new message is a coordinated `protocol/` change, not a local invention.

## Known limitations

- A turn left in-flight when the connection drops or reconnects is not auto-finalized
  in the timeline (it stays open without a terminal status); it will resolve on the
  next successful turn. Finalizing stale turns on disconnect is a planned follow-up.
- The kill switch sends `kill_switch.activate` and the resulting `kill_switch.ack` is
  visible in the Wire inspector, but open turns are not yet marked `killed` in the
  event stream. Tying the ack to turn state is a planned follow-up.
