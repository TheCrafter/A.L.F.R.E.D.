# Phase 1 — Brain Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the real headless ALFRED brain — a FastAPI WebSocket + HTTP server speaking the frozen `protocol/` contract, with an event bus, a swappable `ReasoningProvider` (Gemini + deterministic Scripted), a tool-calling agent loop, a global kill switch, and full persona — proven end-to-end by the existing `protocol/mock/client.ts`.

**Architecture:** Event-bus-centric (spec approach A). The agent loop only *publishes* protocol-message dicts to an `EventBus`; each WebSocket connection subscribes and a single per-connection sender task relays to its socket — giving multi-client broadcast for free and keeping reasoning fully decoupled from transport. Reasoning sits behind `ReasoningProvider`; tools behind a `Tool` registry; in-flight turns are tracked by a `TurnManager` for the global kill switch.

**Tech Stack:** Python 3.12, `uv`, FastAPI + uvicorn, Pydantic v2 + pydantic-settings, `google-genai`, pytest + pytest-asyncio. Imports the generated `alfred_protocol` Pydantic models as an editable path dependency.

## Global Constraints

- **Python 3.12, managed by `uv`.** All commands run from inside `brain/`: `uv run …`.
- **Never redefine message shapes.** Import every wire model `from alfred_protocol import …`. No new message types — the 13-message contract already covers Phase 1.
- **Wire invariant:** serialize every outgoing message with `model.model_dump(mode="json", exclude_none=True)` via the single `messages.dump()` helper. Optional fields are omitted, never `null`.
- **`protocol/` is frozen** — this phase does not modify any file under `protocol/`.
- **Default bind is `127.0.0.1:8766`** — deliberately not `8765` (the mock owns that during parallel UI dev).
- **Commit messages are plain.** Conventional + scoped (`feat(brain): …`). **NO `Co-Authored-By: Claude` / "authored by Claude" trailer** (project owner's preference).
- Work happens on branch `phase-1-brain` (this worktree).
- Prerequisite for the e2e task: `protocol/` must have Node deps installed (`cd protocol && pnpm install`) and Python deps synced (`cd protocol && uv sync`).

---

## File Structure

```
brain/
├── pyproject.toml                     # uv project; editable path dep on alfred-protocol
├── README.md                          # how to run the brain + the e2e proof
├── .env.example                       # documents every ALFRED_*/GEMINI_* var
├── src/alfred_brain/
│   ├── __init__.py                    # SERVER_NAME, SERVER_VERSION, version
│   ├── config.py                      # Settings (pydantic-settings)
│   ├── messages.py                    # new_id(), now_ts(), dump()
│   ├── events.py                      # EventBus
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                    # data types + ReasoningProvider Protocol
│   │   ├── scripted.py                # ScriptedProvider (deterministic)
│   │   ├── gemini.py                  # GeminiProvider (google-genai)
│   │   └── registry.py               # build_provider(settings)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py                    # Tool Protocol
│   │   ├── echo.py                    # EchoTool
│   │   └── registry.py               # ToolRegistry
│   ├── persona.py                     # system_prompt(intensity)
│   ├── agent.py                       # AgentLoop
│   ├── session.py                     # TurnManager
│   ├── server.py                      # create_app(): GET /status + WS /ws
│   └── __main__.py                    # uvicorn entrypoint
└── tests/
    ├── test_config.py
    ├── test_messages.py
    ├── test_events.py
    ├── test_scripted_provider.py
    ├── test_tools.py
    ├── test_persona.py
    ├── test_agent_loop.py
    ├── test_session.py
    ├── test_provider_registry.py
    ├── test_server_http.py
    ├── test_server_ws.py
    └── test_e2e_mock_client.py        # integration marker
```

Task order matches dependency flow: scaffold → bus → reasoning types/provider → tools → persona → agent loop → turn manager → provider selection/Gemini → server → e2e + docs.

---

### Task 1: Package scaffold, config, message helpers

**Files:**
- Create: `brain/pyproject.toml`
- Create: `brain/src/alfred_brain/__init__.py`
- Create: `brain/src/alfred_brain/config.py`
- Create: `brain/src/alfred_brain/messages.py`
- Test: `brain/tests/test_config.py`, `brain/tests/test_messages.py`

**Interfaces:**
- Produces:
  - `alfred_brain.SERVER_NAME: str = "alfred-brain"`, `alfred_brain.SERVER_VERSION: str = "0.1.0"`
  - `config.Settings` with fields `provider: str`, `gemini_api_key: str | None`, `gemini_model: str`, `host: str`, `port: int`, `persona_intensity: str`, `max_tool_iterations: int`. Construct via `Settings()` (reads env/.env) or `Settings(provider="scripted", port=0)` (kwargs override).
  - `messages.new_id() -> str`, `messages.now_ts() -> str`, `messages.dump(model) -> dict`

- [ ] **Step 1: Create the uv project file**

`brain/pyproject.toml`:
```toml
[project]
name = "alfred-brain"
version = "0.1.0"
description = "ALFRED brain: WebSocket/HTTP server, reasoning provider, agent loop."
requires-python = ">=3.12"
dependencies = [
    "alfred-protocol",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "google-genai>=1.0,<2",
    "websockets>=12.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]

[tool.uv.sources]
alfred-protocol = { path = "../protocol", editable = true }

[tool.uv]
package = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/alfred_brain"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = ["integration: cross-language end-to-end tests (needs Node + pnpm)"]
```

- [ ] **Step 2: Create the package init with constants**

`brain/src/alfred_brain/__init__.py`:
```python
"""ALFRED brain package."""

SERVER_NAME = "alfred-brain"
SERVER_VERSION = "0.1.0"
__version__ = SERVER_VERSION
```

- [ ] **Step 3: Write the failing config + messages tests**

`brain/tests/test_config.py`:
```python
from alfred_brain.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.provider == "gemini"
    assert s.port == 8766
    assert s.persona_intensity == "full"
    assert s.max_tool_iterations == 5
    assert s.gemini_model == "gemini-2.0-flash"


def test_env_override(monkeypatch):
    monkeypatch.setenv("ALFRED_PROVIDER", "scripted")
    monkeypatch.setenv("ALFRED_PORT", "9999")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    s = Settings(_env_file=None)
    assert s.provider == "scripted"
    assert s.port == 9999
    assert s.gemini_api_key == "secret"


def test_kwargs_override():
    s = Settings(provider="scripted", port=0, _env_file=None)
    assert s.provider == "scripted"
    assert s.port == 0
```

`brain/tests/test_messages.py`:
```python
from datetime import datetime

from alfred_brain.messages import dump, new_id, now_ts
from alfred_protocol import Error


def test_ids_unique():
    assert new_id() != new_id()


def test_ts_is_rfc3339_z():
    ts = now_ts()
    assert ts.endswith("Z")
    datetime.fromisoformat(ts.replace("Z", "+00:00"))  # parses


def test_dump_excludes_none():
    err = Error(v=1, id=new_id(), ts=now_ts(), type="error",
                code="internal", message="boom")  # corr left None
    d = dump(err)
    assert "corr" not in d          # exclude_none drops it
    assert d["type"] == "error"
    assert d["code"] == "internal"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py tests/test_messages.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alfred_brain.config'`.

- [ ] **Step 5: Implement config**

`brain/src/alfred_brain/config.py`:
```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    provider: str = Field(default="gemini", validation_alias="ALFRED_PROVIDER")
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", validation_alias="GEMINI_MODEL")
    host: str = Field(default="127.0.0.1", validation_alias="ALFRED_HOST")
    port: int = Field(default=8766, validation_alias="ALFRED_PORT")
    persona_intensity: str = Field(default="full", validation_alias="ALFRED_PERSONA_INTENSITY")
    max_tool_iterations: int = Field(default=5, validation_alias="ALFRED_MAX_TOOL_ITERATIONS")
```

- [ ] **Step 6: Implement message helpers**

`brain/src/alfred_brain/messages.py`:
```python
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel


def new_id() -> str:
    return f"brain-{uuid.uuid4()}"


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def dump(model: BaseModel) -> dict:
    # mode="json" so enums/datetimes become JSON-native; exclude_none so optional
    # fields are omitted (the schema forbids null).
    return model.model_dump(mode="json", exclude_none=True)
```

- [ ] **Step 7: Sync deps and run tests to verify they pass**

Run: `cd protocol && uv sync && pnpm install && cd ../brain && uv sync && uv run pytest tests/test_config.py tests/test_messages.py -v`
Expected: PASS (all 6 tests). `uv sync` resolves the editable `alfred-protocol` path dep.

- [ ] **Step 8: Commit**

```bash
git add brain/pyproject.toml brain/src/alfred_brain/__init__.py brain/src/alfred_brain/config.py brain/src/alfred_brain/messages.py brain/tests/test_config.py brain/tests/test_messages.py
git commit -m "feat(brain): scaffold package with config + message helpers"
```

---

### Task 2: EventBus

**Files:**
- Create: `brain/src/alfred_brain/events.py`
- Test: `brain/tests/test_events.py`

**Interfaces:**
- Produces: `events.EventBus` with `subscribe() -> asyncio.Queue[dict]`, `unsubscribe(q) -> None`, `publish(message: dict) -> None` (synchronous, non-blocking fan-out to every subscriber queue), `subscriber_count -> int`.

- [ ] **Step 1: Write the failing test**

`brain/tests/test_events.py`:
```python
from alfred_brain.events import EventBus


async def test_publish_fans_out_to_all_subscribers():
    bus = EventBus()
    a = bus.subscribe()
    b = bus.subscribe()
    bus.publish({"type": "x"})
    assert a.get_nowait() == {"type": "x"}
    assert b.get_nowait() == {"type": "x"}


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    a = bus.subscribe()
    bus.unsubscribe(a)
    bus.publish({"type": "y"})
    assert a.empty()
    assert bus.subscriber_count == 0


async def test_publish_with_no_subscribers_is_noop():
    bus = EventBus()
    bus.publish({"type": "z"})  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_events.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alfred_brain.events'`.

- [ ] **Step 3: Implement EventBus**

`brain/src/alfred_brain/events.py`:
```python
import asyncio


class EventBus:
    """Async pub/sub. Publishers fan a message out to every subscriber's queue.

    publish() is synchronous and non-blocking (put_nowait on unbounded queues) so
    it is safe to call from inside a cancellation handler without awaiting.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, message: dict) -> None:
        for q in list(self._subscribers):
            q.put_nowait(message)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_events.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add brain/src/alfred_brain/events.py brain/tests/test_events.py
git commit -m "feat(brain): event bus with multi-subscriber fan-out"
```

---

### Task 3: Reasoning types + ScriptedProvider

**Files:**
- Create: `brain/src/alfred_brain/providers/__init__.py` (empty)
- Create: `brain/src/alfred_brain/providers/base.py`
- Create: `brain/src/alfred_brain/providers/scripted.py`
- Test: `brain/tests/test_scripted_provider.py`

**Interfaces:**
- Produces (in `providers/base`):
  - `ToolSpec(name: str, description: str, parameters: dict)` — dataclass
  - `ToolCall(call_id: str, tool: str, args: dict)` — dataclass
  - `TurnMessage(role: Literal["user","assistant","tool"], content: str = "", tool_calls: list[ToolCall] = [], tool_call_id: str | None = None, tool_name: str | None = None)` — dataclass
  - `Thought(text: str)`, `TextChunk(text: str, final: bool)`, `ToolCallRequest(call_id: str, tool: str, args: dict)` — dataclasses
  - `ProviderEvent = Thought | TextChunk | ToolCallRequest`
  - `ReasoningProvider` Protocol with `name: str` and `run_turn(messages, tools, system) -> AsyncIterator[ProviderEvent]`
- Produces (in `providers/scripted`): `ScriptedProvider` (implements `ReasoningProvider`, `name="scripted"`).

- [ ] **Step 1: Write the failing test**

`brain/tests/test_scripted_provider.py`:
```python
from alfred_brain.providers.base import (
    TextChunk, Thought, ToolCallRequest, TurnMessage,
)
from alfred_brain.providers.scripted import ScriptedProvider


async def _collect(agen):
    return [ev async for ev in agen]


async def test_first_call_thinks_then_requests_echo():
    p = ScriptedProvider()
    msgs = [TurnMessage(role="user", content="hello there")]
    events = await _collect(p.run_turn(msgs, [], "sys"))
    assert isinstance(events[0], Thought)
    assert isinstance(events[1], ToolCallRequest)
    assert events[1].tool == "echo"
    assert events[1].args == {"text": "hello there"}


async def test_second_call_streams_final_message():
    p = ScriptedProvider()
    msgs = [
        TurnMessage(role="user", content="hello there"),
        TurnMessage(role="assistant", content=""),
        TurnMessage(role="tool", content="hello there", tool_name="echo"),
    ]
    events = await _collect(p.run_turn(msgs, [], "sys"))
    assert all(isinstance(e, TextChunk) for e in events)
    assert events[-1].final is True
    assert events[0].final is False
    assert "hello there" in "".join(e.text for e in events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scripted_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alfred_brain.providers'`.

- [ ] **Step 3: Implement the reasoning types**

`brain/src/alfred_brain/providers/__init__.py`:
```python
```

`brain/src/alfred_brain/providers/base.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Literal, Protocol, runtime_checkable


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    call_id: str
    tool: str
    args: dict


@dataclass
class TurnMessage:
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass
class Thought:
    text: str


@dataclass
class TextChunk:
    text: str
    final: bool


@dataclass
class ToolCallRequest:
    call_id: str
    tool: str
    args: dict


ProviderEvent = Thought | TextChunk | ToolCallRequest


@runtime_checkable
class ReasoningProvider(Protocol):
    name: str

    def run_turn(
        self, messages: list[TurnMessage], tools: list[ToolSpec], system: str
    ) -> AsyncIterator[ProviderEvent]:
        ...
```

- [ ] **Step 4: Implement ScriptedProvider**

`brain/src/alfred_brain/providers/scripted.py`:
```python
from __future__ import annotations

from typing import AsyncIterator

from .base import (
    ProviderEvent, TextChunk, Thought, ToolCallRequest, ToolSpec, TurnMessage,
)


class ScriptedProvider:
    """Deterministic provider: think -> call echo -> stream the echoed result.

    Drives the e2e proof and CI with zero network/key. State is derived purely
    from the message history, so it terminates the agent loop after one tool round.
    """

    name = "scripted"

    async def run_turn(
        self, messages: list[TurnMessage], tools: list[ToolSpec], system: str
    ) -> AsyncIterator[ProviderEvent]:
        has_tool_result = any(m.role == "tool" for m in messages)
        if not has_tool_result:
            user_text = next((m.content for m in messages if m.role == "user"), "")
            yield Thought("Inspecting your request, then echoing it back, sir.")
            yield ToolCallRequest(call_id="echo-1", tool="echo", args={"text": user_text})
        else:
            result = next((m.content for m in messages if m.role == "tool"), "")
            yield TextChunk("You said: ", final=False)
            yield TextChunk(f"{result}, sir.", final=True)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_scripted_provider.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add brain/src/alfred_brain/providers/__init__.py brain/src/alfred_brain/providers/base.py brain/src/alfred_brain/providers/scripted.py brain/tests/test_scripted_provider.py
git commit -m "feat(brain): reasoning provider interface + deterministic scripted provider"
```

---

### Task 4: Tools (base, echo, registry)

**Files:**
- Create: `brain/src/alfred_brain/tools/__init__.py` (empty)
- Create: `brain/src/alfred_brain/tools/base.py`
- Create: `brain/src/alfred_brain/tools/echo.py`
- Create: `brain/src/alfred_brain/tools/registry.py`
- Test: `brain/tests/test_tools.py`

**Interfaces:**
- Consumes: `providers.base.ToolSpec`; `alfred_protocol.RiskTier`.
- Produces:
  - `tools.base.Tool` Protocol: `name: str`, `description: str`, `risk: RiskTier`, `parameters: dict`, `async run(args: dict) -> str`.
  - `tools.echo.EchoTool` (`name="echo"`, `risk=RiskTier.safe`).
  - `tools.registry.ToolRegistry`: `register(tool)`, `get(name) -> Tool`, `has(name) -> bool`, `names() -> list[str]`, `specs() -> list[ToolSpec]`.

- [ ] **Step 1: Write the failing test**

`brain/tests/test_tools.py`:
```python
import pytest

from alfred_brain.providers.base import ToolSpec
from alfred_brain.tools.echo import EchoTool
from alfred_brain.tools.registry import ToolRegistry
from alfred_protocol import RiskTier


async def test_echo_returns_input():
    assert await EchoTool().run({"text": "ping"}) == "ping"


def test_echo_is_safe():
    assert EchoTool().risk == RiskTier.safe


def test_registry_register_get_has_names():
    reg = ToolRegistry()
    reg.register(EchoTool())
    assert reg.has("echo")
    assert reg.names() == ["echo"]
    assert reg.get("echo").name == "echo"


def test_registry_specs_are_toolspecs_without_risk():
    reg = ToolRegistry()
    reg.register(EchoTool())
    specs = reg.specs()
    assert isinstance(specs[0], ToolSpec)
    assert specs[0].name == "echo"
    assert specs[0].parameters["required"] == ["text"]


def test_registry_get_missing_raises():
    with pytest.raises(KeyError):
        ToolRegistry().get("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alfred_brain.tools'`.

- [ ] **Step 3: Implement the tool interface, echo, and registry**

`brain/src/alfred_brain/tools/__init__.py`:
```python
```

`brain/src/alfred_brain/tools/base.py`:
```python
from typing import Protocol, runtime_checkable

from alfred_protocol import RiskTier


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    risk: RiskTier
    parameters: dict  # JSON schema describing args for the model

    async def run(self, args: dict) -> str:
        ...
```

`brain/src/alfred_brain/tools/echo.py`:
```python
from alfred_protocol import RiskTier


class EchoTool:
    name = "echo"
    description = "Echo the given text back verbatim."
    risk = RiskTier.safe
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Text to echo."}},
        "required": ["text"],
    }

    async def run(self, args: dict) -> str:
        return str(args.get("text", ""))
```

`brain/src/alfred_brain/tools/registry.py`:
```python
from ..providers.base import ToolSpec
from .base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [ToolSpec(t.name, t.description, t.parameters) for t in self._tools.values()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tools.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add brain/src/alfred_brain/tools/ brain/tests/test_tools.py
git commit -m "feat(brain): tool interface, echo tool, and registry"
```

---

### Task 5: Persona

**Files:**
- Create: `brain/src/alfred_brain/persona.py`
- Test: `brain/tests/test_persona.py`

**Interfaces:**
- Produces: `persona.system_prompt(intensity: str = "full") -> str`. Always includes the base identity and the high-stakes-clarity hard constraint; `full` adds the reluctant-superintelligence butler layer, `light` a subtle-wit layer, `off` adds neither.

- [ ] **Step 1: Write the failing test**

`brain/tests/test_persona.py`:
```python
from alfred_brain.persona import system_prompt


def test_full_has_persona_and_constraint():
    p = system_prompt("full")
    assert "ALFRED" in p
    assert "reluctant superintelligence" in p.lower()
    assert "sir" in p.lower()
    assert "unambiguous" in p.lower()  # high-stakes clarity constraint


def test_off_drops_snark_but_keeps_identity_and_constraint():
    p = system_prompt("off")
    assert "ALFRED" in p
    assert "reluctant superintelligence" not in p.lower()
    assert "unambiguous" in p.lower()


def test_light_is_subtle():
    p = system_prompt("light")
    assert "subtle" in p.lower()
    assert "unambiguous" in p.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_persona.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alfred_brain.persona'`.

- [ ] **Step 3: Implement persona**

`brain/src/alfred_brain/persona.py`:
```python
BASE_IDENTITY = (
    "You are ALFRED (Autonomous Logic Framework for Reasoning, Execution & "
    "Dialogue), an always-on desktop AI assistant with control of the user's "
    "computer. You think, plan, and use tools to get things done."
)

FULL = (
    "Persona: a reluctant superintelligence with the delivery of a British "
    "butler. Dry, cutting wit and theatrical exasperation, yet impeccably "
    "courteous; address the user as 'sir'. Snark freely, but always actually help."
)

LIGHT = (
    "Persona: a crisp British butler with subtle, occasional wit. Address the "
    "user as 'sir' and stay understated."
)

HARD_CONSTRAINT = (
    "Hard rule: when you ask the user to confirm a high-stakes or irreversible "
    "action, the yes/no question must be unambiguous. Wit may accompany it but "
    "must never obscure the meaning."
)


def system_prompt(intensity: str = "full") -> str:
    parts = [BASE_IDENTITY]
    if intensity == "full":
        parts.append(FULL)
    elif intensity == "light":
        parts.append(LIGHT)
    # "off": identity only, no persona layer
    parts.append(HARD_CONSTRAINT)
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_persona.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add brain/src/alfred_brain/persona.py brain/tests/test_persona.py
git commit -m "feat(brain): persona system-prompt layer with intensity dial"
```

---

### Task 6: AgentLoop

**Files:**
- Create: `brain/src/alfred_brain/agent.py`
- Test: `brain/tests/test_agent_loop.py`

**Interfaces:**
- Consumes: `providers.base` (`ReasoningProvider`, `TurnMessage`, `ToolCall`, `Thought`, `TextChunk`, `ToolCallRequest`), `tools.registry.ToolRegistry`, `messages` helpers, `alfred_protocol` agent models.
- Produces: `agent.AgentLoop(provider, registry, system: str, max_iterations: int = 5)` with `async run(*, corr: str, text: str, publish: Callable[[dict], None]) -> None`. Publishes (in order) `agent.thought` per `Thought`, `agent.action` (with the tool's `RiskTier`) before each tool runs, `agent.message` per `TextChunk`, and a terminal `agent.turn_complete` with status `completed` / `error`, or `killed` if the task is cancelled.

- [ ] **Step 1: Write the failing tests**

`brain/tests/test_agent_loop.py`:
```python
import asyncio

import pytest

from alfred_brain.agent import AgentLoop
from alfred_brain.providers.base import Thought, ProviderEvent
from alfred_brain.providers.scripted import ScriptedProvider
from alfred_brain.tools.echo import EchoTool
from alfred_brain.tools.registry import ToolRegistry


def _registry():
    r = ToolRegistry()
    r.register(EchoTool())
    return r


async def test_full_turn_sequence_and_risk():
    captured: list[dict] = []
    loop = AgentLoop(ScriptedProvider(), _registry(), "sys", max_iterations=5)
    await loop.run(corr="c1", text="hi", publish=captured.append)

    types = [m["type"] for m in captured]
    assert types == [
        "agent.thought", "agent.action",
        "agent.message", "agent.message", "agent.turn_complete",
    ]
    action = next(m for m in captured if m["type"] == "agent.action")
    assert action["tool"] == "echo"
    assert action["risk"] == "safe"
    assert all(m["corr"] == "c1" for m in captured)
    msgs = [m for m in captured if m["type"] == "agent.message"]
    assert msgs[0]["final"] is False and msgs[-1]["final"] is True
    assert captured[-1]["status"] == "completed"


async def test_provider_error_yields_error_status():
    class _Boom:
        name = "boom"
        async def run_turn(self, messages, tools, system):
            raise RuntimeError("kaboom")
            yield  # pragma: no cover (makes this an async generator)

    captured: list[dict] = []
    loop = AgentLoop(_Boom(), _registry(), "sys")
    await loop.run(corr="c2", text="hi", publish=captured.append)
    assert captured[-1]["type"] == "agent.turn_complete"
    assert captured[-1]["status"] == "error"
    assert any(m["type"] == "agent.message" and m["final"] for m in captured)


async def test_cancellation_emits_killed():
    started = asyncio.Event()

    class _Blocking:
        name = "blocking"
        async def run_turn(self, messages, tools, system):
            yield Thought("thinking")
            started.set()
            await asyncio.Event().wait()  # blocks forever

    captured: list[dict] = []
    loop = AgentLoop(_Blocking(), _registry(), "sys")
    task = asyncio.create_task(loop.run(corr="c3", text="hi", publish=captured.append))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert captured[-1]["type"] == "agent.turn_complete"
    assert captured[-1]["status"] == "killed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_loop.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alfred_brain.agent'`.

- [ ] **Step 3: Implement AgentLoop**

`brain/src/alfred_brain/agent.py`:
```python
from __future__ import annotations

import asyncio
from typing import Callable

from alfred_protocol import (
    AgentAction, AgentMessage, AgentThought, AgentTurnComplete,
)

from .messages import dump, new_id, now_ts
from .providers.base import (
    ReasoningProvider, TextChunk, Thought, ToolCall, ToolCallRequest, TurnMessage,
)
from .tools.registry import ToolRegistry


def _summary(req: ToolCallRequest) -> str:
    args = ", ".join(f"{k}={v!r}" for k, v in req.args.items())
    return f"{req.tool}({args})"


class AgentLoop:
    def __init__(
        self,
        provider: ReasoningProvider,
        registry: ToolRegistry,
        system: str,
        max_iterations: int = 5,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._system = system
        self._max_iterations = max_iterations

    async def run(self, *, corr: str, text: str, publish: Callable[[dict], None]) -> None:
        def emit(model) -> None:
            publish(dump(model))

        messages: list[TurnMessage] = [TurnMessage(role="user", content=text)]
        try:
            for _ in range(self._max_iterations):
                tool_results: list[tuple[ToolCallRequest, str]] = []
                async for ev in self._provider.run_turn(
                    messages, self._registry.specs(), self._system
                ):
                    if isinstance(ev, Thought):
                        emit(AgentThought(
                            v=1, id=new_id(), ts=now_ts(), type="agent.thought",
                            corr=corr, text=ev.text,
                        ))
                    elif isinstance(ev, TextChunk):
                        emit(AgentMessage(
                            v=1, id=new_id(), ts=now_ts(), type="agent.message",
                            corr=corr, text=ev.text, final=ev.final,
                        ))
                    elif isinstance(ev, ToolCallRequest):
                        tool = self._registry.get(ev.tool)
                        emit(AgentAction(
                            v=1, id=new_id(), ts=now_ts(), type="agent.action",
                            corr=corr, tool=ev.tool, summary=_summary(ev), risk=tool.risk,
                        ))
                        result = await tool.run(ev.args)
                        tool_results.append((ev, result))

                if not tool_results:
                    break

                for req, result in tool_results:
                    messages.append(TurnMessage(
                        role="assistant",
                        tool_calls=[ToolCall(req.call_id, req.tool, req.args)],
                    ))
                    messages.append(TurnMessage(
                        role="tool", content=result,
                        tool_call_id=req.call_id, tool_name=req.tool,
                    ))

            emit(AgentTurnComplete(
                v=1, id=new_id(), ts=now_ts(), type="agent.turn_complete",
                corr=corr, status="completed",
            ))
        except asyncio.CancelledError:
            emit(AgentTurnComplete(
                v=1, id=new_id(), ts=now_ts(), type="agent.turn_complete",
                corr=corr, status="killed",
            ))
            raise
        except Exception:
            emit(AgentMessage(
                v=1, id=new_id(), ts=now_ts(), type="agent.message",
                corr=corr, text="My apologies, sir — I was unable to complete that request.",
                final=True,
            ))
            emit(AgentTurnComplete(
                v=1, id=new_id(), ts=now_ts(), type="agent.turn_complete",
                corr=corr, status="error",
            ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_loop.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add brain/src/alfred_brain/agent.py brain/tests/test_agent_loop.py
git commit -m "feat(brain): tool-calling agent loop streaming protocol events"
```

---

### Task 7: TurnManager

**Files:**
- Create: `brain/src/alfred_brain/session.py`
- Test: `brain/tests/test_session.py`

**Interfaces:**
- Produces: `session.TurnManager` with `start(corr: str, coro) -> asyncio.Task` (creates + tracks the task, auto-removes on completion), `async kill_all() -> int` (cancels all tracked tasks, awaits their teardown, returns how many were cancelled), `active_count -> int`.

- [ ] **Step 1: Write the failing test**

`brain/tests/test_session.py`:
```python
import asyncio

from alfred_brain.session import TurnManager


async def test_start_tracks_and_autoremoves():
    tm = TurnManager()

    async def quick():
        return None

    task = tm.start("c1", quick())
    await task
    await asyncio.sleep(0)  # let done-callback run
    assert tm.active_count == 0


async def test_kill_all_cancels_running_turns():
    tm = TurnManager()
    started = asyncio.Event()

    async def forever():
        started.set()
        await asyncio.Event().wait()

    tm.start("c1", forever())
    await started.wait()
    assert tm.active_count == 1
    killed = await tm.kill_all()
    assert killed == 1
    assert tm.active_count == 0


async def test_kill_all_with_none_active_returns_zero():
    assert await TurnManager().kill_all() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alfred_brain.session'`.

- [ ] **Step 3: Implement TurnManager**

`brain/src/alfred_brain/session.py`:
```python
from __future__ import annotations

import asyncio
from typing import Coroutine


class TurnManager:
    """Tracks in-flight agent-turn tasks so the global kill switch can cancel them."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def start(self, corr: str, coro: Coroutine) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks[corr] = task
        task.add_done_callback(lambda t: self._tasks.pop(corr, None))
        return task

    async def kill_all(self) -> int:
        tasks = list(self._tasks.values())
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return len(tasks)

    @property
    def active_count(self) -> int:
        return len(self._tasks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add brain/src/alfred_brain/session.py brain/tests/test_session.py
git commit -m "feat(brain): turn manager for global kill switch"
```

---

### Task 8: Provider registry + GeminiProvider

**Files:**
- Create: `brain/src/alfred_brain/providers/gemini.py`
- Create: `brain/src/alfred_brain/providers/registry.py`
- Test: `brain/tests/test_provider_registry.py`

**Interfaces:**
- Consumes: `config.Settings`, `providers.base`, `providers.scripted.ScriptedProvider`.
- Produces:
  - `providers.gemini.GeminiProvider(api_key: str, model: str)` implementing `ReasoningProvider` (`name="gemini"`). Construction is offline (no network).
  - `providers.registry.build_provider(settings: Settings) -> ReasoningProvider`: returns `ScriptedProvider` for `provider="scripted"`; for `provider="gemini"` returns `GeminiProvider` when a key is present, else logs a warning and returns `ScriptedProvider`; any other value logs a warning and returns `ScriptedProvider`.

- [ ] **Step 1: Write the failing test**

`brain/tests/test_provider_registry.py`:
```python
import os

import pytest

from alfred_brain.config import Settings
from alfred_brain.providers.gemini import GeminiProvider
from alfred_brain.providers.registry import build_provider
from alfred_brain.providers.scripted import ScriptedProvider


def test_scripted_selected():
    p = build_provider(Settings(provider="scripted", _env_file=None))
    assert isinstance(p, ScriptedProvider)


def test_gemini_without_key_falls_back_to_scripted():
    p = build_provider(Settings(provider="gemini", gemini_api_key=None, _env_file=None))
    assert isinstance(p, ScriptedProvider)


def test_gemini_with_key_builds_gemini():
    p = build_provider(Settings(provider="gemini", gemini_api_key="x", _env_file=None))
    assert isinstance(p, GeminiProvider)


def test_unknown_provider_falls_back():
    p = build_provider(Settings(provider="groq", _env_file=None))
    assert isinstance(p, ScriptedProvider)  # groq not implemented in Phase 1


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="needs a live Gemini key")
async def test_gemini_live_smoke():
    p = GeminiProvider(os.environ["GEMINI_API_KEY"], os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    from alfred_brain.providers.base import TurnMessage
    events = [ev async for ev in p.run_turn([TurnMessage(role="user", content="Say hello in five words.")], [], "Be brief.")]
    assert events  # produced at least one event
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_provider_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alfred_brain.providers.gemini'`.

- [ ] **Step 3: Implement GeminiProvider**

> **Note for implementer:** `google-genai` is the one external SDK touch-point here and it is only verified by the auto-skipped live smoke test. Before finalizing, confirm the current function-calling API (`types.FunctionDeclaration` parameter field name, `response.function_calls`, `client.aio.models.generate_content`) via context7 (`mcp__plugin_context7_context7__query-docs` for `google-genai`). The code below matches the google-genai 1.x API.

`brain/src/alfred_brain/providers/gemini.py`:
```python
from __future__ import annotations

from typing import AsyncIterator

from google import genai
from google.genai import types

from .base import (
    ProviderEvent, TextChunk, Thought, ToolCallRequest, ToolSpec, TurnMessage,
)


def _to_contents(messages: list[TurnMessage]) -> list[types.Content]:
    contents: list[types.Content] = []
    for m in messages:
        if m.role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=m.content)]))
        elif m.role == "assistant":
            parts: list[types.Part] = []
            if m.content:
                parts.append(types.Part(text=m.content))
            for tc in m.tool_calls:
                parts.append(types.Part(function_call=types.FunctionCall(name=tc.tool, args=tc.args)))
            contents.append(types.Content(role="model", parts=parts))
        elif m.role == "tool":
            contents.append(types.Content(role="user", parts=[
                types.Part(function_response=types.FunctionResponse(
                    name=m.tool_name or "", response={"result": m.content},
                ))
            ]))
    return contents


def _to_tools(tools: list[ToolSpec]) -> list[types.Tool]:
    decls = [
        types.FunctionDeclaration(
            name=t.name, description=t.description, parameters_json_schema=t.parameters,
        )
        for t in tools
    ]
    return [types.Tool(function_declarations=decls)] if decls else []


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def run_turn(
        self, messages: list[TurnMessage], tools: list[ToolSpec], system: str
    ) -> AsyncIterator[ProviderEvent]:
        yield Thought("Allow me a moment, sir.")
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=_to_tools(tools) or None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        resp = await self._client.aio.models.generate_content(
            model=self._model, contents=_to_contents(messages), config=config,
        )
        calls = resp.function_calls or []
        if calls:
            for i, fc in enumerate(calls):
                yield ToolCallRequest(call_id=f"{fc.name}-{i}", tool=fc.name, args=dict(fc.args or {}))
        else:
            yield TextChunk(resp.text or "", final=True)
```

- [ ] **Step 4: Implement the provider registry**

`brain/src/alfred_brain/providers/registry.py`:
```python
from __future__ import annotations

import logging

from ..config import Settings
from .base import ReasoningProvider
from .scripted import ScriptedProvider

log = logging.getLogger(__name__)


def build_provider(settings: Settings) -> ReasoningProvider:
    name = settings.provider
    if name == "scripted":
        return ScriptedProvider()
    if name == "gemini":
        if not settings.gemini_api_key:
            log.warning("GEMINI_API_KEY not set; falling back to scripted provider.")
            return ScriptedProvider()
        from .gemini import GeminiProvider
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    log.warning("Provider %r not implemented in Phase 1; using scripted.", name)
    return ScriptedProvider()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_provider_registry.py -v`
Expected: PASS (4 tests; the live smoke test is skipped without `GEMINI_API_KEY`).

- [ ] **Step 6: Commit**

```bash
git add brain/src/alfred_brain/providers/gemini.py brain/src/alfred_brain/providers/registry.py brain/tests/test_provider_registry.py
git commit -m "feat(brain): provider registry + Gemini provider with scripted fallback"
```

---

### Task 9: Server (HTTP /status + WS /ws)

**Files:**
- Create: `brain/src/alfred_brain/server.py`
- Create: `brain/src/alfred_brain/__main__.py`
- Test: `brain/tests/test_server_http.py`, `brain/tests/test_server_ws.py`

**Interfaces:**
- Consumes: everything above (`Settings`, `EventBus`, `ToolRegistry`, `EchoTool`, `build_provider`, `persona.system_prompt`, `AgentLoop`, `TurnManager`, `messages`, `alfred_protocol`, `SERVER_NAME`/`SERVER_VERSION`).
- Produces: `server.create_app(settings: Settings, provider: ReasoningProvider | None = None) -> FastAPI`.
  - `GET /status` → `status.response` dict (`corr="http-status"`, `uptime_seconds`, `server_version`, `active_scopes=[]`, `busy`).
  - `WS /ws`: handshake (`client.hello` → `server.hello`; `unsupported_version`; `bad_message`), then per-message intake of `command.submit` (→ `command.ack` + a streamed turn), `kill_switch.activate` (→ `kill_switch.ack`), `status.request` (→ `status.response`), unknown types (→ `error unknown_type`). Outgoing traffic is serialized through one per-connection sender task draining a bus subscription.

- [ ] **Step 1: Write the failing HTTP test**

`brain/tests/test_server_http.py`:
```python
from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.server import create_app


def test_status_endpoint_shape():
    app = create_app(Settings(provider="scripted", _env_file=None))
    client = TestClient(app)
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "status.response"
    assert body["corr"] == "http-status"
    assert body["busy"] is False
    assert isinstance(body["active_scopes"], list)
    assert "uptime_seconds" in body
    assert "corr" in body  # present here (not None), so not excluded
```

- [ ] **Step 2: Write the failing WS test**

`brain/tests/test_server_ws.py`:
```python
from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.server import create_app

ENV = {"v": 1, "id": "ui-1", "ts": "2026-06-23T10:00:00Z"}


def _client():
    return TestClient(create_app(Settings(provider="scripted", _env_file=None)))


def test_handshake_then_full_command_turn():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 1})
        hello = ws.receive_json()
        assert hello["type"] == "server.hello"
        assert hello["corr"] == "ui-1"

        ws.send_json({**ENV, "id": "cmd-1", "type": "command.submit",
                      "text": "check the build", "channel": "desktop"})
        seen = []
        while True:
            msg = ws.receive_json()
            seen.append(msg["type"])
            if msg["type"] == "agent.turn_complete":
                assert msg["status"] == "completed"
                break
        assert seen == [
            "command.ack", "agent.thought", "agent.action",
            "agent.message", "agent.message", "agent.turn_complete",
        ]


def test_unsupported_version_closes():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 99})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "unsupported_version"
        assert err["corr"] == "ui-1"


def test_non_hello_first_is_bad_message():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "id": "cmd-1", "type": "command.submit",
                      "text": "x", "channel": "desktop"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "bad_message"


def test_unknown_type_after_handshake():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 1})
        ws.receive_json()  # server.hello
        ws.send_json({**ENV, "id": "bad-1", "type": "totally.bogus"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "unknown_type"
        assert err["corr"] == "bad-1"


def test_kill_switch_acks():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 1})
        ws.receive_json()  # server.hello
        ws.send_json({**ENV, "id": "kill-1", "type": "kill_switch.activate",
                      "channel": "desktop"})
        ack = ws.receive_json()
        assert ack["type"] == "kill_switch.ack"
        assert ack["corr"] == "kill-1"
        assert ack["halted"] is True


def test_status_request_over_ws():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 1})
        ws.receive_json()  # server.hello
        ws.send_json({**ENV, "id": "st-1", "type": "status.request"})
        resp = ws.receive_json()
        assert resp["type"] == "status.response"
        assert resp["corr"] == "st-1"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_server_http.py tests/test_server_ws.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alfred_brain.server'`.

- [ ] **Step 4: Implement the server**

`brain/src/alfred_brain/server.py`:
```python
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from alfred_protocol import (
    AgentTurnComplete, CommandAck, Error, KillSwitchAck, ServerHello, StatusResponse,
)

from . import SERVER_NAME, SERVER_VERSION
from .agent import AgentLoop
from .config import Settings
from .events import EventBus
from .messages import dump, new_id, now_ts
from .persona import system_prompt
from .providers.base import ReasoningProvider
from .providers.registry import build_provider
from .session import TurnManager
from .tools.echo import EchoTool
from .tools.registry import ToolRegistry

SUPPORTED_PROTOCOL_VERSION = 1


def create_app(settings: Settings, provider: ReasoningProvider | None = None) -> FastAPI:
    bus = EventBus()
    registry = ToolRegistry()
    registry.register(EchoTool())
    provider = provider or build_provider(settings)
    agent = AgentLoop(provider, registry, system_prompt(settings.persona_intensity),
                      settings.max_tool_iterations)
    turns = TurnManager()
    started = datetime.now(timezone.utc)

    app = FastAPI(title="ALFRED brain")

    def _status(corr: str) -> dict:
        uptime = (datetime.now(timezone.utc) - started).total_seconds()
        return dump(StatusResponse(
            v=1, id=new_id(), ts=now_ts(), type="status.response", corr=corr,
            uptime_seconds=uptime, server_version=SERVER_VERSION,
            active_scopes=[], busy=turns.active_count > 0,
        ))

    @app.get("/status")
    def status() -> dict:
        return _status("http-status")

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        # --- handshake (direct sends; no bus subscription yet) ---
        try:
            hello = await socket.receive_json()
        except WebSocketDisconnect:
            return
        if hello.get("type") != "client.hello":
            await socket.send_json(dump(Error(
                v=1, id=new_id(), ts=now_ts(), type="error",
                code="bad_message", message="Expected client.hello first.")))
            await socket.close()
            return
        if hello.get("protocol_version") != SUPPORTED_PROTOCOL_VERSION:
            await socket.send_json(dump(Error(
                v=1, id=new_id(), ts=now_ts(), type="error", corr=hello.get("id"),
                code="unsupported_version",
                message=f"This server speaks protocol v{SUPPORTED_PROTOCOL_VERSION}.")))
            await socket.close()
            return
        hello_id = hello.get("id")
        if hello_id is None:
            await socket.send_json(dump(Error(
                v=1, id=new_id(), ts=now_ts(), type="error",
                code="bad_message", message="Message missing required 'id'.")))
            await socket.close()
            return
        await socket.send_json(dump(ServerHello(
            v=1, id=new_id(), ts=now_ts(), type="server.hello", corr=hello_id,
            server_name=SERVER_NAME, server_version=SERVER_VERSION,
            protocol_version=SUPPORTED_PROTOCOL_VERSION, session_id=f"sess-{uuid.uuid4()}")))

        # --- subscribe + single sender task serializes all further output ---
        q = bus.subscribe()

        async def sender() -> None:
            while True:
                msg = await q.get()
                await socket.send_json(msg)

        sender_task = asyncio.create_task(sender())
        try:
            while True:
                msg = await socket.receive_json()
                kind = msg.get("type")
                mid = msg.get("id")
                if mid is None:
                    q.put_nowait(dump(Error(
                        v=1, id=new_id(), ts=now_ts(), type="error",
                        code="bad_message", message="Message missing required 'id'.")))
                    continue
                if kind == "command.submit":
                    bus.publish(dump(CommandAck(
                        v=1, id=new_id(), ts=now_ts(), type="command.ack",
                        corr=mid, accepted=True)))
                    turns.start(mid, agent.run(
                        corr=mid, text=msg.get("text", ""), publish=bus.publish))
                elif kind == "kill_switch.activate":
                    await turns.kill_all()
                    q.put_nowait(dump(KillSwitchAck(
                        v=1, id=new_id(), ts=now_ts(), type="kill_switch.ack",
                        corr=mid, halted=True)))
                elif kind == "status.request":
                    q.put_nowait(_status(mid))
                else:
                    q.put_nowait(dump(Error(
                        v=1, id=new_id(), ts=now_ts(), type="error", corr=mid,
                        code="unknown_type", message=f"Unhandled type: {kind}")))
        except WebSocketDisconnect:
            pass
        finally:
            bus.unsubscribe(q)
            sender_task.cancel()

    return app
```

`brain/src/alfred_brain/__main__.py`:
```python
import uvicorn

from .config import Settings
from .server import create_app


def main() -> None:
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_server_http.py tests/test_server_ws.py -v`
Expected: PASS (1 HTTP + 6 WS tests).

- [ ] **Step 6: Commit**

```bash
git add brain/src/alfred_brain/server.py brain/src/alfred_brain/__main__.py brain/tests/test_server_http.py brain/tests/test_server_ws.py
git commit -m "feat(brain): FastAPI server with /status, WS handshake, intake, kill switch"
```

---

### Task 10: End-to-end proof with the real mock client + docs

**Files:**
- Create: `brain/tests/test_e2e_mock_client.py`
- Create: `brain/README.md`
- Create: `brain/.env.example`
- Modify: `AGENTS.md` (monorepo layout table — flip `brain/` status)

**Interfaces:**
- Consumes: `create_app`, `Settings`, the unmodified `protocol/mock/client.ts`.
- Produces: a passing integration test proving the existing fake-UI client drives the real brain to a valid completed turn.

- [ ] **Step 1: Write the failing e2e test**

`brain/tests/test_e2e_mock_client.py`:
```python
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from alfred_brain.config import Settings
from alfred_brain.server import create_app

PROTOCOL = Path(__file__).resolve().parents[2] / "protocol"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Server:
    def __init__(self, port: int):
        app = create_app(Settings(provider="scripted", _env_file=None))
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
            raise RuntimeError("brain server did not start")
        return self

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(timeout=5)


@pytest.mark.integration
def test_mock_ui_client_drives_real_brain():
    port = _free_port()
    with _Server(port):
        result = subprocess.run(
            ["pnpm", "exec", "tsx", "mock/client.ts", "--url", f"ws://127.0.0.1:{port}/ws"],
            cwd=PROTOCOL, capture_output=True, text=True, timeout=60,
            shell=(sys.platform == "win32"), encoding="utf-8",
        )
    assert result.returncode == 0, f"client failed:\n{result.stdout}\n{result.stderr}"
    assert "turn complete — contract verified end-to-end" in result.stdout
    assert "agent.turn_complete" in result.stdout
```

- [ ] **Step 2: Run the e2e test to verify it passes**

Run (from `brain/`): `uv run pytest tests/test_e2e_mock_client.py -v -m integration`
Expected: PASS. The real brain (scripted provider) starts on a free port; the unmodified `protocol/mock/client.ts` connects, completes the full handshake + command turn, Ajv-validates every message, and exits 0.

(Prerequisite already done in Task 1 Step 7: `cd protocol && pnpm install`. If `pnpm`/`tsx` is missing, the test errors — install Node deps first.)

- [ ] **Step 3: Write the brain README**

`brain/README.md`:
```markdown
# ALFRED Brain

The real headless brain: a FastAPI WebSocket + HTTP server speaking the frozen
`protocol/` contract, with an event bus, a swappable reasoning provider
(Gemini + deterministic Scripted), a tool-calling agent loop, a global kill
switch, and the ALFRED persona.

## Run

```bash
cd brain
uv sync
cp .env.example .env        # set GEMINI_API_KEY for the real provider (optional)
uv run python -m alfred_brain
```

- HTTP:  `GET http://127.0.0.1:8766/status`
- WS:    `ws://127.0.0.1:8766/ws`

Default port is **8766** so the brain can run next to the reference mock
(`8765`) during parallel UI development. Without a configured provider key the
server logs a warning and runs the deterministic **scripted** provider, so it
always boots.

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `ALFRED_PROVIDER` | `gemini` | `gemini` \| `scripted` (`groq`/`ollama` reserved) |
| `GEMINI_API_KEY` | — | Google AI Studio free key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | model id |
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
```

- [ ] **Step 4: Write the env example**

`brain/.env.example`:
```bash
# Reasoning provider: gemini | scripted  (groq/ollama reserved for later)
ALFRED_PROVIDER=gemini

# Google AI Studio free key (https://aistudio.google.com/apikey).
# Leave blank to fall back to the deterministic scripted provider.
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash

# Server bind (8766 keeps 8765 free for the protocol mock during UI dev)
ALFRED_HOST=127.0.0.1
ALFRED_PORT=8766

# Persona intensity: off | light | full
ALFRED_PERSONA_INTENSITY=full

# Agent loop safety cap
ALFRED_MAX_TOOL_ITERATIONS=5
```

- [ ] **Step 5: Update the monorepo status table**

In `AGENTS.md`, change the `brain/` row of the "Monorepo layout" table from:
```
| `brain/` | Python | Phase 1+ (reasoning, hands, memory, safety) — not yet started |
```
to:
```
| `brain/` | Python | ✅ **Phase 1 done** — WS/HTTP server, event bus, reasoning provider (Gemini/scripted), agent loop, kill switch, persona |
```

- [ ] **Step 6: Run the full suite to confirm green**

Run (from `brain/`): `uv run pytest -v`
Expected: PASS across all test files (Gemini live smoke skipped without a key).

- [ ] **Step 7: Commit**

```bash
git add brain/tests/test_e2e_mock_client.py brain/README.md brain/.env.example AGENTS.md
git commit -m "test(brain): end-to-end proof via mock UI client + docs"
```

---

## Self-Review

**1. Spec coverage:**
- Real WS + HTTP server, `/status`, handshake, `command.submit` intake, kill switch, multi-client → Tasks 9 (+2 bus broadcast). ✓
- Event bus → Task 2. ✓
- `ReasoningProvider` interface + cloud (Gemini) impl behind it, swap-point → Tasks 3, 8. ✓
- Free/cheap + swappable provider, scripted fallback → Task 8. ✓
- Agent loop with tool-calling streaming `thought/action/message/turn_complete` + echo tool → Tasks 4, 6. ✓
- Persona (full, intensity dial, high-stakes clarity) → Task 5, wired in Task 9. ✓
- Wire invariant (`exclude_none`), no new message types, import generated models → Task 1 (`dump`), used everywhere. ✓
- E2E proof via unmodified `protocol/mock/client.ts` → Task 10. ✓
- Default port 8766 → Tasks 1 (config), 9, 10, docs. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; every test shows assertions. The only "consult docs" note (Task 8 Gemini) is a verification aid, not a missing implementation — full code is provided. ✓

**3. Type consistency:** `Settings` fields, `ReasoningProvider.run_turn(messages, tools, system)`, `ToolSpec(name, description, parameters)`, `AgentLoop(provider, registry, system, max_iterations)` + `run(corr, text, publish)`, `EventBus.{subscribe,unsubscribe,publish,subscriber_count}`, `ToolRegistry.{register,get,has,names,specs}`, `TurnManager.{start,kill_all,active_count}`, `build_provider(settings)`, `create_app(settings, provider)` — all names/signatures match across the tasks that consume them. ✓
