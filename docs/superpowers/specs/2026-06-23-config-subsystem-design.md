# ALFRED — Config Subsystem Design

- **Date:** 2026-06-23
- **Status:** Approved design (brainstormed). Awaiting implementation plan.
- **Iteration:** MARK I (first spec of the MARK I iteration; Memory is the second).
- **Scope:** Brain configuration — a user-owned config file with env overrides,
  first-run bootstrap, runtime reload, and admin visibility.

---

## 1. Context & motivation

The brain currently reads settings only from environment variables and a dev
`.env` (`brain/src/alfred_brain/config.py`). For an app other people install, we
need durable, user-owned configuration that:

- lives **outside the repo and outside the app directory** (survives reinstalls),
- is **discoverable and editable** (a real file with documented options),
- supports **secrets** without committing them,
- can be **reloaded at runtime** for the settings where that's safe.

This subsystem is also a prerequisite for Memory: the Memory vault path comes from
config, and `$ALFRED_HOME` establishes the user-data home both share.

## 2. Goals / non-goals

**Goals**
- A TOML config file at `$ALFRED_HOME/config.toml`, auto-created on first run.
- Precedence `defaults → config.toml → env vars` (env wins).
- First-run bootstrap that **seeds the file from the current environment** (so an
  existing `.env`-based setup migrates with no manual copying).
- Self-documenting template: every constrained field lists its allowed values in a
  comment; model lists are generated from the registry catalog so they never drift.
- Validated enums (`provider`, `persona.intensity`, `logging.level`).
- Runtime reload of **hot** fields via an admin endpoint; **startup-only** fields
  documented and left untouched until restart.
- Admin visibility: an endpoint showing the **effective** config with the **source
  per field** and **secrets redacted**.

**Non-goals (deferred)**
- **Desktop UI config** — no UI preferences exist yet; building a `desktop-ui.toml`
  now would be speculative. Reserve the location (`$ALFRED_HOME/desktop-ui.toml`);
  add it when a real preference appears.
- **"Save current model as default"** (persisting a dropdown hot-swap back into the
  file) — tidy future add, not now.
- **File-watch / auto-reload** — reload is explicit (endpoint) for now.
- **New WS protocol messages** — config is admin HTTP only; the frozen `protocol/`
  contract is untouched.

## 3. Home & file location

- `ALFRED_HOME` (env var; default `~/.alfred`, `~` expanded per-platform) locates
  the user-data home. It is resolved **before** loading config, since it's where
  the config file itself lives, and cannot itself be set in the file.
- Brain config: `$ALFRED_HOME/config.toml`.
- The Memory vault (next spec) defaults to `$ALFRED_HOME/vault`.

## 4. File format & structure

TOML (read with the stdlib `tomllib`; allows comments). Sectioned by concern:

```toml
# ~/.alfred/config.toml — ALFRED brain config.
# Env vars override any value here (e.g. GROQ_API_KEY). [*] = restart required.

[server]
host = "127.0.0.1"   # [*] bind address
port = 8766          # [*] 1–65535

[reasoning]
provider = "groq"                          # groq | gemini | scripted   (hot-reloadable)
groq_api_key = ""                          # from https://console.groq.com/keys
groq_model = "llama-3.3-70b-versatile"     # llama-3.3-70b-versatile | llama-3.1-8b-instant
gemini_api_key = ""                        # from https://aistudio.google.com/apikey
gemini_model = "gemini-2.5-flash"          # gemini-2.5-flash | gemini-2.0-flash   (free tier)

[persona]
intensity = "full"   # full | light | off   (hot-reloadable)

[agent]
max_tool_iterations = 5   # integer ≥ 1   (hot-reloadable)

[logging]
level = "INFO"   # DEBUG | INFO | WARNING | ERROR | CRITICAL   (hot-reloadable)
```

The `groq_model` / `gemini_model` allowed-value comments are generated from the
registry catalog (`GROQ_MODELS` / `GEMINI_MODELS`) at template-write time.

## 5. Loading & precedence

`defaults → config.toml → env vars` (env wins). Implemented via
`pydantic-settings` `settings_customise_sources`, ordering sources highest-first:
`init → env → dotenv → toml(config.toml) → defaults`. So an env var (or repo
`.env`) overrides the file, which overrides field defaults.

`Settings` **stays flat** (current field names unchanged) — the sectioned TOML is
**flattened on load** by the TOML source via an explicit section→field map. This
keeps every existing access site and test untouched while the *file* stays nicely
sectioned for the user. The map:

