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
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=m.content)]))
        elif m.role == "assistant":
            parts: list[types.Part] = []
            if m.content:
                parts.append(types.Part.from_text(text=m.content))
            for tc in m.tool_calls:
                parts.append(types.Part.from_function_call(name=tc.tool, args=tc.args))
            contents.append(types.Content(role="model", parts=parts))
        elif m.role == "tool":
            contents.append(types.Content(role="tool", parts=[
                types.Part.from_function_response(
                    name=m.tool_name or "", response={"result": m.content},
                )
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
