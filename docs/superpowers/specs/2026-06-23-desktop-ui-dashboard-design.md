# ALFRED — Desktop UI Dashboard (MVP) Design

- **Date:** 2026-06-23
- **Status:** Approved design — ready for implementation plan.
- **Phase:** Subset of Phase 4 (Desktop UI). Voice subsystem explicitly deferred.
- **Branch / worktree:** `phase-1-ui` (isolated worktree).
- **Depends on:** `protocol/` (frozen Phase 0 contract). Develops against the reference
  mock brain; swaps to the real brain by changing one URL.

---

## 1. Purpose & scope

Build `desktop-ui/` — the "JARVIS dashboard": a Tauri + React desktop app that is a
faithful, **contract-valid** client of the brain over the frozen WebSocket/HTTP protocol.
It connects to the brain, performs the protocol handshake, renders the live event stream,
sends commands, shows status, and exposes a prominent kill switch. It points at the mock
brain now and at the real brain later with a URL change — same contract.

### In scope (the six surfaces)

1. **Connection bar** — brain base-URL field, connect/disconnect, live connection-state
   indicator, and negotiated session/server info from `server.hello`.
2. **Event stream** — the live timeline of the brain's activity: `agent.thought`,
   `agent.action` (with risk badge), and `agent.message` (assembled from streamed chunks),
   grouped into **turns** keyed by `corr`.
3. **Command input** — sends `command.submit` (`channel: "desktop"`), with an optional
   `scope_override` field.
4. **Status panel** — `GET /status` → `status.response` (uptime, server version, active
   scopes, busy).
5. **Kill switch** — prominent, always-reachable control; sends `kill_switch.activate` and
   renders the returned `kill_switch.ack`.
6. **Wire inspector** — collapsible raw inbound/outbound JSON log with per-message Ajv
   validation pass/fail, direction, and timestamp.

### Out of scope (deferred)

- **Voice** (wake word / STT / TTS) — later Phase 4 pass.
- **Memory review panel** — no protocol messages exist for it yet (Phase 2 produces the
  data; the contract has no memory message types). Adding it would require a coordinated
  protocol change.
- **Multi-client management UI**, **transcript persistence across app restarts**,
  **global kill-switch hotkey** (OS-level hotkey is a later Phase 4 item; the in-app button
  ships now).

### Non-negotiable constraints

- **Contract-first.** Import generated **types** from `@alfred/protocol`
  (`import type { Message, … }`). Never redefine a message shape. **Never edit `protocol/`**
  — it is frozen. If a needed message genuinely does not exist, **stop and flag a
  coordinated protocol change** rather than inventing one.
- **Validate every inbound message** against `schema/protocol.schema.json` with Ajv, exactly
  as `protocol/mock/client.ts` does (`Ajv2020` + `ajv-formats`).
- **Wire invariants** (per AGENTS.md): optional fields are **omitted when absent, never
  `null`**; every message carries the envelope `{ v: 1, id, ts (RFC 3339), type }`.
- TypeScript **strict mode**; never `any`.

---

## 2. Architecture & module boundaries

The wire logic is **framework-agnostic and unit-testable without React**. Three layers:

### 2.1 Protocol layer (pure TypeScript, no React)

- **`ProtocolClient`** — owns a single WebSocket connection and its lifecycle. Responsibilities:
  - Perform the handshake: on open, send `client.hello`
    (`client_name: "alfred-desktop-ui"`, `client_version`, `protocol_version: 1`); wait for
    `server.hello`; treat an `error` `unsupported_version` as a fatal, surfaced failure.
  - **Ajv-validate every inbound message** before emitting it. An invalid message is NOT
    processed — it is surfaced (wire inspector + connection error state).
  - Typed `send` helpers that build envelope + body and serialize:
    `submitCommand(text, { scopeOverride? })` and `activateKillSwitch(reason?)`. Helpers
    set `channel: "desktop"` and never emit `null` for absent optionals (omit instead).
  - **Reconnect** with exponential backoff; re-run the handshake on reconnect.
  - Expose **event taps**: typed inbound-message events, plus raw inbound/outbound taps for
    the wire inspector.
  - Imports **only** `import type { … } from "@alfred/protocol"`.
