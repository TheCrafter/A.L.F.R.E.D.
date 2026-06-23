# ALFRED Desktop UI

The JARVIS dashboard — a Tauri + React client of the ALFRED brain over the frozen
`protocol/` contract. Renders the live event stream, sends commands, shows status,
and exposes a kill switch. Voice and the memory panel are deferred.

## Develop

```bash
# 1. Start the real brain (from ../brain) — defaults to ws://127.0.0.1:8766/ws
cd ../brain ; uv sync ; uv run python -m alfred_brain
# (or the contract mock from ../protocol: uv run uvicorn mock.server:app --port 8765)

# 2. Run the dashboard (from desktop-ui)
pnpm install
pnpm dev            # browser renderer at http://localhost:1420 (/status proxied to :8766)
pnpm tauri dev      # native window (requires the Rust toolchain)
```

The connection bar defaults to `ws://127.0.0.1:8766/ws` (the real brain). Point it
elsewhere by editing the URL — same contract. Note: in the plain-browser renderer the
`/status` proxy target is fixed (see `vite.config.ts`), so cross-port status only
follows the URL bar in the Tauri window (which fetches via the HTTP plugin).

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

## Disconnect & kill behavior

- A turn left in-flight when the connection drops is finalized as `interrupted` in the
  timeline (a UI-local terminal status; the wire only carries
  `completed | error | killed`). The brain also cancels that connection's in-flight
  turns on disconnect, so they don't keep running or leak output to the next client.
- The kill switch sends `kill_switch.activate`; the brain cancels in-flight turns and
  emits `agent.turn_complete status=killed` for each, so open turns are marked `killed`
  in the event stream. The `kill_switch.ack` is also visible in the Wire inspector.
