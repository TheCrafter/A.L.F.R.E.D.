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
