# Phase 0 — Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `protocol/` package — a single JSON-Schema source of truth for every WebSocket/HTTP message crossing the brain boundary, with codegen to Pydantic v2 + TypeScript, golden fixtures, round-trip tests, a CI drift guard, and a runnable reference mock server + client — so the brain and desktop-ui can be developed in parallel sessions, each mocking the other against a frozen contract.

**Architecture:** One JSON Schema file (`schema/protocol.schema.json`, draft 2020-12) is the canonical contract. A Python orchestrator (`scripts/codegen.py`) regenerates committed Pydantic models (via `datamodel-code-generator`) and TypeScript types (via `json-schema-to-typescript`). Golden fixtures — one canonical JSON per message — are validated against the schema, round-tripped through Pydantic, and runtime-validated with Ajv. A FastAPI "fake brain" mock server emits contract-valid events; a `ws`-based "fake UI" mock client connects, validates every received message with Ajv, and exits non-zero on any violation. CI regenerates and fails on drift, then runs all suites.

**Tech Stack:** JSON Schema 2020-12 · Python 3.12 + uv · Pydantic v2 · datamodel-code-generator · jsonschema · FastAPI + uvicorn + websockets · pytest · Node 20 + pnpm · TypeScript 5 · json-schema-to-typescript · Ajv 8 + ajv-formats · ws · tsx · vitest.

## Global Constraints

- **Python:** 3.12, managed by `uv`. All Python commands run via `uv run …` from inside `protocol/`.
- **Node:** 20, package manager `pnpm` (v9). All TS commands run via `pnpm …` / `pnpm exec …` from inside `protocol/`.
- **JSON Schema dialect:** draft **2020-12** (`https://json-schema.org/draft/2020-12/schema`). Every message validates against this dialect.
- **Codegen is deterministic and committed.** Generated files in `protocol/gen/` are checked into git. CI regenerates and runs `git diff --exit-code protocol/gen` — any drift fails the build. Never hand-edit anything under `gen/`.
  - `datamodel-codegen` MUST be invoked with `--disable-timestamp` so output is byte-stable.
- **Forward-compatible messages.** No message schema sets `additionalProperties: false`. Receivers tolerate unknown fields so the protocol can add fields without breaking older clients. Pydantic v2's default `extra='ignore'` and TypeScript structural typing both honor this.
- **Envelope on every message:** `v` (protocol major version, integer, `1` for this protocol), `id` (string, unique per message), `ts` (string, RFC 3339 / ISO-8601 `date-time`). Plus `type` (string literal discriminator).
- **Discriminator:** the top-level `Message` is a `oneOf` over all message definitions, discriminated by the `type` property.
- **Class/interface names** are controlled by the `title` of each `$def` (e.g. `CommandSubmit`). Keep titles in PascalCase matching the message intent.
- **No live brain in Phase 0.** The mock server is a scripted replayer with zero reasoning; it lives in `protocol/mock/`, never in `brain/`. The real brain WebSocket server is Phase 1.

---

## File Structure

```
protocol/
├── README.md                              # regen / run-mock / run-tests + two-session runbook
├── .gitignore                             # node_modules, .venv, __pycache__, dist, .pytest_cache
├── pyproject.toml                         # uv project "alfred-protocol" (Python pkg + dev deps)
├── package.json                           # pnpm project "@alfred/protocol" (TS pkg + dev deps)
├── tsconfig.json                          # TS config (strict, resolveJsonModule, NodeNext)
├── vitest.config.ts                       # vitest config
├── schema/
│   └── protocol.schema.json               # ⭐ SINGLE SOURCE OF TRUTH (JSON Schema 2020-12)
├── gen/                                    # GENERATED — committed, never hand-edited
│   ├── python/alfred_protocol/
│   │   ├── __init__.py                    # hand-written stable re-export of models.py
│   │   └── models.py                      # generated Pydantic v2 models + Message union
│   └── typescript/
│       └── index.ts                       # generated TS types + Message union
├── scripts/
│   └── codegen.py                         # regenerates BOTH gen/ outputs from the schema
├── fixtures/                               # one canonical JSON example per message
│   ├── client_hello.json
│   ├── server_hello.json
│   ├── status_request.json
│   ├── status_response.json
│   ├── command_submit.json
│   ├── command_ack.json
│   ├── agent_thought.json
│   ├── agent_action.json
│   ├── agent_message.json
│   ├── agent_turn_complete.json
│   ├── kill_switch_activate.json
│   ├── kill_switch_ack.json
│   └── error.json
├── mock/
│   ├── server.py                          # fake brain: FastAPI HTTP /status + WS /ws
│   └── client.ts                          # fake UI: connects, validates stream, exits 0/1
└── tests/
    ├── python/
    │   ├── test_schema_valid.py           # schema is valid 2020-12; fixtures validate
    │   ├── test_roundtrip.py              # fixtures ↔ Pydantic round-trip stability
    │   └── test_mock_server.py            # handshake, command stream, kill, negotiation
    └── typescript/
        ├── roundtrip.test.ts              # Ajv runtime-validates every fixture
        └── conformance.test-d.ts          # tsc proves generated types are constructible

.github/workflows/protocol.yml             # CI: drift check + all test suites (repo root)
```

**Message surface (Phase-1 core, 13 messages).** Direction is informational; the schema does not encode direction.

| `type` | title | direction | purpose |
|---|---|---|---|
| `client.hello` | `ClientHello` | client→brain | announce client + supported protocol version |
| `server.hello` | `ServerHello` | brain→client | accept connection, negotiated version, session id |
| `status.request` | `StatusRequest` | client→brain | request status (HTTP `GET /status`) |
| `status.response` | `StatusResponse` | brain→client | uptime, version, active scopes, busy flag |
| `command.submit` | `CommandSubmit` | client→brain | user instruction + origin channel + optional scope override |
| `command.ack` | `CommandAck` | brain→client | accepted/rejected acknowledgement of a command |
| `agent.thought` | `AgentThought` | brain→client | a reasoning/status line in the agent loop |
| `agent.action` | `AgentAction` | brain→client | a tool invocation (name, summary, risk tier) |
| `agent.message` | `AgentMessage` | brain→client | assistant/persona text chunk (`final` flag for streaming) |
| `agent.turn_complete` | `AgentTurnComplete` | brain→client | turn finished (completed/error/killed) |
| `kill_switch.activate` | `KillSwitchActivate` | client→brain | halt all action |
| `kill_switch.ack` | `KillSwitchAck` | brain→client | confirm halt |
| `error` | `Error` | brain→client | protocol/processing error (with code) |

---

## Task 1: Scaffold the protocol package (Python + TypeScript)

