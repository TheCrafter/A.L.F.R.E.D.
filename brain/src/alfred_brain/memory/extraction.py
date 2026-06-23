from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from ..providers.base import ReasoningProvider, TextChunk, TurnMessage
from .record import Memory, MemoryRecord

logger = logging.getLogger(__name__)


_ENTITY_TYPES = {"person", "place", "org", "project", "topic"}


@dataclass
class EntityRef:
    name: str
    type: str = "topic"


@dataclass
class ExtractOp:
    action: Literal["add", "update"]
    text: str
    id: str | None = None
    type: str = "note"
    tags: list[str] = field(default_factory=list)
    confidence: Literal["high", "low"] = "low"
    stakes: Literal["low", "high"] = "low"
    title: str = ""
    entities: list[EntityRef] = field(default_factory=list)


def route_status(confidence: str, stakes: str) -> str:
    return "confirmed" if confidence == "high" and stakes == "low" else "provisional"


EXTRACTION_SYSTEM = (
    "You extract durable, long-term memories from a conversation transcript. "
    "Keep ONLY lasting facts worth remembering across sessions: the user's "
    "identity, lasting preferences, ongoing projects, important people, and how "
    "the user wants the assistant to behave. Ignore greetings, one-off requests, "
    "and ephemeral chatter.\n\n"
    "You are given KNOWN entities, EXISTING memories (each with an id), and a "
    "TRANSCRIPT. For each durable fact:\n"
    "- If it refines or matches an existing memory, emit an \"update\" op with that "
    "id instead of duplicating it; otherwise emit an \"add\" op.\n"
    "- Give it a concise \"title\" (<= 6 words) that reads well as a note name.\n"
    "- List the \"entities\" it concerns as {name, type} with type one of "
    "person|place|org|project|topic. REUSE a KNOWN entity's exact name when it "
    "refers to the same thing, so notes link to the same hub.\n"
    "- If the transcript confirms a tentative existing memory, \"update\" it with "
    "confidence \"high\".\n\n"
    "Set \"confidence\" (high|low) by certainty, and \"stakes\" (low|high) by how "
    "much acting on it wrongly would matter (security, money, identity, "
    "irreversible actions are high).\n\n"
    "Respond with ONLY a JSON object, no prose:\n"
    '{"operations": [{"action": "add", "text": "...", "title": "...", '
    '"type": "fact", "tags": [], "confidence": "high", "stakes": "low", '
    '"entities": [{"name": "...", "type": "person"}]}]}\n'
    "Use an empty operations list when nothing durable is present."
)


def _render(batch: list[TurnMessage]) -> str:
    lines = [f"{m.role}: {m.content.strip()}"
             for m in batch
             if m.role in ("user", "assistant") and m.content.strip()]
    return "\n".join(lines)


def _parse_ops(raw: str) -> list[ExtractOp]:
    """Tolerantly parse the model's JSON. Raises ValueError on failure."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found")
    data = json.loads(text[start:end + 1])
    ops: list[ExtractOp] = []
    for o in data.get("operations", []):
        if not isinstance(o, dict):
            continue
        action = o.get("action")
        body = str(o.get("text", "")).strip()
        if action not in ("add", "update") or not body:
            continue
        entities: list[EntityRef] = []
        for e in (o.get("entities") or []):
            if not isinstance(e, dict):
                continue
            ename = str(e.get("name", "")).strip()
            if not ename:
                continue
            etype = str(e.get("type", "topic"))
            entities.append(EntityRef(ename, etype if etype in _ENTITY_TYPES else "topic"))
        ops.append(ExtractOp(
            action=action, text=body,
            id=(str(o["id"]) if o.get("id") else None),
            type=str(o.get("type", "note")),
            tags=[str(t) for t in (o.get("tags") or [])],
            confidence="high" if o.get("confidence") == "high" else "low",
            stakes="high" if o.get("stakes") == "high" else "low",
            title=str(o.get("title", "")).strip(),
            entities=entities,
        ))
    return ops


class Extractor:
    """Runs an LLM extraction pass over aged-out messages and writes memories."""

    def __init__(self, provider: ReasoningProvider, memory: Memory,
                 *, recall_k: int = 5) -> None:
        self._provider = provider
        self._memory = memory
        self._recall_k = recall_k
        self._lock = asyncio.Lock()

    def set_provider(self, provider: ReasoningProvider) -> None:
        self._provider = provider

    def set_recall_k(self, k: int) -> None:
        self._recall_k = k

    async def _call(self, transcript: str, existing: list[MemoryRecord],
                    known: list[tuple[str, str]]) -> str:
        existing_block = "\n".join(
            f"- [{r.id}] ({r.type}, {r.status}) {r.text}" for r in existing
        ) or "(none)"
        known_block = ", ".join(f"{n} ({t})" for n, t in known) or "(none)"
        user = (f"KNOWN entities: {known_block}\n\n"
                f"EXISTING memories:\n{existing_block}\n\n"
                f"TRANSCRIPT:\n{transcript}")
        chunks: list[str] = []
        async for ev in self._provider.run_turn(
            [TurnMessage(role="user", content=user)], [], EXTRACTION_SYSTEM
        ):
            if isinstance(ev, TextChunk):
                chunks.append(ev.text)
        return "".join(chunks)

    async def extract(self, batch: list[TurnMessage]) -> list[MemoryRecord]:
        transcript = _render(batch)
        if not transcript:
            return []
        async with self._lock:
            logger.info("memory extraction: scanning %d-message batch", len(batch))
            try:
                existing = self._memory.recall(transcript, k=self._recall_k)
                known = self._memory.list_entities()
                raw = await self._call(transcript, existing, known)
                try:
                    ops = _parse_ops(raw)
                except ValueError:
                    raw = await self._call(transcript, existing, known)  # one retry
                    ops = _parse_ops(raw)
            except Exception:
                logger.exception("memory extraction failed")
                return []
            applied = self._apply(ops)
            logger.info("memory extraction: wrote %d memory(s) from %d op(s)",
                        len(applied), len(ops))
            return applied

    def _apply(self, ops: list[ExtractOp]) -> list[MemoryRecord]:
        applied: list[MemoryRecord] = []
        for op in ops:
            try:
                status = route_status(op.confidence, op.stakes)
                links = [self._memory.ensure_entity(e.name, e.type)
                         for e in op.entities if e.name.strip()]
                if op.action == "add":
                    applied.append(self._memory.remember(
                        op.text, type=op.type, tags=op.tags, status=status,
                        title=op.title, links=links))
                elif op.action == "update" and op.id:
                    rec = self._memory.update(
                        op.id, text=op.text, type=op.type, tags=op.tags,
                        status=status, title=(op.title or None),
                        links=(links or None))
                    if rec is not None:
                        applied.append(rec)
            except Exception:
                logger.exception("applying extraction op failed: %s", op)
        return applied
