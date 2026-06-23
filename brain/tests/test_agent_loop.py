import asyncio

import pytest

from alfred_brain.agent import AgentLoop
from alfred_brain.providers.base import Thought
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


async def test_provider_error_is_logged(caplog):
    class _Boom:
        name = "boom"
        async def run_turn(self, messages, tools, system):
            raise RuntimeError("kaboom")
            yield  # pragma: no cover (makes this an async generator)

    captured: list[dict] = []
    loop = AgentLoop(_Boom(), _registry(), "sys")
    with caplog.at_level("ERROR"):
        await loop.run(corr="c-log", text="hi", publish=captured.append)

    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert errors, "a swallowed turn failure must be logged server-side"
    rec = errors[-1]
    assert "c-log" in rec.getMessage()
    assert rec.exc_info and rec.exc_info[1].args == ("kaboom",)


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