| TOML | flat field |
|------|-----------|
| `[server] host` / `port` | `host` / `port` |
| `[reasoning] provider` / `groq_api_key` / `groq_model` / `gemini_api_key` / `gemini_model` | same names |
| `[persona] intensity` | `persona_intensity` |
| `[agent] max_tool_iterations` | `max_tool_iterations` |
| `[logging] level` | `log_level` (new field) |

**Each field keeps its existing env alias** (`validation_alias`), so current env
names stay valid and backward compatible: `GROQ_API_KEY`, `GEMINI_API_KEY`,
`GEMINI_MODEL`, `GROQ_MODEL`, `ALFRED_PROVIDER`, `ALFRED_HOST`, `ALFRED_PORT`,
`ALFRED_PERSONA_INTENSITY`, `ALFRED_MAX_TOOL_ITERATIONS`, plus new
`ALFRED_LOG_LEVEL`.

Validated `Literal`s: `provider ∈ {groq, gemini, scripted}`, `persona_intensity ∈
{full, light, off}`, `log_level ∈ {DEBUG, INFO, WARNING, ERROR, CRITICAL}`. `port`
constrained to 1–65535; `max_tool_iterations ≥ 1`.

## 6. First-run bootstrap

If `$ALFRED_HOME/config.toml` is missing on startup:
1. Create `$ALFRED_HOME/` (and parents) if absent.
2. Write `config.toml` from the documented template, **pre-filling any value found
   in the current environment** (e.g. `GROQ_API_KEY`, `ALFRED_PROVIDER` from a dev
   `.env`), leaving the rest at template defaults / empty.
3. Load normally.

An existing file is **never overwritten** (we only create when missing). Bootstrap
writes are best-effort: if the directory can't be created/written (permissions),
the brain logs a warning and runs on defaults + env rather than failing.

## 7. Runtime reload

- **Hot-reloadable:** `reasoning.provider` + models, `persona.intensity`,
  `agent.max_tool_iterations`, `logging.level`.
- **Startup-only:** `server.host`, `server.port`, `ALFRED_HOME`. Documented `[*]`.

`POST /config/reload`:
1. Re-read and validate the file (+ env overlay).
2. On **success**: apply hot fields to the live brain — rebuild the provider via
   the existing `AgentLoop.set_provider` path, update persona/system prompt, agent
   iteration cap, and logging level. Return `{changed: [...], startup_only_pending:
   [...], current: <redacted effective config>}`.
3. On **failure** (invalid TOML/values): **reject** with HTTP 400 + detail and keep
   the previously-loaded config live — never half-apply.

Reload re-asserts the file, so a prior dropdown hot-swap (`POST /models`) is
overridden back to the config's provider/model.

## 8. Admin endpoints (off-contract HTTP)

Alongside `/status` and `/models`, both leaving the frozen WS contract untouched:

- `GET /config` → effective config, **secrets redacted** (`groq_api_key:
  "set"|"unset"`), with the **source per field** (`default | file | env`) so an
  env var shadowing the file is never a mystery.
- `POST /config/reload` → as in §7.

## 9. Validation & error handling

- **Startup:** invalid TOML syntax or a value failing validation → fail fast with a
  message naming the file path and the offending field.
- **Reload:** validate before applying; on failure return 400 + detail and keep the
  old config (atomic — all hot fields or none).
- **Unknown keys** in the file → log a warning and ignore (tolerant of older/newer
  files), never crash.
- Secrets are never logged or returned unredacted.

## 10. Code shape

A small `config` package in the brain owns:
- `home()` — resolve `$ALFRED_HOME` (env or `~/.alfred`).
- the flat `Settings` model + the section-flattening TOML settings source + per-field
  source tracking.
- `bootstrap()` — create home and write the seeded template when missing.
- `effective_view(settings)` — redacted config + per-field source for `GET /config`.
- `template(settings_env)` — render the documented TOML (model comments from the
  registry catalog).

The server wires `GET /config` and `POST /config/reload`, holds the live `Settings`,
and applies hot changes through the existing provider/persona/agent wiring.

## 11. Testing

Unit tests with a **temp `ALFRED_HOME`** (never the real `~`):
- precedence: env overrides file overrides default;
- bootstrap creates home + writes a file seeded from env; never overwrites an
  existing file; survives an unwritable home (warn + run on defaults);
- validation: bad enum / out-of-range port / bad TOML fail fast at startup;
- reload: hot fields apply; startup-only fields are reported pending, not applied;
  invalid reload is rejected and the old config stays live;
- unknown keys tolerated with a warning;
- `GET /config` redacts secrets and reports correct per-field source.

## 12. Related (tracked separately)

**MARK labeling** (this is the first spec of MARK I) is a small cross-cutting item —
a `MARK` constant, a `MARKS.md` log, and a HUD badge — handled separately from
config, not in this spec.