- **`fetchStatus(baseUrl)`** — performs `GET {baseUrl}/status`, Ajv-validates the body, and
  returns a typed `StatusResponse`. Routed through the Tauri HTTP plugin (see §3.3).

### 2.2 State layer

- A **Zustand store** subscribes to `ProtocolClient` events and holds:
  - **Connection state machine:** `idle → connecting → handshaking → ready →
    reconnecting → closed | error`. Carries `server.hello` info (`server_name`,
    `server_version`, `session_id`, negotiated `protocol_version`) when `ready`.
  - **`turns`** — ordered list keyed by `corr` (the `command.submit` id). Inbound messages
    route to their turn by `corr`.
  - **`status`** — latest `StatusResponse` plus fetch state.
  - **`wireLog`** — bounded ring buffer of raw messages with direction + validation result.

### 2.3 View layer

- One React component per surface in §1, each presentational and reading store slices.
  No component talks to the WebSocket directly — all I/O goes through the store →
  `ProtocolClient`.

### 2.4 The `Turn` model

```
Turn = {
  corr: string,              // id of the command.submit that opened the turn
  commandText: string,
  channel: "desktop",
  scopeOverride?: string,
  ack?: { accepted: boolean, reason?: string },   // from command.ack
  thoughts: AgentThought[],
  actions: AgentAction[],
  message: { text: string, final: boolean },       // assembled from agent.message chunks
  status?: "completed" | "error" | "killed",       // from agent.turn_complete
  startedAt: string, endedAt?: string,
}
```

`agent.message` chunks append to `message.text` until a chunk with `final: true` arrives.
Messages whose `corr` matches no known turn are still logged in the wire inspector and
surfaced as an "orphan" notice (defensive; should not happen with the mock).

---

## 3. Protocol & connection handling

### 3.1 Types and schema sourcing

- **Types:** `desktop-ui/` declares `@alfred/protocol` as a `workspace:*` dependency via a
  new root `pnpm-workspace.yaml` listing `protocol` and `desktop-ui`. The protocol package's
  `main`/`types` already point at `gen/typescript/index.ts`, so `import type` resolves with
  no changes to `protocol/`.
- **Schema JSON (runtime, for Ajv):** imported directly from `protocol/schema/protocol.schema.json`
  through a build alias (Vite `resolve.alias` + matching `tsconfig` path + Vitest alias),
  e.g. `import schema from "@alfred/protocol-schema"`. This reads the frozen file in place —
  **no copy, no edit to `protocol/`** (its `package.json` has no `exports` for the schema and
  we will not add one, since that would modify the frozen contract).

### 3.2 Handshake & validation

Mirror `protocol/mock/client.ts`:
- `Ajv2020({ strict: false, allErrors: true })` + `addFormats`, compiled once from the schema.
- Client sends `client.hello`; server replies `server.hello` (→ `ready`) or `error`
  `unsupported_version` (→ fatal error state, surfaced).
- Every inbound frame is `JSON.parse`d then validated; on failure the client emits a
  validation-error event (logged + connection → `error`) instead of acting on it.

### 3.3 Transport & CORS

- **WebSocket** connects directly to `ws://<host>/ws` (cross-origin WS needs no CORS; the
  mock accepts any origin). Native `WebSocket` in the Tauri webview; the unit tests inject a
  fake WebSocket.
- **`GET /status`** is routed through the **Tauri HTTP plugin** to avoid webview CORS
  (the FastAPI mock sets no CORS headers). For plain-browser component development, a **Vite
  dev-proxy** forwards `/status` to the brain so the same code path works without Tauri.