**Files:**
- Create: `protocol/pyproject.toml`
- Create: `protocol/package.json`
- Create: `protocol/tsconfig.json`
- Create: `protocol/vitest.config.ts`
- Create: `protocol/.gitignore`
- Create: `protocol/README.md` (skeleton)
- Create: `protocol/gen/python/alfred_protocol/__init__.py` (placeholder)

**Interfaces:**
- Produces: a `uv`-managed Python project named `alfred-protocol` and a `pnpm`-managed TS project `@alfred/protocol`, both installable, both runnable from `protocol/`. Later tasks run `uv run …` and `pnpm exec …` from this directory.

- [ ] **Step 1: Create `protocol/pyproject.toml`**

```toml
[project]
name = "alfred-protocol"
version = "0.1.0"
description = "ALFRED shared WebSocket/HTTP contract: schema, generated Pydantic models, fixtures, and reference mock server."
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.6",
]

[dependency-groups]
dev = [
    "datamodel-code-generator>=0.25.5",
    "jsonschema>=4.21",
    "pytest>=8.0",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "websockets>=12.0",
    "httpx>=0.27",
]

[tool.uv]
package = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["gen/python/alfred_protocol"]

[tool.pytest.ini_options]
pythonpath = ["gen/python", "."]
testpaths = ["tests/python"]
```

- [ ] **Step 2: Create `protocol/package.json`**

```json
{
  "name": "@alfred/protocol",
  "version": "0.1.0",
  "private": true,
  "description": "ALFRED shared WebSocket/HTTP contract: generated TypeScript types and reference mock client.",
  "type": "module",
  "main": "gen/typescript/index.ts",
  "types": "gen/typescript/index.ts",
  "scripts": {
    "gen:ts": "json2ts -i schema/protocol.schema.json -o gen/typescript/index.ts --additionalProperties --no-style.singleQuote",
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "mock:client": "tsx mock/client.ts"
  },
  "devDependencies": {
    "json-schema-to-typescript": "^14.0.0",
    "ajv": "^8.13.0",
    "ajv-formats": "^3.0.1",
    "ws": "^8.17.0",
    "@types/ws": "^8.5.10",
    "@types/node": "^20.12.0",
    "tsx": "^4.10.0",
    "typescript": "^5.4.0",
    "vitest": "^1.6.0"
  }
}
```

- [ ] **Step 3: Create `protocol/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noEmit": true,
    "resolveJsonModule": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["gen/typescript", "mock", "tests/typescript"]
}
```

- [ ] **Step 4: Create `protocol/vitest.config.ts`**

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/typescript/**/*.test.ts"],
    environment: "node",
  },
});
```

- [ ] **Step 5: Create `protocol/.gitignore`**

```gitignore
# Python
.venv/
__pycache__/
*.pyc
.pytest_cache/
# Node
node_modules/
# tooling
.uv/
```

- [ ] **Step 6: Create `protocol/gen/python/alfred_protocol/__init__.py` placeholder**

```python
"""ALFRED protocol — generated Pydantic models.

This package re-exports the generated models from ``models.py``. The models
module is produced by ``scripts/codegen.py`` and committed; do not edit it by
hand. Until codegen runs, importing models will fail — that is expected during
initial scaffolding.
"""
```

- [ ] **Step 7: Create `protocol/README.md` skeleton**

```markdown
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
```

- [ ] **Step 8: Install both toolchains**

Run:
```bash
cd protocol
uv sync
pnpm install
```
Expected: `uv sync` creates `.venv` and `uv.lock`; `pnpm install` creates `node_modules` and `pnpm-lock.yaml`. No errors.

- [ ] **Step 9: Verify both toolchains run**

Run:
```bash
uv run python -c "import pydantic; print('pydantic', pydantic.VERSION)"
pnpm exec tsc --version
pnpm exec json2ts --help >/dev/null && echo "json2ts ok"
```
Expected: prints a `pydantic 2.x` line, a `Version 5.x` line, and `json2ts ok`.

- [ ] **Step 10: Commit**

```bash
git add protocol/pyproject.toml protocol/package.json protocol/tsconfig.json \
        protocol/vitest.config.ts protocol/.gitignore protocol/README.md \
        protocol/gen/python/alfred_protocol/__init__.py \
        protocol/uv.lock protocol/pnpm-lock.yaml
git commit -m "chore(protocol): scaffold uv + pnpm package"
```

---

## Task 2: Author the JSON Schema contract + schema-validity test

**Files:**
- Create: `protocol/schema/protocol.schema.json`
- Test: `protocol/tests/python/test_schema_valid.py`

**Interfaces:**
- Produces: `schema/protocol.schema.json` — a valid draft-2020-12 schema whose root `Message` is a `oneOf` of 13 message `$defs`, each merging the shared `Envelope` via `allOf`. Every `$def` has a PascalCase `title` (drives generated class names). `test_schema_valid.py::test_schema_is_valid_2020_12` asserts the schema itself is a legal 2020-12 schema. Fixture validation is added in Task 3.

- [ ] **Step 1: Write the failing test**

`protocol/tests/python/test_schema_valid.py`:
```python
import json
from pathlib import Path

from jsonschema.validators import Draft202012Validator

SCHEMA_PATH = Path(__file__).parents[2] / "schema" / "protocol.schema.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_is_valid_2020_12():
    schema = load_schema()
    # Raises jsonschema.exceptions.SchemaError if the schema is itself invalid.
    Draft202012Validator.check_schema(schema)


