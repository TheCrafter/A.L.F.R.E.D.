from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .record import MemoryRecord

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
_ILLEGAL = re.compile(r'[\\/:*?"<>|]')
_RELATED = re.compile(r"\n+Related:\s*(.+)$", re.DOTALL)


def _safe_filename(title: str) -> str:
    name = _ILLEGAL.sub("", title)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80].strip() or "memory"


def _derive_title(text: str) -> str:
    return " ".join(text.split()[:8])[:60].strip() or "memory"


def _split_body(body: str) -> tuple[str, list[str]]:
    m = _RELATED.search(body)
    if not m:
        return body, []
    text = body[: m.start()].strip()
    links = re.findall(r"\[\[(.+?)\]\]", m.group(1))
    return text, links


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
        self._entities = Path(vault_dir) / "entities"

    def write(self, text: str, *, type: str = "note",
              tags: list[str] | None = None, status: str = "confirmed",
              title: str = "", links: list[str] | None = None) -> MemoryRecord:
        self._dir.mkdir(parents=True, exist_ok=True)
        rec = MemoryRecord(
            id=_new_id(), text=text, type=type, tags=list(tags or []),
            status=status, created=_now(), path=Path(),
            title=(title.strip() or _derive_title(text)), links=list(links or []),
        )
        rec.path = self._unique_path(rec.title)
        rec.path.write_text(self._render(rec), encoding="utf-8")
        return rec

    def _unique_path(self, title: str) -> Path:
        base = _safe_filename(title)
        path = self._dir / f"{base}.md"
        n = 2
        while path.exists():
            path = self._dir / f"{base} {n}.md"
            n += 1
        return path

    def _render(self, rec: MemoryRecord) -> str:
        meta = {"id": rec.id, "created": rec.created, "type": rec.type,
                "tags": rec.tags, "status": rec.status, "title": rec.title}
        if rec.updated:
            meta["updated"] = rec.updated
        front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
        body = rec.text
        if rec.links:
            body += "\n\nRelated: " + ", ".join(f"[[{l}]]" for l in rec.links)
        return f"---\n{front}---\n\n{body}\n"

    def read(self, path: Path) -> MemoryRecord:
        raw = Path(path).read_text(encoding="utf-8")
        m = _FRONTMATTER.match(raw)
        if not m:
            raise ValueError(f"not a memory note (no frontmatter): {path}")
        meta = yaml.safe_load(m.group(1)) or {}
        text, links = _split_body(m.group(2).strip())
        return MemoryRecord(
            id=str(meta.get("id", "")), text=text,
            type=str(meta.get("type", "note")), tags=list(meta.get("tags") or []),
            status=str(meta.get("status", "active")),
            created=str(meta.get("created", "")), path=Path(path),
            updated=(str(meta["updated"]) if meta.get("updated") else None),
            title=str(meta.get("title", "")), links=links,
        )

    def all(self) -> list[MemoryRecord]:
        if not self._dir.is_dir():
            return []
        return [self.read(p) for p in sorted(self._dir.glob("*.md"))]

    def update(self, id: str, *, text: str | None = None, type: str | None = None,
               tags: list[str] | None = None, status: str | None = None,
               title: str | None = None,
               links: list[str] | None = None) -> MemoryRecord | None:
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
            if title is not None:
                rec.title = title
            if links is not None:
                rec.links = list(links)
            rec.updated = _now()
            rec.path.write_text(self._render(rec), encoding="utf-8")  # same path
            return rec
        return None

    def delete(self, id: str) -> bool:
        for rec in self.all():
            if rec.id == id:
                rec.path.unlink()
                return True
        return False

    def ensure_entity(self, name: str, type: str = "topic") -> str:
        name = name.strip()
        stem = _safe_filename(name)
        self._entities.mkdir(parents=True, exist_ok=True)
        key = stem.casefold()
        for p in self._entities.glob("*.md"):
            if p.stem.casefold() == key:
                return p.stem
        front = yaml.safe_dump({"type": type, "created": _now()},
                               sort_keys=False, allow_unicode=True)
        (self._entities / f"{stem}.md").write_text(
            f"---\n{front}---\n\n# {name}\n", encoding="utf-8")
        return stem

    def list_entities(self) -> list[tuple[str, str]]:
        if not self._entities.is_dir():
            return []
        out: list[tuple[str, str]] = []
        for p in sorted(self._entities.glob("*.md")):
            m = _FRONTMATTER.match(p.read_text(encoding="utf-8"))
            meta = (yaml.safe_load(m.group(1)) if m else {}) or {}
            out.append((p.stem, str(meta.get("type", "topic"))))
        return out
