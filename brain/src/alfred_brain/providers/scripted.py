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
