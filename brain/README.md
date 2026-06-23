# ALFRED Brain

The real headless brain: a FastAPI WebSocket + HTTP server speaking the frozen
`protocol/` contract, with an event bus, a swappable reasoning provider
(Gemini, Groq, + deterministic Scripted), a tool-calling agent loop, a global kill
switch, and the ALFRED persona.

## Run

```bash
cd brain
uv sync
cp .env.example .env        # set GEMINI_API_KEY for the real provider (optional)
uv run python -m alfred_brain
```

On first launch the brain creates `~/.alfred/config.toml` (seeded from any env
vars / `.env` present) and reads config from there. Env vars override the file.
`GET /config` shows the effective config (secrets redacted) with each value's
source; `POST /config/reload` re-applies hot fields (provider/model, persona,
agent iterations, log level) without a restart. `host`/`port` need a restart.
Set `ALFRED_HOME` to relocate the config + vault home (default `~/.alfred`).

- HTTP:  `GET http://127.0.0.1:8766/status`
- WS:    `ws://127.0.0.1:8766/ws`
- HTTP (admin, off-contract): `GET /models` lists switchable provider/model combos
  and the live one; `POST /models {"provider","model"}` hot-swaps the reasoning
  model at runtime (used by the desktop model picker; 400 if the key is missing).

Default port is **8766** so the brain can run next to the reference mock
(`8765`) during parallel UI development. Without a configured provider key the
server logs a warning and runs the deterministic **scripted** provider, so it
always boots.

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `ALFRED_PROVIDER` | `gemini` | `gemini` \| `groq` \| `scripted` (`ollama` reserved) |
| `GEMINI_API_KEY` | — | Google AI Studio free key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | model id |
| `GROQ_API_KEY` | — | Groq free key (console.groq.com) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | model id |
| `ALFRED_HOST` | `127.0.0.1` | bind host |
| `ALFRED_PORT` | `8766` | bind port |
| `ALFRED_PERSONA_INTENSITY` | `full` | `off` \| `light` \| `full` |
| `ALFRED_MAX_TOOL_ITERATIONS` | `5` | agent-loop cap |

## Test

```bash
cd brain
uv run pytest -v                       # unit + integration (skips Gemini smoke without a key)
uv run pytest -v -m "not integration"  # fast unit tests only
```

The end-to-end proof (`tests/test_e2e_mock_client.py`) starts the real brain and
runs the unmodified `protocol/mock/client.ts` against it — the mirror of Phase 0.
It needs Node + pnpm with `protocol/` deps installed (`cd protocol && pnpm install`).
