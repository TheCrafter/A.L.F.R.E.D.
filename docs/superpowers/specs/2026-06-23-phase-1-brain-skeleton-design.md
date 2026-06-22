# ALFRED — Phase 1: Brain Skeleton Design

- **Date:** 2026-06-23
- **Status:** Approved design. Implementation plan to follow in `docs/superpowers/plans/`.
- **Phase:** 1 — Brain skeleton (builds on the frozen Phase 0 `protocol/` contract).
- **Branch / worktree:** `phase-1-brain` (isolated worktree).

---

## 1. Goal

Build the **real** headless brain service behind the frozen `protocol/` contract:
the WebSocket + HTTP server, an event bus, a swappable `ReasoningProvider`, and a
basic tool-calling agent loop that streams `agent.*` events back over the wire.

Acceptance is the **mirror of Phase 0**: the existing, unmodified fake-UI client
`protocol/mock/client.ts` connects to *our real brain* and drives a full command
turn to completion, Ajv-validating every message (exit 0).

This is a **skeleton** — the seams (provider, tools, bus, transport) are the
deliverable. Memory (Phase 2), real hands + safety (Phase 3), UI/voice (Phase 4),
and Telegram (Phase 5) are explicitly out of scope.

---

## 2. Contract adherence (non-negotiable)

- **No new message types.** Everything Phase 1 needs already exists in the 13-message
  contract: `client.hello`/`server.hello`, `status.request`/`status.response`,
  `command.submit`/`command.ack`, `agent.thought`/`agent.action`/`agent.message`/
  `agent.turn_complete`, `kill_switch.activate`/`kill_switch.ack`, `error`. If a new
  shape were ever needed it would be a coordinated `protocol/` change — out of scope here.
- **Import generated Pydantic models:** `from alfred_protocol import ...`. Never redefine
  message shapes. `brain/` adds `alfred-protocol` as an editable path dependency.
- **Wire invariant:** every outgoing message is serialized with
  `model.model_dump(mode="json", exclude_none=True)` through a single helper so optional
  fields are omitted (never `null`), exactly as `protocol/mock/server.py` does.
- **`protocol/` is frozen** — this phase does not touch it.

---

## 3. Reasoning provider (the swap-point)

The architecture spec names "cloud Claude" as the first provider; the project owner's
**cost constraint overrides that** — the Anthropic API is too expensive for this stage.
Because `ReasoningProvider` is explicitly the swap-point, the concrete model is a
one-class choice that touches nothing else.

- **Default real provider: Gemini** via the `google-genai` SDK + a free Google AI Studio
  key. `gemini-2.0-flash` (configurable); supports function calling, which the agent loop
  needs.
