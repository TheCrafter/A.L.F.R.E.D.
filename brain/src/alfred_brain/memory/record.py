from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class MemoryRecord:
    id: str
    text: str
    type: str
    tags: list[str]
    status: str
    created: str  # RFC 3339
    path: Path
    updated: str | None = None


@runtime_checkable
class Memory(Protocol):
    def remember(self, text: str, *, type: str = "note",
                 tags: list[str] | None = None,
                 status: str = "confirmed") -> MemoryRecord: ...
    def recall(self, query: str, *, k: int = 5) -> list[MemoryRecord]: ...
    def update(self, id: str, *, text: str | None = None, type: str | None = None,
               tags: list[str] | None = None,
               status: str | None = None) -> MemoryRecord | None: ...
    def forget(self, id: str) -> bool: ...
    def all(self) -> list[MemoryRecord]: ...
