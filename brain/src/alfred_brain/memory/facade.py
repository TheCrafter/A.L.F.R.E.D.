from __future__ import annotations

from pathlib import Path

from .index import Embedder, VectorIndex
from .record import MemoryRecord
from .vault import Vault


class VaultMemory:
    """Memory implementation: markdown vault (source of truth) + in-memory index.

    The index is rebuilt from the vault on construction, so it always reflects
    the markdown on disk.
    """

    def __init__(self, vault_dir: Path, embedder: Embedder) -> None:
        self._vault = Vault(vault_dir)
        self._index = VectorIndex(embedder)
        self._records: dict[str, MemoryRecord] = {}
        for rec in self._vault.all():
            self._records[rec.id] = rec
            self._index.add(rec.id, rec.text)

    def remember(self, text: str, *, type: str = "note",
                 tags: list[str] | None = None,
                 status: str = "confirmed") -> MemoryRecord:
        rec = self._vault.write(text, type=type, tags=tags, status=status)
        self._records[rec.id] = rec
        self._index.add(rec.id, rec.text)
        return rec

    def recall(self, query: str, *, k: int = 5) -> list[MemoryRecord]:
        return [self._records[i] for i, _ in self._index.search(query, k)
                if i in self._records]

    def update(self, id: str, *, text: str | None = None, type: str | None = None,
               tags: list[str] | None = None,
               status: str | None = None) -> MemoryRecord | None:
        rec = self._vault.update(id, text=text, type=type, tags=tags, status=status)
        if rec is None:
            return None
        self._records[rec.id] = rec
        if text is not None:
            self._index.remove(rec.id)
            self._index.add(rec.id, rec.text)
        return rec

    def forget(self, id: str) -> bool:
        if not self._vault.delete(id):
            return False
        self._records.pop(id, None)
        self._index.remove(id)
        return True

    def all(self) -> list[MemoryRecord]:
        return list(self._records.values())
