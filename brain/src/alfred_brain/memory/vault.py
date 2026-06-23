from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .record import MemoryRecord

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _slugify(text: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-").split("-")
    slug = "-".join(w for w in words if w)[:40].strip("-")
    return slug or "memory"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Vault:
    """Reads/writes memories as Obsidian-compatible markdown notes.

    Layout: <vault_dir>/memories/<slug>-<id>.md  (frontmatter + body).
    The vault is the source of truth for the Memory subsystem.
    """

    def __init__(self, vault_dir: Path) -> None:
        self._dir = Path(vault_dir) / "memories"

    def write(self, text: str, *, type: str = "note",
              tags: list[str] | None = None,
              status: str = "confirmed") -> MemoryRecord:
        self._dir.mkdir(parents=True, exist_ok=True)
        rec = MemoryRecord(
            id=_new_id(), text=text, type=type, tags=list(tags or []),
            status=status, created=_now(),
            path=Path(),  # set below
        )
        rec.path = self._dir / f"{_slugify(text)}-{rec.id}.md"
        rec.path.write_text(self._render(rec), encoding="utf-8")
        return rec

    def _render(self, rec: MemoryRecord) -> str:
        meta = {"id": rec.id, "created": rec.created, "type": rec.type,
                "tags": rec.tags, "status": rec.status}
        if rec.updated:
            meta["updated"] = rec.updated
        front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
        return f"---\n{front}---\n\n{rec.text}\n"

    def read(self, path: Path) -> MemoryRecord:
        raw = Path(path).read_text(encoding="utf-8")
        m = _FRONTMATTER.match(raw)
        if not m:
            raise ValueError(f"not a memory note (no frontmatter): {path}")
        meta = yaml.safe_load(m.group(1)) or {}
        return MemoryRecord(
            id=str(meta.get("id", "")), text=m.group(2).strip(),
            type=str(meta.get("type", "note")), tags=list(meta.get("tags") or []),
            status=str(meta.get("status", "active")),
            created=str(meta.get("created", "")), path=Path(path),
            updated=(str(meta["updated"]) if meta.get("updated") else None),
        )

    def all(self) -> list[MemoryRecord]:
        if not self._dir.is_dir():
            return []
        return [self.read(p) for p in sorted(self._dir.glob("*.md"))]

    def update(self, id: str, *, text: str | None = None, type: str | None = None,
               tags: list[str] | None = None,
               status: str | None = None) -> MemoryRecord | None:
        for rec in self.all():
            if rec.id != id:
                continue
            if text is not None:
                rec.text = text
            if type is not None:
                rec.type = type
            if tags is not None:
                rec.tags = list(tags)
            if status is not None:
                rec.status = status
            rec.updated = _now()
            rec.path.write_text(self._render(rec), encoding="utf-8")
            return rec
        return None

    def delete(self, id: str) -> bool:
        for rec in self.all():
            if rec.id == id:
                rec.path.unlink()
                return True
        return False
