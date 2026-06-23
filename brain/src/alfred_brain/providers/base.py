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