def test_schema_has_all_thirteen_messages():
    schema = load_schema()
    titles = {d["title"] for d in schema["$defs"].values()}
    expected = {
        "ClientHello", "ServerHello", "StatusRequest", "StatusResponse",
        "CommandSubmit", "CommandAck", "AgentThought", "AgentAction",
        "AgentMessage", "AgentTurnComplete", "KillSwitchActivate",
        "KillSwitchAck", "Error",
    }
    assert expected <= titles
    assert len(schema["oneOf"]) == 13
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd protocol && uv run pytest tests/python/test_schema_valid.py -v`
Expected: FAIL — `FileNotFoundError` / no such file `schema/protocol.schema.json`.

- [ ] **Step 3: Write the schema**

`protocol/schema/protocol.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://alfred.local/protocol/v1.json",
  "title": "Message",
  "description": "Any message crossing the ALFRED brain boundary.",
  "discriminator": { "propertyName": "type" },
  "oneOf": [
    { "$ref": "#/$defs/ClientHello" },
    { "$ref": "#/$defs/ServerHello" },
    { "$ref": "#/$defs/StatusRequest" },
    { "$ref": "#/$defs/StatusResponse" },
    { "$ref": "#/$defs/CommandSubmit" },
    { "$ref": "#/$defs/CommandAck" },
    { "$ref": "#/$defs/AgentThought" },
    { "$ref": "#/$defs/AgentAction" },
    { "$ref": "#/$defs/AgentMessage" },
    { "$ref": "#/$defs/AgentTurnComplete" },
    { "$ref": "#/$defs/KillSwitchActivate" },
    { "$ref": "#/$defs/KillSwitchAck" },
    { "$ref": "#/$defs/Error" }
  ],
  "$defs": {
    "Envelope": {
      "title": "Envelope",
      "type": "object",
      "description": "Fields shared by every message.",
      "properties": {
        "v": { "type": "integer", "description": "Protocol major version.", "const": 1 },
        "id": { "type": "string", "description": "Unique id for this message." },
        "ts": { "type": "string", "format": "date-time", "description": "RFC 3339 UTC timestamp." }
      },
      "required": ["v", "id", "ts"]
    },
    "Channel": {
      "title": "Channel",
      "type": "string",
      "enum": ["desktop", "telegram", "voice"]
    },
    "RiskTier": {
      "title": "RiskTier",
      "type": "string",
      "enum": ["safe", "sensitive", "forbidden"]
    },
    "ClientHello": {
      "title": "ClientHello",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "client.hello" },
            "client_name": { "type": "string" },
            "client_version": { "type": "string" },
            "protocol_version": { "type": "integer", "description": "Highest protocol version the client supports." }
          },
          "required": ["type", "client_name", "client_version", "protocol_version"]
        }
      ]
    },
    "ServerHello": {
      "title": "ServerHello",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "server.hello" },
            "corr": { "type": "string", "description": "id of the client.hello being answered." },
            "server_name": { "type": "string" },
            "server_version": { "type": "string" },
            "protocol_version": { "type": "integer", "description": "Negotiated protocol version." },
            "session_id": { "type": "string" }
          },
          "required": ["type", "corr", "server_name", "server_version", "protocol_version", "session_id"]
        }
      ]
    },
    "StatusRequest": {
      "title": "StatusRequest",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": { "type": { "const": "status.request" } },
          "required": ["type"]
        }
      ]
    },
    "StatusResponse": {
      "title": "StatusResponse",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "status.response" },
            "corr": { "type": "string" },
            "uptime_seconds": { "type": "number" },
            "server_version": { "type": "string" },
            "active_scopes": { "type": "array", "items": { "type": "string" } },
            "busy": { "type": "boolean" }
          },
          "required": ["type", "corr", "uptime_seconds", "server_version", "active_scopes", "busy"]
        }
      ]
    },
    "CommandSubmit": {
      "title": "CommandSubmit",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "command.submit" },
            "text": { "type": "string" },
            "channel": { "$ref": "#/$defs/Channel" },
            "scope_override": { "type": "string", "description": "Optional manual scope, e.g. 'business'." }
          },
          "required": ["type", "text", "channel"]
        }
      ]
    },
    "CommandAck": {
      "title": "CommandAck",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "command.ack" },
            "corr": { "type": "string" },
            "accepted": { "type": "boolean" },
            "reason": { "type": "string", "description": "Why rejected, when accepted is false." }
          },
          "required": ["type", "corr", "accepted"]
        }
      ]
    },
    "AgentThought": {
      "title": "AgentThought",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "agent.thought" },
            "corr": { "type": "string" },
            "text": { "type": "string" }
          },
          "required": ["type", "corr", "text"]
        }
      ]
    },
    "AgentAction": {
      "title": "AgentAction",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "agent.action" },
            "corr": { "type": "string" },
            "tool": { "type": "string" },
            "summary": { "type": "string" },
            "risk": { "$ref": "#/$defs/RiskTier" }
          },
          "required": ["type", "corr", "tool", "summary", "risk"]
        }
      ]
    },
    "AgentMessage": {
      "title": "AgentMessage",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "agent.message" },
            "corr": { "type": "string" },
            "text": { "type": "string" },
            "final": { "type": "boolean", "description": "False for a streamed chunk; true for the last chunk of the message." }
          },
          "required": ["type", "corr", "text", "final"]
        }
      ]
    },
    "AgentTurnComplete": {
      "title": "AgentTurnComplete",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "agent.turn_complete" },
            "corr": { "type": "string" },
            "status": { "type": "string", "enum": ["completed", "error", "killed"] }
          },
          "required": ["type", "corr", "status"]
        }
      ]
    },
    "KillSwitchActivate": {
      "title": "KillSwitchActivate",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "kill_switch.activate" },
            "channel": { "$ref": "#/$defs/Channel" },
            "reason": { "type": "string" }
          },
          "required": ["type", "channel"]
        }
      ]
    },
    "KillSwitchAck": {
      "title": "KillSwitchAck",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "kill_switch.ack" },
            "corr": { "type": "string" },
            "halted": { "type": "boolean" }
          },
          "required": ["type", "corr", "halted"]
        }
      ]
    },
    "Error": {
      "title": "Error",
      "allOf": [
        { "$ref": "#/$defs/Envelope" },
        {
          "type": "object",
          "properties": {
            "type": { "const": "error" },
            "corr": { "type": "string" },
            "code": { "type": "string", "enum": ["bad_message", "unsupported_version", "unknown_type", "internal"] },
            "message": { "type": "string" }
          },
          "required": ["type", "code", "message"]
        }
      ]
    }
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd protocol && uv run pytest tests/python/test_schema_valid.py -v`
Expected: PASS — both `test_schema_is_valid_2020_12` and `test_schema_has_all_thirteen_messages`.

- [ ] **Step 5: Commit**

```bash
git add protocol/schema/protocol.schema.json protocol/tests/python/test_schema_valid.py
git commit -m "feat(protocol): define JSON Schema contract for Phase-1 message surface"
```

---

## Task 3: Golden fixtures + fixture-validation test

**Files:**
- Create: all 13 files under `protocol/fixtures/`
- Modify: `protocol/tests/python/test_schema_valid.py` (add fixture validation)

**Interfaces:**
- Consumes: `schema/protocol.schema.json` from Task 2.
- Produces: `fixtures/<name>.json` — one canonical, schema-valid example per message, used by every downstream test and by the mock client. `test_schema_valid.py::test_all_fixtures_validate` asserts each fixture validates against the schema and that there is exactly one fixture per message `type`.

- [ ] **Step 1: Write the failing test (extend the existing file)**

Append to `protocol/tests/python/test_schema_valid.py`:
```python
import pytest
from jsonschema import Draft202012Validator, FormatChecker

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"

EXPECTED_TYPES = {
    "client.hello", "server.hello", "status.request", "status.response",
    "command.submit", "command.ack", "agent.thought", "agent.action",
    "agent.message", "agent.turn_complete", "kill_switch.activate",
    "kill_switch.ack", "error",
}


def fixture_files() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


def test_one_fixture_per_message_type():
    types = set()
    for f in fixture_files():
        types.add(json.loads(f.read_text(encoding="utf-8"))["type"])
    assert types == EXPECTED_TYPES


