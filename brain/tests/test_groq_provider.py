from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from alfred_brain.providers.base import TextChunk, Thought, ToolCallRequest, ToolSpec, TurnMessage
from alfred_brain.providers.groq import GroqProvider


# --- a minimal fake of the AsyncGroq client surface the provider uses ---
class _FakeCompletions:
    def __init__(self, message):
        self._message = message
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self._message)])


class _FakeClient:
    def __init__(self, message):
        self.chat = SimpleNamespace(completions=_FakeCompletions(message))


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id, type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


async def test_text_response_yields_thought_then_final_chunk():
    msg = SimpleNamespace(content="Naturally, sir.", tool_calls=None)
    p = GroqProvider("k", "m", client=_FakeClient(msg))
    events = [ev async for ev in p.run_turn([TurnMessage(role="user", content="hi")], [], "be brief")]
    assert isinstance(events[0], Thought)
    assert events[-1] == TextChunk("Naturally, sir.", final=True)


async def test_tool_call_response_yields_requests_with_parsed_args():
    msg = SimpleNamespace(
        content=None,
        tool_calls=[_tool_call("call_1", "echo", '{"text": "ping"}')],
    )
    p = GroqProvider("k", "m", client=_FakeClient(msg))
    spec = ToolSpec(name="echo", description="echo", parameters={"type": "object"})
    events = [ev async for ev in p.run_turn([TurnMessage(role="user", content="hi")], [spec], "sys")]
    reqs = [e for e in events if isinstance(e, ToolCallRequest)]
    assert reqs == [ToolCallRequest(call_id="call_1", tool="echo", args={"text": "ping"})]


async def test_request_sends_system_and_tools():
    msg = SimpleNamespace(content="ok", tool_calls=None)
    client = _FakeClient(msg)
    p = GroqProvider("k", "mymodel", client=client)
    spec = ToolSpec(name="echo", description="Echo it.", parameters={"type": "object"})
    [ev async for ev in p.run_turn(
        [TurnMessage(role="user", content="hi")], [spec], "you are alfred")]
    call = client.chat.completions.calls[0]
    assert call["model"] == "mymodel"
    assert call["messages"][0] == {"role": "system", "content": "you are alfred"}
    assert call["tools"][0]["function"]["name"] == "echo"


async def test_round_trips_assistant_tool_call_and_tool_result():
    msg = SimpleNamespace(content="done", tool_calls=None)
    client = _FakeClient(msg)
    p = GroqProvider("k", "m", client=client)
    from alfred_brain.providers.base import ToolCall
    messages = [
        TurnMessage(role="user", content="echo hi"),
        TurnMessage(role="assistant", tool_calls=[ToolCall("call_1", "echo", {"text": "hi"})]),
        TurnMessage(role="tool", content="hi", tool_call_id="call_1", tool_name="echo"),
    ]
    [ev async for ev in p.run_turn(messages, [], "sys")]
    sent = client.chat.completions.calls[0]["messages"]
    assistant = next(m for m in sent if m["role"] == "assistant")
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert assistant["tool_calls"][0]["function"]["name"] == "echo"
    tool = next(m for m in sent if m["role"] == "tool")
    assert tool["tool_call_id"] == "call_1" and tool["content"] == "hi"


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("GROQ_API_KEY"), reason="needs a live Groq key")
async def test_groq_live_smoke():
    p = GroqProvider(os.environ["GROQ_API_KEY"], os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
    events = [ev async for ev in p.run_turn(
        [TurnMessage(role="user", content="Say hello in five words.")], [], "Be brief.")]
    assert events
