from __future__ import annotations

from alfred_protocol import RiskTier

from .record import Memory


class RememberTool:
    name = "remember"
    description = ("Store a durable memory the user wants kept (facts, preferences, "
                   "project knowledge). Use when the user says to remember something "
                   "or shares a lasting fact.")
    risk = RiskTier.sensitive
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The memory to store."},
            "type": {"type": "string",
                     "description": "fact | preference | project | note",
                     "default": "note"},
            "tags": {"type": "array", "items": {"type": "string"},
                     "description": "Optional tags."},
        },
        "required": ["text"],
    }

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    async def run(self, args: dict) -> str:
        text = str(args.get("text", "")).strip()
        if not text:
            return "Error: text is required."
        rec = self._memory.remember(
            text,
            type=str(args.get("type", "note")),
            tags=list(args.get("tags") or []),
            status="confirmed",
        )
        return f"Remembered ({rec.type}) as {rec.id}."


class RecallTool:
    name = "recall"
    description = "Search stored memories for anything relevant to a query."
    risk = RiskTier.safe
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look up."},
            "k": {"type": "integer", "description": "Max results (default 5)."},
        },
        "required": ["query"],
    }

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    async def run(self, args: dict) -> str:
        k = int(args.get("k", 5))
        hits = self._memory.recall(str(args.get("query", "")), k=k)
        if not hits:
            return "No relevant memories."
        return "\n".join(f"{h.id}: ({h.type}) {h.text}" for h in hits)


class ForgetTool:
    name = "forget"
    description = "Delete a stored memory by its id (ids come from recall results)."
    risk = RiskTier.sensitive
    parameters = {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "The memory id to delete."}},
        "required": ["id"],
    }

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    async def run(self, args: dict) -> str:
        ok = self._memory.forget(str(args.get("id", "")))
        return "Forgotten." if ok else "No memory with that id."