@pytest.mark.parametrize("fixture", fixture_files(), ids=lambda p: p.stem)
def test_fixture_validates_against_schema(fixture: Path):
    schema = load_schema()
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    data = json.loads(fixture.read_text(encoding="utf-8"))
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    assert not errors, f"{fixture.name}: " + "; ".join(e.message for e in errors)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd protocol && uv run pytest tests/python/test_schema_valid.py -v`
Expected: FAIL — `test_one_fixture_per_message_type` fails (empty `types` set ≠ expected); parametrized fixture test collects nothing.

- [ ] **Step 3: Write the fixtures**

`protocol/fixtures/client_hello.json`:
```json
{ "v": 1, "id": "11111111-1111-1111-1111-111111111111", "ts": "2026-06-23T10:00:00Z", "type": "client.hello", "client_name": "desktop-ui", "client_version": "0.1.0", "protocol_version": 1 }
```

`protocol/fixtures/server_hello.json`:
```json
{ "v": 1, "id": "22222222-2222-2222-2222-222222222222", "ts": "2026-06-23T10:00:00Z", "type": "server.hello", "corr": "11111111-1111-1111-1111-111111111111", "server_name": "alfred-brain", "server_version": "0.1.0", "protocol_version": 1, "session_id": "sess-abc" }
```

`protocol/fixtures/status_request.json`:
```json
{ "v": 1, "id": "33333333-3333-3333-3333-333333333333", "ts": "2026-06-23T10:00:01Z", "type": "status.request" }
```

`protocol/fixtures/status_response.json`:
```json
{ "v": 1, "id": "44444444-4444-4444-4444-444444444444", "ts": "2026-06-23T10:00:01Z", "type": "status.response", "corr": "33333333-3333-3333-3333-333333333333", "uptime_seconds": 12.5, "server_version": "0.1.0", "active_scopes": ["coding"], "busy": false }
```

`protocol/fixtures/command_submit.json`:
```json
{ "v": 1, "id": "55555555-5555-5555-5555-555555555555", "ts": "2026-06-23T10:00:02Z", "type": "command.submit", "text": "check the build", "channel": "desktop", "scope_override": "coding" }
```

`protocol/fixtures/command_ack.json`:
```json
{ "v": 1, "id": "66666666-6666-6666-6666-666666666666", "ts": "2026-06-23T10:00:02Z", "type": "command.ack", "corr": "55555555-5555-5555-5555-555555555555", "accepted": true }
```

`protocol/fixtures/agent_thought.json`:
```json
{ "v": 1, "id": "77777777-7777-7777-7777-777777777777", "ts": "2026-06-23T10:00:03Z", "type": "agent.thought", "corr": "55555555-5555-5555-5555-555555555555", "text": "Inspecting the project for a build script." }
```

`protocol/fixtures/agent_action.json`:
```json
{ "v": 1, "id": "88888888-8888-8888-8888-888888888888", "ts": "2026-06-23T10:00:04Z", "type": "agent.action", "corr": "55555555-5555-5555-5555-555555555555", "tool": "shell", "summary": "Run `npm run build`", "risk": "sensitive" }
```

`protocol/fixtures/agent_message.json`:
```json
{ "v": 1, "id": "99999999-9999-9999-9999-999999999999", "ts": "2026-06-23T10:00:05Z", "type": "agent.message", "corr": "55555555-5555-5555-5555-555555555555", "text": "The build is green, sir.", "final": true }
```

`protocol/fixtures/agent_turn_complete.json`:
```json
{ "v": 1, "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "ts": "2026-06-23T10:00:06Z", "type": "agent.turn_complete", "corr": "55555555-5555-5555-5555-555555555555", "status": "completed" }
```

`protocol/fixtures/kill_switch_activate.json`:
```json
{ "v": 1, "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "ts": "2026-06-23T10:00:07Z", "type": "kill_switch.activate", "channel": "telegram", "reason": "stop everything" }
```

`protocol/fixtures/kill_switch_ack.json`:
```json
{ "v": 1, "id": "cccccccc-cccc-cccc-cccc-cccccccccccc", "ts": "2026-06-23T10:00:07Z", "type": "kill_switch.ack", "corr": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "halted": true }
```

`protocol/fixtures/error.json`:
```json
{ "v": 1, "id": "dddddddd-dddd-dddd-dddd-dddddddddddd", "ts": "2026-06-23T10:00:08Z", "type": "error", "corr": "55555555-5555-5555-5555-555555555555", "code": "unknown_type", "message": "Unrecognized message type." }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd protocol && uv run pytest tests/python/test_schema_valid.py -v`
Expected: PASS — `test_one_fixture_per_message_type` plus 13 parametrized `test_fixture_validates_against_schema[...]` cases.

- [ ] **Step 5: Commit**

```bash
git add protocol/fixtures/ protocol/tests/python/test_schema_valid.py
git commit -m "feat(protocol): add golden fixtures + schema validation test"
```

---

## Task 4: Python codegen + Pydantic round-trip test

**Files:**
- Create: `protocol/scripts/codegen.py` (Python half only for now; TS half added in Task 5)
- Modify: `protocol/gen/python/alfred_protocol/__init__.py`
- Generate: `protocol/gen/python/alfred_protocol/models.py`
- Test: `protocol/tests/python/test_roundtrip.py`

**Interfaces:**
- Consumes: `schema/protocol.schema.json`, `fixtures/*.json`.
- Produces: `scripts/codegen.py` exposing `generate_python()` (and a `__main__` entry). `gen/python/alfred_protocol/models.py` defines one Pydantic v2 class per message (named by `title`) plus a `Message` discriminated-union alias. `alfred_protocol.__init__` re-exports `Message` and every message class. Later tasks (mock server) import `from alfred_protocol import Message, CommandSubmit, ServerHello, …`.

- [ ] **Step 1: Write `scripts/codegen.py` (Python generation)**

`protocol/scripts/codegen.py`:
```python
"""Regenerate committed Pydantic + TypeScript types from the protocol schema.

Run from the protocol/ directory:
    uv run python scripts/codegen.py            # both languages
    uv run python scripts/codegen.py --python   # Python only
    uv run python scripts/codegen.py --typescript

Output is deterministic (no timestamps) so CI can diff it against the committed
files and fail on drift.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schema" / "protocol.schema.json"
PY_OUT = ROOT / "gen" / "python" / "alfred_protocol" / "models.py"
TS_OUT = ROOT / "gen" / "typescript" / "index.ts"


def generate_python() -> None:
    PY_OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "datamodel-codegen",
        "--input", str(SCHEMA),
        "--input-file-type", "jsonschema",
        "--output", str(PY_OUT),
        "--output-model-type", "pydantic_v2.BaseModel",
        "--use-annotated",
        "--use-schema-description",
        "--use-field-description",
        "--target-python-version", "3.12",
        "--disable-timestamp",
        "--use-double-quotes",
    ]
    print("→", " ".join(cmd))
    subprocess.run(cmd, check=True)


def generate_typescript() -> None:
    TS_OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "pnpm", "exec", "json2ts",
        "-i", str(SCHEMA),
        "-o", str(TS_OUT),
        "--additionalProperties",
    ]
    print("→", " ".join(cmd))
    subprocess.run(cmd, check=True, shell=(sys.platform == "win32"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", action="store_true")
    parser.add_argument("--typescript", action="store_true")
    args = parser.parse_args()
    do_all = not (args.python or args.typescript)
    if args.python or do_all:
        generate_python()
    if args.typescript or do_all:
        generate_typescript()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run Python codegen**

Run: `cd protocol && uv run python scripts/codegen.py --python`
Expected: creates `gen/python/alfred_protocol/models.py` containing classes `ClientHello`, `ServerHello`, … `Error`, and a `Message` union. No error.

- [ ] **Step 3: Inspect the generated union name**

Run: `cd protocol && uv run python -c "import ast,sys; src=open('gen/python/alfred_protocol/models.py').read(); print('Message' in src, 'class CommandSubmit' in src)"`
Expected: prints `True True`. (If the root alias is not named `Message`, note the actual name — the schema's root `title: Message` should produce it.)

- [ ] **Step 4: Write the re-export `__init__.py`**

Replace `protocol/gen/python/alfred_protocol/__init__.py`:
```python
"""ALFRED protocol — generated Pydantic models (re-exported).

``models.py`` is generated by ``scripts/codegen.py`` and committed; do not edit
it by hand. This module gives consumers a stable import surface.
"""
from .models import (  # noqa: F401
    AgentAction,
    AgentMessage,
    AgentThought,
    AgentTurnComplete,
    ClientHello,
    CommandAck,
    CommandSubmit,
    Error,
    KillSwitchAck,
    KillSwitchActivate,
    Message,
    ServerHello,
    StatusRequest,
    StatusResponse,
)

__all__ = [
    "AgentAction",
    "AgentMessage",
    "AgentThought",
    "AgentTurnComplete",
    "ClientHello",
    "CommandAck",
    "CommandSubmit",
    "Error",
    "KillSwitchAck",
    "KillSwitchActivate",
    "Message",
    "ServerHello",
    "StatusRequest",
    "StatusResponse",
]
```

- [ ] **Step 5: Write the failing round-trip test**

`protocol/tests/python/test_roundtrip.py`:
```python
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from alfred_protocol import Message

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"
ADAPTER = TypeAdapter(Message)


def fixture_files() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


@pytest.mark.parametrize("fixture", fixture_files(), ids=lambda p: p.stem)
def test_fixture_roundtrips_through_pydantic(fixture: Path):
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    model = ADAPTER.validate_python(raw)
    # Dump back to JSON, re-parse: the model must be stable across a round trip.
    reparsed = ADAPTER.validate_json(ADAPTER.dump_json(model))
    assert model == reparsed


@pytest.mark.parametrize("fixture", fixture_files(), ids=lambda p: p.stem)
def test_discriminator_picks_the_right_class(fixture: Path):
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    model = ADAPTER.validate_python(raw)
    # The chosen model's `type` literal must equal the fixture's type field.
    assert model.type == raw["type"]
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd protocol && uv run pytest tests/python/test_roundtrip.py -v`
Expected: PASS — 26 cases (13 round-trip + 13 discriminator). If `validate_python` raises a discriminator error, confirm the schema's root `discriminator.propertyName` is `type` and each branch has a `type` const.

- [ ] **Step 7: Commit**

```bash
git add protocol/scripts/codegen.py protocol/gen/python/ protocol/tests/python/test_roundtrip.py
git commit -m "feat(protocol): generate Pydantic models + round-trip tests"
```

---

## Task 5: TypeScript codegen + Ajv runtime validation + type conformance

**Files:**
- Generate: `protocol/gen/typescript/index.ts`
- Test: `protocol/tests/typescript/roundtrip.test.ts`
- Test: `protocol/tests/typescript/conformance.test-d.ts`

**Interfaces:**
- Consumes: `schema/protocol.schema.json`, `fixtures/*.json`, `scripts/codegen.py::generate_typescript`.
- Produces: `gen/typescript/index.ts` exporting a `Message` union type plus one interface per message (e.g. `CommandSubmit`, `ServerHello`). The mock client (Task 8) imports these. `roundtrip.test.ts` runtime-validates every fixture with Ajv; `conformance.test-d.ts` proves the generated types are constructible under `tsc`.

- [ ] **Step 1: Run TypeScript codegen**

Run: `cd protocol && uv run python scripts/codegen.py --typescript`
Expected: creates `gen/typescript/index.ts` with `export type Message = ClientHello | ServerHello | …` and one `export interface` per message. No error.

- [ ] **Step 2: Verify the generated TS compiles**

Run: `cd protocol && pnpm exec tsc --noEmit`
Expected: no type errors.

- [ ] **Step 3: Write the failing Ajv runtime test**

`protocol/tests/typescript/roundtrip.test.ts`:
```typescript
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it, expect } from "vitest";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const schema = JSON.parse(readFileSync(join(root, "schema", "protocol.schema.json"), "utf-8"));
const fixturesDir = join(root, "fixtures");

// strict:false so Ajv ignores the OpenAPI-style `discriminator` keyword.
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const validate = ajv.compile(schema);

const fixtures = readdirSync(fixturesDir).filter((f) => f.endsWith(".json"));

describe("fixtures validate against the protocol schema (Ajv)", () => {
  it("has 13 fixtures", () => {
    expect(fixtures.length).toBe(13);
  });

  for (const file of fixtures) {
    it(`validates ${file}`, () => {
      const data = JSON.parse(readFileSync(join(fixturesDir, file), "utf-8"));
      const ok = validate(data);
      expect(validate.errors ?? []).toEqual([]);
      expect(ok).toBe(true);
    });
  }
});
```

- [ ] **Step 4: Run the Ajv test to verify it passes**

Run: `cd protocol && pnpm exec vitest run`
Expected: PASS — 14 assertions (count check + 13 fixtures). If Ajv throws on the `discriminator` keyword, confirm `strict: false` is set.

- [ ] **Step 5: Write the type-conformance check**

`protocol/tests/typescript/conformance.test-d.ts`:
```typescript
// Compile-time only: proves the generated types are usable and coherent.
// Checked by `tsc --noEmit`; never executed.
import type {
  Message,
  CommandSubmit,
  ServerHello,
  AgentMessage,
  Error as ProtocolError,
} from "../../gen/typescript/index.js";

const command: CommandSubmit = {
  v: 1,
  id: "x",
  ts: "2026-06-23T10:00:02Z",
  type: "command.submit",
  text: "check the build",
  channel: "desktop",
};

const hello: ServerHello = {
  v: 1,
  id: "y",
  ts: "2026-06-23T10:00:00Z",
  type: "server.hello",
  corr: "x",
  server_name: "alfred-brain",
  server_version: "0.1.0",
  protocol_version: 1,
  session_id: "sess-abc",
};

const chunk: AgentMessage = {
  v: 1, id: "z", ts: "2026-06-23T10:00:05Z",
  type: "agent.message", corr: "x", text: "…", final: true,
};

const err: ProtocolError = {
  v: 1, id: "e", ts: "2026-06-23T10:00:08Z",
  type: "error", code: "unknown_type", message: "nope",
};

// All four must be assignable to the discriminated union.
const all: Message[] = [command, hello, chunk, err];
void all;
```

- [ ] **Step 6: Run the conformance check**

Run: `cd protocol && pnpm exec tsc --noEmit`
Expected: no errors. (If a property name in the generated interface differs from the fixtures — e.g. casing — this fails and reveals a schema/codegen mismatch to fix before proceeding.)

- [ ] **Step 7: Commit**

```bash
git add protocol/gen/typescript/ protocol/tests/typescript/
git commit -m "feat(protocol): generate TS types + Ajv validation + type conformance"
```

---

## Task 6: Unified codegen + CI drift guard

**Files:**
- Create: `.github/workflows/protocol.yml` (repo root)
- Modify: `protocol/README.md` (commands section)

**Interfaces:**
- Consumes: `scripts/codegen.py` (both halves), all test suites.
- Produces: a CI workflow that regenerates `gen/`, fails on any drift from the committed output, and runs the Python + TS suites. No new code interfaces.

- [ ] **Step 1: Verify full regeneration is a no-op (no drift locally)**

Run:
```bash
cd protocol
uv run python scripts/codegen.py
git status --porcelain gen/
```
Expected: `git status` prints nothing — regenerating both languages reproduces the committed files byte-for-byte. If `gen/python/...` shows changes, confirm `--disable-timestamp` is in `codegen.py`; re-commit the canonical output before continuing.

- [ ] **Step 2: Write the CI workflow**

`.github/workflows/protocol.yml`:
```yaml
name: protocol

on:
  push:
    paths: ["protocol/**", ".github/workflows/protocol.yml"]
  pull_request:
    paths: ["protocol/**", ".github/workflows/protocol.yml"]

jobs:
  contract:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: protocol
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          python-version: "3.12"

      - name: Install pnpm
        uses: pnpm/action-setup@v4
        with:
          version: 9

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
          cache-dependency-path: protocol/pnpm-lock.yaml

      - name: Install Python deps
        run: uv sync

      - name: Install Node deps
        run: pnpm install --frozen-lockfile

      - name: Regenerate types
        run: uv run python scripts/codegen.py

      - name: Fail on codegen drift
        run: git diff --exit-code gen/

      - name: Python tests
        run: uv run pytest -v

      - name: TypeScript typecheck
        run: pnpm exec tsc --noEmit

      - name: TypeScript tests
        run: pnpm exec vitest run
```

- [ ] **Step 3: Update `protocol/README.md` commands section**

Replace the `## Commands` section of `protocol/README.md` with:
````markdown
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
````

- [ ] **Step 4: Verify the workflow file is valid YAML**

Run: `cd protocol && uv run python -c "import yaml,sys; yaml.safe_load(open('../.github/workflows/protocol.yml')); print('yaml ok')"`
Expected: prints `yaml ok`. (If PyYAML is unavailable, instead confirm structure by eye; PyYAML ships transitively but is not required.)

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/protocol.yml protocol/README.md
git commit -m "ci(protocol): add codegen drift guard + test workflow"
```

---

## Task 7: Reference mock server (Python "fake brain") + tests

**Files:**
- Create: `protocol/mock/server.py`
- Test: `protocol/tests/python/test_mock_server.py`

**Interfaces:**
- Consumes: `alfred_protocol` models (Task 4), `schema/protocol.schema.json` (for test validation).
- Produces: `mock/server.py` exposing `app` (a FastAPI app) with `GET /status` → `status.response` and `WS /ws` implementing the handshake, a scripted command turn, kill-switch ack, and version negotiation. `make_envelope()` / per-message builders stamp valid envelopes. Reusable by the integration test in Task 8.

- [ ] **Step 1: Write the failing test**

`protocol/tests/python/test_mock_server.py`:
```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from mock.server import app, SUPPORTED_PROTOCOL_VERSION

SCHEMA_PATH = Path(__file__).parents[2] / "schema" / "protocol.schema.json"
VALIDATOR = Draft202012Validator(
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8")), format_checker=FormatChecker()
)


def assert_valid(msg: dict) -> None:
    errors = sorted(VALIDATOR.iter_errors(msg), key=lambda e: e.path)
    assert not errors, "; ".join(e.message for e in errors)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def hello(version: int = SUPPORTED_PROTOCOL_VERSION) -> dict:
    return {
        "v": 1, "id": "client-hello-1", "ts": "2026-06-23T10:00:00Z",
        "type": "client.hello", "client_name": "test", "client_version": "0.0.1",
        "protocol_version": version,
    }


def test_http_status_is_valid(client: TestClient):
    resp = client.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert_valid(body)
    assert body["type"] == "status.response"


def test_ws_handshake_returns_server_hello(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_json(hello())
        reply = ws.receive_json()
        assert_valid(reply)
        assert reply["type"] == "server.hello"
        assert reply["corr"] == "client-hello-1"
        assert reply["protocol_version"] == SUPPORTED_PROTOCOL_VERSION


def test_command_produces_valid_event_stream(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_json(hello())
        ws.receive_json()  # server.hello
        ws.send_json({
            "v": 1, "id": "cmd-1", "ts": "2026-06-23T10:00:02Z",
            "type": "command.submit", "text": "check the build", "channel": "desktop",
        })
        seen: list[str] = []
        while True:
            msg = ws.receive_json()
            assert_valid(msg)
            assert msg.get("corr") == "cmd-1"
            seen.append(msg["type"])
            if msg["type"] == "agent.turn_complete":
                break
        assert seen[0] == "command.ack"
        assert "agent.thought" in seen
        assert "agent.action" in seen
        assert "agent.message" in seen
        assert seen[-1] == "agent.turn_complete"


def test_kill_switch_is_acknowledged(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_json(hello())
        ws.receive_json()
        ws.send_json({
            "v": 1, "id": "kill-1", "ts": "2026-06-23T10:00:07Z",
            "type": "kill_switch.activate", "channel": "telegram",
        })
        ack = ws.receive_json()
        assert_valid(ack)
        assert ack["type"] == "kill_switch.ack"
        assert ack["corr"] == "kill-1"
        assert ack["halted"] is True


def test_unsupported_version_is_rejected(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_json(hello(version=999))
        err = ws.receive_json()
        assert_valid(err)
        assert err["type"] == "error"
        assert err["code"] == "unsupported_version"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd protocol && uv run pytest tests/python/test_mock_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mock.server'`.

- [ ] **Step 3: Write the mock server**

`protocol/mock/server.py`:
```python
"""Reference mock 'fake brain'.

A scripted replayer with ZERO reasoning. It exists only so the desktop-ui can
develop against a live, contract-valid endpoint while the real brain is built
in a separate session. It builds every outgoing message from the generated
Pydantic models, so anything it emits is guaranteed to satisfy the contract.

Run it:
    uv run uvicorn mock.server:app --port 8765
"""
from __future__ import annotations

import itertools
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from alfred_protocol import (
    AgentAction,
    AgentMessage,
    AgentThought,
    AgentTurnComplete,
    CommandAck,
    Error,
    KillSwitchAck,
    ServerHello,
    StatusResponse,
)

SUPPORTED_PROTOCOL_VERSION = 1
SERVER_NAME = "alfred-mock-brain"
SERVER_VERSION = "0.1.0"

app = FastAPI(title="ALFRED mock brain")
_ids = itertools.count(1)
_started = datetime.now(timezone.utc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mid() -> str:
    return f"mock-{next(_ids)}"


def _dump(model) -> dict:
    # mode="json" so datetimes/enums serialize to JSON-native values.
    return model.model_dump(mode="json")


@app.get("/status")
def status() -> dict:
    uptime = (datetime.now(timezone.utc) - _started).total_seconds()
    return _dump(StatusResponse(
        v=1, id=_mid(), ts=_now(), type="status.response",
        corr="http-status", uptime_seconds=uptime,
        server_version=SERVER_VERSION, active_scopes=["coding"], busy=False,
    ))


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    await socket.accept()
    try:
        hello = await socket.receive_json()
        if hello.get("type") != "client.hello":
            await socket.send_json(_dump(Error(
                v=1, id=_mid(), ts=_now(), type="error",
                code="bad_message", message="Expected client.hello first.",
            )))
            await socket.close()
            return
        if hello.get("protocol_version") != SUPPORTED_PROTOCOL_VERSION:
            await socket.send_json(_dump(Error(
                v=1, id=_mid(), ts=_now(), type="error", corr=hello.get("id"),
                code="unsupported_version",
                message=f"This server speaks protocol v{SUPPORTED_PROTOCOL_VERSION}.",
            )))
            await socket.close()
            return

        await socket.send_json(_dump(ServerHello(
            v=1, id=_mid(), ts=_now(), type="server.hello", corr=hello["id"],
            server_name=SERVER_NAME, server_version=SERVER_VERSION,
            protocol_version=SUPPORTED_PROTOCOL_VERSION, session_id="mock-session",
        )))

        while True:
            msg = await socket.receive_json()
            kind = msg.get("type")
            if kind == "command.submit":
                await _run_command_turn(socket, msg["id"])
            elif kind == "kill_switch.activate":
                await socket.send_json(_dump(KillSwitchAck(
                    v=1, id=_mid(), ts=_now(), type="kill_switch.ack",
                    corr=msg["id"], halted=True,
                )))
            else:
                await socket.send_json(_dump(Error(
                    v=1, id=_mid(), ts=_now(), type="error", corr=msg.get("id"),
                    code="unknown_type", message=f"Unhandled type: {kind}",
                )))
    except WebSocketDisconnect:
        return


async def _run_command_turn(socket: WebSocket, corr: str) -> None:
    await socket.send_json(_dump(CommandAck(
        v=1, id=_mid(), ts=_now(), type="command.ack", corr=corr, accepted=True,
    )))
    await socket.send_json(_dump(AgentThought(
        v=1, id=_mid(), ts=_now(), type="agent.thought", corr=corr,
        text="Inspecting the project for a build script.",
    )))
    await socket.send_json(_dump(AgentAction(
        v=1, id=_mid(), ts=_now(), type="agent.action", corr=corr,
        tool="shell", summary="Run `npm run build`", risk="sensitive",
    )))
    await socket.send_json(_dump(AgentMessage(
        v=1, id=_mid(), ts=_now(), type="agent.message", corr=corr,
        text="The build is ", final=False,
    )))
    await socket.send_json(_dump(AgentMessage(
        v=1, id=_mid(), ts=_now(), type="agent.message", corr=corr,
        text="green, sir.", final=True,
    )))
    await socket.send_json(_dump(AgentTurnComplete(
        v=1, id=_mid(), ts=_now(), type="agent.turn_complete", corr=corr,
        status="completed",
    )))
```

- [ ] **Step 4: Add `mock/__init__.py` so the test can import `mock.server`**

Create `protocol/mock/__init__.py` (empty file):
```python
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd protocol && uv run pytest tests/python/test_mock_server.py -v`
Expected: PASS — all 5 tests. If `model_dump(mode="json")` rejects the literal `type=`, note that generated models accept the literal as a default; passing it explicitly is still valid.

- [ ] **Step 6: Commit**

```bash
git add protocol/mock/server.py protocol/mock/__init__.py protocol/tests/python/test_mock_server.py
git commit -m "feat(protocol): reference mock brain server + tests"
```

---

## Task 8: Reference mock client (TS "fake UI") + end-to-end integration test

**Files:**
- Create: `protocol/mock/client.ts`
- Test: `protocol/tests/python/test_integration.py`

**Interfaces:**
- Consumes: generated TS types (Task 5), `mock/server.py` (Task 7), `schema/protocol.schema.json`.
- Produces: `mock/client.ts` — a runnable script that connects to a `--url`, performs the handshake, sends a command, Ajv-validates every received message, prints the stream, and exits `0` if every message is valid (and the turn completes) or `1` otherwise. `test_integration.py` boots the server in-process and runs the client subprocess end-to-end across both languages.

- [ ] **Step 1: Write the mock client**

`protocol/mock/client.ts`:
```typescript
/**
 * Reference mock "fake UI" client.
 *
 * Connects to a mock brain, performs the protocol handshake, submits one
 * command, and validates every received message against the schema with Ajv.
 * Exits 0 if the full turn completes with only valid messages; exits 1 on the
 * first invalid message or on timeout.
 *
 *   pnpm exec tsx mock/client.ts --url ws://127.0.0.1:8765/ws
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import WebSocket from "ws";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import type { Message } from "../gen/typescript/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const schema = JSON.parse(
  readFileSync(join(here, "..", "schema", "protocol.schema.json"), "utf-8"),
);
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const validate = ajv.compile(schema);

function urlArg(): string {
  const i = process.argv.indexOf("--url");
  return i >= 0 ? process.argv[i + 1] : "ws://127.0.0.1:8765/ws";
}

function envelope() {
  return { v: 1 as const, id: `ui-${Math.floor(performance.now())}`, ts: new Date().toISOString() };
}

function fail(reason: string): never {
  console.error(`✗ ${reason}`);
  process.exit(1);
}

const ws = new WebSocket(urlArg());
const timer = setTimeout(() => fail("timed out waiting for turn_complete"), 5000);

ws.on("open", () => {
  const hello: Message = {
    ...envelope(), type: "client.hello",
    client_name: "mock-ui", client_version: "0.1.0", protocol_version: 1,
  };
  ws.send(JSON.stringify(hello));
});

let sawServerHello = false;

ws.on("message", (raw) => {
  const data = JSON.parse(raw.toString());
  if (!validate(data)) {
    fail(`invalid message ${data?.type}: ${ajv.errorsText(validate.errors)}`);
  }
  console.log(`✓ ${data.type}`);

  if (data.type === "server.hello") {
    sawServerHello = true;
    const cmd: Message = {
      ...envelope(), type: "command.submit",
      text: "check the build", channel: "desktop",
    };
    ws.send(JSON.stringify(cmd));
  } else if (data.type === "agent.turn_complete") {
    clearTimeout(timer);
    if (!sawServerHello) fail("turn completed without a server.hello");
    console.log("✓ turn complete — contract verified end-to-end");
    ws.close();
    process.exit(0);
  } else if (data.type === "error") {
    fail(`server error: ${data.code} ${data.message}`);
  }
});

ws.on("error", (err) => fail(`socket error: ${err.message}`));
```

- [ ] **Step 2: Write the failing integration test**

`protocol/tests/python/test_integration.py`:
```python
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from mock.server import app

ROOT = Path(__file__).parents[2]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Server:
    def __init__(self, port: int):
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("mock server did not start")
        return self

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(timeout=5)


@pytest.mark.integration
def test_ts_client_completes_against_python_server():
    port = _free_port()
    with _Server(port):
        result = subprocess.run(
            ["pnpm", "exec", "tsx", "mock/client.ts", "--url", f"ws://127.0.0.1:{port}/ws"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
            shell=(sys.platform == "win32"),
        )
    assert result.returncode == 0, f"client failed:\n{result.stdout}\n{result.stderr}"
    assert "turn complete — contract verified end-to-end" in result.stdout
    assert "agent.turn_complete" in result.stdout
```

- [ ] **Step 3: Register the `integration` marker**

Add to `protocol/pyproject.toml` under `[tool.pytest.ini_options]`:
```toml
markers = ["integration: cross-language end-to-end tests (needs Node + pnpm)"]
```

- [ ] **Step 4: Run the integration test to verify it passes**

Run: `cd protocol && uv run pytest tests/python/test_integration.py -v`
Expected: PASS — the TS client connects to the Python server, validates the full stream, and exits 0. (First run may be slow while `tsx` warms up.)

- [ ] **Step 5: Run the whole suite to confirm nothing regressed**

Run:
```bash
cd protocol
uv run pytest -v
pnpm exec vitest run
pnpm exec tsc --noEmit
```
Expected: all green.

- [ ] **Step 6: Add the integration job to CI**

Add this step to `.github/workflows/protocol.yml` after the existing "TypeScript tests" step:
```yaml
      - name: End-to-end mock (Python server ↔ TS client)
        run: uv run pytest tests/python/test_integration.py -v
```

- [ ] **Step 7: Commit**

```bash
git add protocol/mock/client.ts protocol/tests/python/test_integration.py \
        protocol/pyproject.toml .github/workflows/protocol.yml
git commit -m "feat(protocol): reference mock UI client + cross-language e2e test"
```

---

## Task 9: Versioning doc + two-session parallel-dev runbook (Phase 0 acceptance)

**Files:**
- Modify: `protocol/README.md` (add versioning + runbook + mock usage)

**Interfaces:**
- Consumes: everything above. Produces no code — this task documents how the brain and desktop-ui sessions consume the contract, and records the Phase-0 acceptance checklist.

- [ ] **Step 1: Append versioning + runbook to `protocol/README.md`**

Append to `protocol/README.md`:
````markdown
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
````

- [ ] **Step 2: Verify the documented commands actually work**

Run, exactly as written in the README:
```bash
cd protocol
uv run python scripts/codegen.py
git diff --exit-code gen/
uv run pytest -v
pnpm exec vitest run
pnpm exec tsc --noEmit
```
Expected: clean regen (no diff) and all suites green.

- [ ] **Step 3: Commit**

```bash
git add protocol/README.md
git commit -m "docs(protocol): versioning, mock usage, and parallel-dev runbook"
```

- [ ] **Step 4: Tag Phase 0 complete**

```bash
git tag phase-0-protocol
```

---

## Self-Review

**Spec coverage (§4.1 + §6):**
- "single source-of-truth schema in `protocol/`" → Task 2 (`schema/protocol.schema.json`).
- "Codegen produces Pydantic models (Python) and TypeScript types" → Tasks 4–5 + orchestrator in Task 4/6.
- "HTTP for simple request/reply (`get_status`)" → `StatusRequest`/`StatusResponse` + `GET /status` in mock (Tasks 2, 3, 7).
- "WebSocket for the streaming event channel and commands" → `agent.*` stream + `command.*` + `/ws` (Tasks 2, 3, 7).
- "Supports multiple simultaneous clients" → stateless per-connection mock server; `channel` field distinguishes origins. (Full multi-client fan-out is the real brain's concern in Phase 1; the contract supports it — `Channel` enum, per-connection sessions.)
- "each side mocks the other" → reference mock server + client (Tasks 7–8) + fixtures (Task 3).
- "contract change is one atomic commit across both sides" → committed `gen/` + drift CI (Task 6); runbook (Task 9).
- "Isolate concurrent streams with git worktrees" → documented as the handoff in Task 9 (worktree creation happens at execution time, per the brainstorm).
- Persona / safety / memory messages are intentionally **out of Phase 0** per the agreed scope ("envelope + Phase-1 core, grow later"); `RiskTier` is seeded on `agent.action` for forward-compat with the Phase-3 safety layer.

**Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N". Every code step contains complete, runnable content. The only empty file is `mock/__init__.py` (intentionally empty package marker, Task 7 Step 4).

**Type consistency:** Message `type` literals, field names (`corr`, `final`, `active_scopes`, `protocol_version`, `risk`, `halted`), enums (`Channel`, `RiskTier`, turn `status`, error `code`), and class/interface names (`CommandSubmit`, `ServerHello`, `AgentMessage`, `Error`) are identical across the schema (Task 2), fixtures (Task 3), Pydantic re-exports (Task 4), TS conformance (Task 5), mock server (Task 7), and mock client (Task 8). The Python union and TS union are both named `Message` (driven by the schema root `title`).
