from __future__ import annotations

import asyncio
import logging
from typing import Callable

from alfred_protocol import (
    AgentAction, AgentMessage, AgentThought, AgentTurnComplete, Error,
)

from .memory import Memory
from .memory.working import WorkingMemory
from .memory.extraction import Extractor
from .messages import dump, new_id, now_ts
from .providers.base import (
    ReasoningProvider, TextChunk, Thought, ToolCall, ToolCallRequest, TurnMessage,
)
from .tools.registry import ToolRegistry


logger = logging.getLogger(__name__)


MEMORY_GUIDANCE = (
    "# Memory\n"
    "You have a persistent long-term memory; durable facts are saved automatically "
    "after the conversation — you do not need to call a tool to save them. Use the "
    "`remember` tool only when the user explicitly asks you to remember something. "
    "Relevant memories may be listed below. A memory marked 'unconfirmed' is not yet "
    "verified — treat it cautiously and confirm a high-stakes one with the user "
    "before relying on it."
)


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
        memory: "Memory | None" = None,
        recall_top_k: int = 5,
        working: "WorkingMemory | None" = None,
        extractor: "Extractor | None" = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._system = system
        self._max_iterations = max_iterations
        self._memory = memory
        self._recall_top_k = recall_top_k
        self._working = working
        self._extractor = extractor
        self._extract_tasks: set[asyncio.Task] = set()

    def set_provider(self, provider: ReasoningProvider) -> None:
        """Swap the reasoning provider at runtime (used by the model picker)."""
        self._provider = provider

    def set_system(self, system: str) -> None:
        self._system = system

    def set_max_iterations(self, n: int) -> None:
        self._max_iterations = n

    def set_recall_top_k(self, n: int) -> None:
        self._recall_top_k = n

    async def drain_extractions(self) -> None:
        """Await any in-flight fire-and-forget extraction tasks (used on shutdown)."""
        tasks = list(self._extract_tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, *, corr: str, text: str, publish: Callable[[dict], None]) -> None:
        def emit(model: AgentThought | AgentMessage | AgentAction | AgentTurnComplete) -> None:
            publish(dump(model))

        messages: list[TurnMessage] = []
        if self._working is not None:
            messages.extend(self._working.context())
        messages.append(TurnMessage(role="user", content=text))

        system = self._system
        if self._memory is not None:
            block = MEMORY_GUIDANCE
            hits = self._memory.recall(text, k=self._recall_top_k)
            if hits:
                lines = []
                for h in hits:
                    label = f"{h.type}, unconfirmed" if h.status == "provisional" else h.type
                    lines.append(f"- ({label}) {h.text}")
                block += "\n\nRelevant memories:\n" + "\n".join(lines)
            system = f"{self._system}\n\n{block}"

        assistant_parts: list[str] = []
        try:
            for _ in range(self._max_iterations):
                tool_results: list[tuple[ToolCallRequest, str]] = []
                async for ev in self._provider.run_turn(
                    messages, self._registry.specs(), system
                ):
                    if isinstance(ev, Thought):
                        emit(AgentThought(
                            v=1, id=new_id(), ts=now_ts(), type="agent.thought",
                            corr=corr, text=ev.text,
                        ))
                    elif isinstance(ev, TextChunk):
                        assistant_parts.append(ev.text)
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

            if self._working is not None:
                self._working.append("user", text)
                reply = "".join(assistant_parts)
                if reply:
                    self._working.append("assistant", reply)
                if self._extractor is not None:
                    batch = self._working.take_batch()
                    if batch:
                        task = asyncio.create_task(self._extractor.extract(batch))
                        self._extract_tasks.add(task)
                        task.add_done_callback(self._extract_tasks.discard)

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
        except Exception as exc:
            logger.exception("agent turn %s failed", corr)
            # Surface the real failure (scoped to the turn) so the UI can show it
            # alongside the persona apology, instead of an opaque dead end.
            publish(dump(Error(
                v=1, id=new_id(), ts=now_ts(), type="error",
                corr=corr, code="internal", message=f"{type(exc).__name__}: {exc}"[:500],
            )))
            emit(AgentMessage(
                v=1, id=new_id(), ts=now_ts(), type="agent.message",
                corr=corr, text="My apologies, sir — I was unable to complete that request.",
                final=True,
            ))
            emit(AgentTurnComplete(
                v=1, id=new_id(), ts=now_ts(), type="agent.turn_complete",
                corr=corr, status="error",
            ))
