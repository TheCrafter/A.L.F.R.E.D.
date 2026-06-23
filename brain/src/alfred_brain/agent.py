from __future__ import annotations

import asyncio
import logging
from typing import Callable

from alfred_protocol import (
    AgentAction, AgentMessage, AgentThought, AgentTurnComplete,
)

from .messages import dump, new_id, now_ts
from .providers.base import (
    ReasoningProvider, TextChunk, Thought, ToolCall, ToolCallRequest, TurnMessage,
)
from .tools.registry import ToolRegistry


logger = logging.getLogger(__name__)


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

    def set_provider(self, provider: ReasoningProvider) -> None:
        """Swap the reasoning provider at runtime (used by the model picker)."""
        self._provider = provider

    async def run(self, *, corr: str, text: str, publish: Callable[[dict], None]) -> None:
        def emit(model: AgentThought | AgentMessage | AgentAction | AgentTurnComplete) -> None:
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
            logger.exception("agent turn %s failed", corr)
            emit(AgentMessage(
                v=1, id=new_id(), ts=now_ts(), type="agent.message",
                corr=corr, text="My apologies, sir — I was unable to complete that request.",
                final=True,
            ))
            emit(AgentTurnComplete(
                v=1, id=new_id(), ts=now_ts(), type="agent.turn_complete",
                corr=corr, status="error",
            ))
