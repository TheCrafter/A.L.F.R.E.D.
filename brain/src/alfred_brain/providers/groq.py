from __future__ import annotations

import json
from typing import Any, AsyncIterator

from groq import AsyncGroq

from .base import (
    ProviderEvent, TextChunk, Thought, ToolCallRequest, ToolSpec, TurnMessage,
)


def _to_messages(system: str, messages: list[TurnMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "user":
            out.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": m.content or None}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.call_id,
                        "type": "function",
                        "function": {"name": tc.tool, "arguments": json.dumps(tc.args)},
                    }
                    for tc in m.tool_calls
                ]
            out.append(msg)
        elif m.role == "tool":
            out.append({
                "role": "tool",
                "tool_call_id": m.tool_call_id or "",
                "content": m.content,
            })
    return out


def _to_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name, "description": t.description, "parameters": t.parameters,
            },
        }
        for t in tools
    ]


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, client: AsyncGroq | None = None) -> None:
        self._client = client or AsyncGroq(api_key=api_key)
        self._model = model

    async def _create(self, **kwargs):
        # Groq's Llama models intermittently emit a malformed <function=...> tool
        # call that the API rejects with HTTP 400 `tool_use_failed`. Retrying
        # re-runs the generation, which almost always yields a valid structured
        # call. Only this specific error is retried; anything else propagates.
        # (asyncio.CancelledError subclasses BaseException, so the kill switch
        # is never swallowed here.)
        attempts = 5
        for i in range(attempts):
            try:
                return await self._client.chat.completions.create(**kwargs)
            except Exception as exc:
                if "tool_use_failed" in str(exc) and i < attempts - 1:
                    continue
                raise

    async def run_turn(
        self, messages: list[TurnMessage], tools: list[ToolSpec], system: str
    ) -> AsyncIterator[ProviderEvent]:
        yield Thought("One moment, sir.")
        tool_defs = _to_tools(tools)
        resp = await self._create(
            model=self._model,
            messages=_to_messages(system, messages),
            **({"tools": tool_defs, "tool_choice": "auto"} if tool_defs else {}),
        )
        message = resp.choices[0].message
        calls = message.tool_calls or []
        if calls:
            for tc in calls:
                args = json.loads(tc.function.arguments or "{}")
                yield ToolCallRequest(call_id=tc.id, tool=tc.function.name, args=args)
        else:
            yield TextChunk(message.content or "", final=True)