- **Swappable via config/registry** with zero changes elsewhere:
  `ALFRED_PROVIDER ∈ {gemini, groq, ollama, scripted}`. Groq (OpenAI-compatible, free
  tier) and Ollama (local, free, the spec's eventual local-model path) are documented
  follow-on providers; only `gemini` and `scripted` are *implemented* in Phase 1.
- **Deterministic `ScriptedProvider`** backs the e2e proof and CI so the contract proof
  never burns quota, hits a rate limit, or flakes, and never needs a key.
- **Startup fallback:** if the selected provider's key is absent, log a warning and fall
  back to `scripted` so the brain always boots.

### `ReasoningProvider` interface

```python
class ReasoningProvider(Protocol):
    name: str
    async def run_turn(
        self, messages: list[TurnMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[ProviderEvent]: ...
```

`run_turn` yields a normalized stream of provider-agnostic events — `Thought(text)`,
`TextChunk(text, final)`, `ToolCallRequest(call_id, tool, args)` — and consumes
tool results fed back through a continued conversation. No SDK types leak above this
interface. Both `GeminiProvider` and `ScriptedProvider` implement it.

---

## 4. Tools

- A `Tool` interface + `ToolRegistry`. Each tool declares a `RiskTier` (from
  `alfred_protocol`).
- **One tool this phase: `echo`** (`risk=safe`) — returns its input. It exists to exercise
  the full tool-calling round-trip, not to do useful work.
- The registry exposes JSON-schema tool specs to the provider and dispatches calls.

```python
class Tool(Protocol):
    name: str
    description: str
    risk: RiskTier
    parameters: dict          # JSON schema for the model
    async def run(self, args: dict) -> str: ...
```

`agent.action(tool, summary, risk)` is emitted with the tool's declared risk before each
`run()`.

---

## 5. Architecture (approach A — event-bus-centric)

```
  WS connection ─┐                         ┌─ ReasoningProvider (Gemini | Scripted)
  WS connection ─┼─ subscribe ─ EventBus ◀─┤
  WS connection ─┘   (pub/sub)      ▲      └─ ToolRegistry (echo)
                                    │ publishes protocol-message dicts
                              AgentLoop ── tracked by ── TurnManager (global kill)
```

- **`EventBus`** — async pub/sub. The agent loop publishes protocol-message dicts; each WS
  connection is a subscriber relaying to its socket. This is what makes spec-mandated
  multi-client broadcast (§4.1: "all observing the same live state") trivial and keeps
  reasoning fully decoupled from transport.
- **`AgentLoop`** — runs one turn: calls the provider, translates `ProviderEvent`s into
  protocol messages, executes tool calls via the registry, feeds results back, and
  re-invokes until a final answer or `ALFRED_MAX_TOOL_ITERATIONS` is reached.
- **`TurnManager`** — tracks in-flight turn tasks by `corr` for the global kill switch.
- **`server.py`** — FastAPI app: `GET /status`, `WS /ws` handshake + intake; wires
  bus ↔ connections. Same stack as the reference mock.

### Module layout

```
brain/
├── pyproject.toml            # uv; alfred-protocol (path, editable) + google-genai, fastapi, uvicorn, pydantic-settings
├── README.md
├── .env.example
├── src/alfred_brain/
│   ├── config.py             # pydantic-settings: provider, keys, model, host/port, max iterations
│   ├── events.py             # EventBus + Subscription
│   ├── messages.py           # new id, RFC-3339 ts, dump(model) -> dict(mode="json", exclude_none=True)
│   ├── providers/{base,registry,gemini,scripted}.py
│   ├── tools/{base,registry,echo}.py
│   ├── agent.py              # AgentLoop
│   ├── session.py            # TurnManager
│   └── server.py             # FastAPI: GET /status, WS /ws
└── tests/
    ├── test_events.py
    ├── test_agent_loop.py
    ├── test_tools.py
    ├── test_server_ws.py
    ├── test_status_http.py
    └── test_e2e_mock_client.py   # real server + protocol/mock/client.ts → exit 0 (integration marker)
```

---

## 6. Data flow — one command turn

1. Client connects to `/ws`, sends `client.hello`.
2. Server validates the handshake:
   - first message not `client.hello` → `error(bad_message)` + close;
   - `protocol_version != 1` → `error(corr=hello.id, unsupported_version)` + close;
   - missing `id` → `error(bad_message)` + close;
   - otherwise reply `server.hello(corr=hello.id, session_id=…)` and subscribe the
     connection to the bus.
3. Client sends `command.submit`. Server emits `command.ack(corr, accepted=true)` and
   spawns a turn task registered with `TurnManager` under `corr`.
4. `AgentLoop` publishes to the bus (→ broadcast to all clients):
   - `agent.thought` — planning line;
   - per tool call: `agent.action(tool, summary, risk)` → execute → feed result back;
   - `agent.message` streamed chunks (`final=false` … last chunk `final=true`);
   - `agent.turn_complete(status="completed")` (or `"error"`).
5. Turn task deregisters from `TurnManager`.

With `ScriptedProvider` this is fully deterministic: one thought → one `echo` action
(risk=safe) → a streamed two-chunk message → `turn_complete(completed)`. That is the
sequence `protocol/mock/client.ts` validates.

---

## 7. Kill switch (global)

`kill_switch.activate` carries no `corr` in the contract → it halts **all** in-flight
turns. `TurnManager.kill_all()` cancels every turn task; each cancelled task, in its
`finally`, publishes `agent.turn_complete(status="killed")` for its `corr`. The server
replies `kill_switch.ack(corr=activate.id, halted=true)`. Cancellation is cooperative
asyncio task cancellation; tool `run()` is awaited within the cancellation scope so an
in-flight tool is interrupted at the next await point.

---

## 8. Error handling

- **Per-message, post-handshake** (does *not* close the socket, matching mock semantics):
  missing `id` → `error(bad_message)`; unknown/unhandled `type` → `error(corr, unknown_type)`;
  malformed JSON / schema-invalid inbound → `error(bad_message)`.
- **Provider failure mid-turn** (quota/network/rate-limit): caught in the loop → a brief
  apology `agent.message(final=true)` + `agent.turn_complete(status="error")`. Socket and
  other turns survive.
- **Connection drop:** unsubscribe from the bus; broadcasts still complete for other clients.
- **Serialization:** always via the `messages.py` helper (`exclude_none=True`) so the wire
  invariant is enforced in one place.

---

## 9. Configuration

`config.py` (pydantic-settings), documented in `.env.example`:

| Var | Default | Purpose |
|-----|---------|---------|
| `ALFRED_PROVIDER` | `gemini` | `gemini` \| `groq` \| `ollama` \| `scripted` |
| `GEMINI_API_KEY` | — | Google AI Studio free key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | model id |
| `ALFRED_HOST` | `127.0.0.1` | bind host |
| `ALFRED_PORT` | `8765` | bind port (matches mock) |
| `ALFRED_MAX_TOOL_ITERATIONS` | `5` | agent-loop cap |

---

## 10. Testing & end-to-end proof

- **Unit/integration (pytest, scripted provider, no network/key):** bus fan-out;
  agent-loop message sequence + risk tiers; tools + registry; server handshake happy path,
  `unsupported_version`, `bad_message`, full command turn, and kill switch driven in-process
  via ASGI / `httpx` / `websockets`; `GET /status` shape.
- **End-to-end (mirror of Phase 0):** `test_e2e_mock_client.py` starts the real brain
  (scripted provider) on a port and runs the *existing, unmodified* `protocol/mock/client.ts`
  via `pnpm exec tsx`, asserting **exit 0**. Marked `integration` (needs Node/pnpm),
  mirroring the protocol package's marker convention.
- **Live smoke test** for `GeminiProvider`: auto-skips when `GEMINI_API_KEY` is unset.

---

## 11. Out of scope (Phase 1)

Memory, real hands/effectors, safety/permission policy beyond emitting the declared
`RiskTier`, persona tuning beyond a minimal system prompt, voice, Telegram, and any
`protocol/` change. These arrive in their own phases.

---

## 12. Acceptance checklist

- [ ] `brain/` package boots a FastAPI server: `GET /status` + `WS /ws`.
- [ ] Handshake: `client.hello` → `server.hello`; `unsupported_version` and `bad_message`
      paths covered; missing `id` rejected.
- [ ] `command.submit` runs a tool-calling turn streaming
      `thought → action → message(chunks) → turn_complete` over the bus to all clients.
- [ ] `ReasoningProvider` interface with `GeminiProvider` + `ScriptedProvider`, selectable
      by config, with scripted fallback.
- [ ] `echo` tool exercised end-to-end through the registry, emitting `agent.action` with
      its risk tier.
- [ ] Global kill switch cancels in-flight turns → `turn_complete(killed)` + `kill_switch.ack`.
- [ ] Multiple simultaneous clients all receive the broadcast event stream.
- [ ] Unmodified `protocol/mock/client.ts` drives the real brain to a valid completed turn
      (exit 0).
- [ ] Outgoing messages use `model_dump(mode="json", exclude_none=True)`; no new message types.