- **Base URL is configurable** in the connection bar, defaulting to `127.0.0.1:8765`
  (mock brain). WS URL derives as `ws://<host>/ws`, status URL as `http://<host>/status`.

---

## 4. Look & feel — Holographic HUD

- Near-black canvas; **cyan** primary, **amber** for alerts/sensitive; glassmorphic panels;
  monospace data readouts; subtle grid/scanline texture; a pulsing "reactor" connection
  indicator; live glow on streaming message text.
- **Risk badges** color-coded: `safe` (cyan/green), `sensitive` (amber), `forbidden` (red).
- Connection-state and busy indicators are always visible; the **kill switch is always
  reachable** regardless of scroll position.
- **Persona:** Alfred's snark-butler voice flavors empty / loading / error copy (e.g. an
  idle event stream, a disconnected state). **Hard constraint (architecture spec §8): the
  kill-switch confirmation's meaning stays unambiguous** — wit may ride along, but the
  halt/confirm action is never obscured.
- **Stack:** Vite + React 18 + TypeScript (strict), Tailwind CSS with custom HUD theme
  tokens, Zustand, Ajv + ajv-formats. Visual execution leans on the `frontend-design` /
  `impeccable` skills.

---

## 5. Testing strategy (TDD)

- **Unit (Vitest, no browser):**
  - `ProtocolClient`: successful handshake; `unsupported_version` handling; **rejection of a
    schema-invalid inbound message**; `agent.message` chunk assembly; reconnect/backoff;
    `submitCommand` / `activateKillSwitch` emit envelope-correct, `null`-free frames.
  - Turn-routing reducer: messages route to the correct turn by `corr`; orphan handling.
  - `fetchStatus`: valid response parsed; invalid response rejected.
- **Integration:** one test that boots (or connects to) the live mock brain
  (`uv run uvicorn mock.server:app --port 8765`) and drives a full turn end-to-end, asserting
  only contract-valid messages — the UI analogue of `mock/client.ts`.
- **Component smoke tests:** Testing Library + jsdom for the command input (submits) and the
  event stream (renders thought/action/message + risk badge).
- **Typecheck:** `pnpm exec tsc --noEmit` strict, green.

---

## 6. Build sequencing (logical commits on `phase-1-ui`)

1. **Workspace wiring** — root `pnpm-workspace.yaml`; scaffold `desktop-ui/` (Vite + React +
   TS strict, Tailwind, Vitest); `@alfred/protocol` workspace dep; schema alias. Verify
   `tsc --noEmit` and a trivial test pass. No edits to `protocol/`.
2. **Protocol layer (TDD)** — `ProtocolClient` + `fetchStatus`, tested against a fake
   WebSocket and the live mock.
3. **State + minimal UI** — Zustand store + connection bar + event stream + command input
   wired to the mock, running in browser dev.
4. **Status panel + kill switch.**
5. **Wire inspector.**
6. **HUD styling pass** — theme tokens, glow/scanline, persona copy (`frontend-design` /
   `impeccable`).
7. **Tauri shell** — install `rustup`; add Tauri v2 (config, window, HTTP plugin,
   capabilities/CSP for the brain origin); verify end-to-end in the native window against the
   mock brain.

Commits are plain (no `Co-Authored-By: Claude` trailer), conventional and scoped
(`feat(desktop-ui): …`).

---

## 7. Risks & mitigations

- **Webview CORS on `GET /status`** — mitigated by routing status through the Tauri HTTP
  plugin and a Vite dev-proxy for browser work (§3.3).
- **Schema sourcing without touching `protocol/`** — mitigated by a read-only build alias to
  the frozen file rather than an `exports` edit or a copy (§3.1).
- **Rust toolchain footprint** — accepted; `rustup` installed up front per decision, Tauri
  used throughout.
- **Node 25 / pnpm 11** present (AGENTS.md baselines Node 20 / pnpm 9+); newer is compatible.
- **Contract drift temptation** — any missing message halts work and triggers a coordinated
  protocol change, never a local invention.
