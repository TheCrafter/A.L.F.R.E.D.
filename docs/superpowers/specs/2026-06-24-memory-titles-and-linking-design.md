# Memory Note Titles + Hub/Entity Linking — Design

Status: approved (brainstorm) · 2026-06-24
Builds on: `2026-06-23-memory-subsystem-design.md` (vault foundation) and
`2026-06-23-memory-formation-design.md` (extraction pass).

## 1. Problem

Two Obsidian-usability defects in the vault:

1. **Ugly note names.** A fact note is named `<40-char-slug-of-the-entire-fact>-<12-char-hex-id>.md`, e.g. `dimitris-is-32-years-old-lives-in-greece-6bc59450e3e3.md`. That is a terrible Obsidian note title.
2. **No links.** Nothing writes `[[wikilinks]]`, so Obsidian's graph and backlinks are empty — the vault is a flat pile of disconnected notes.

## 2. Solution overview

- **Readable titles:** each memory gets a short LLM-generated `title`; the filename becomes a filesystem-safe form of that title. The stable `id` lives in frontmatter only (no hex in the name).
- **Hub/entity notes:** maintain a lightweight anchor note per entity (person/place/org/project/topic) under `entities/`. Atomic fact notes link **up** to their entity hubs via `[[wikilinks]]`. Obsidian's **backlinks pane and graph are automatic**, so hubs need no ongoing maintenance — the fact notes carry the links, Obsidian does the visualization.

## 3. Vault layout

```
~/.alfred/vault/
  memories/                          # atomic fact notes — indexed for recall (unchanged role)
    Dimitris - age and location.md     body links to [[Dimitris]], [[Greece]]
  entities/                          # NEW: hub notes — navigational, NOT recall-indexed
    Dimitris.md   (type: person)
    Greece.md     (type: place)
    Alfred.md     (type: project)
```

Obsidian resolves `[[Dimitris]]` across the whole vault regardless of subfolder, so the folder split is purely organizational and keeps hubs out of fact recall (`recall` reads only `memories/`).

## 4. Fact note format

```markdown
---
id: 6bc59450e3e3
created: 2026-06-24T20:11:00+00:00
type: fact
tags: [personal]
status: confirmed
title: Dimitris - age and location
---

Dimitris is 32 years old and lives in Greece.

Related: [[Dimitris]], [[Greece]]
```

- Body = the fact text, then (only when links exist) a blank line + a single `Related: [[A]], [[B]]` line.
- `read()` parses frontmatter `title`, splits the trailing `Related:` line back into `links`, and returns `text` without it (so recall stays clean).

## 5. Filenames & titles

- `title`: short (≤ ~6 words), LLM-generated for auto-extraction; for explicit `remember` it is the model-supplied title, falling back to the first ~8 words of the text.
- `_safe_filename(title)`: strip Windows-illegal chars `\ / : * ? " < > |`, collapse whitespace, cap ~80 chars, default `"memory"` if empty.
- Filename = `<safe title>.md` in `memories/`. **Collisions** → numeric suffix (`Dimitris - age and location 2.md`).
- **Stable on update:** `update()` keeps the existing path (never renames), so `[[links]]` to it never break; only the frontmatter `title` (and body) change.
- The `id` (uuid4 hex[:12]) stays in frontmatter and remains the handle for `recall`/`forget`/`update` (all of which already match on frontmatter id, not filename — so dropping the hex from the name breaks nothing).

## 6. Hub/entity notes

```markdown
---
type: person
created: 2026-06-24T20:11:00+00:00
---

# Dimitris
```

- `ensure_entity(name, type="topic") -> str`: find-or-create a hub in `entities/`.
  - Match is case-insensitive on the safe-filename stem (`_safe_filename(name).casefold()`), so "dimitris"/"Dimitris" do not duplicate.
  - On match, return the existing stem (preserves first-seen spelling/casing). On miss, create `entities/<safe name>.md` with `type` + `created` frontmatter and body `# <name>`, return the stem.
  - The returned stem is the wikilink target: the fact body uses `[[<stem>]]`.
- `list_entities() -> list[tuple[str, str]]`: existing `(name, type)` pairs (read from `entities/` frontmatter + stem), used to tell the extractor which hubs already exist so it reuses them.
- Hubs are **not** added to the recall index and **not** returned by `all()` (which reads `memories/` only). They are anchors + auto-backlink targets, nothing more. No maintained summaries (deferred).

## 7. Data model

`MemoryRecord` gains:
- `title: str = ""`
- `links: list[str] = field(default_factory=list)`

`Memory` protocol:
- `remember(text, *, type="note", tags=None, status="confirmed", title="", links=None) -> MemoryRecord`
- `update(id, *, text=None, type=None, tags=None, status=None, title=None, links=None) -> MemoryRecord | None`
- `ensure_entity(name, type="topic") -> str`
- `list_entities() -> list[tuple[str, str]]`

## 8. Extraction changes

- `EntityRef(name: str, type: str = "topic")`.
- `ExtractOp` gains `title: str = ""` and `entities: list[EntityRef] = []`.
- `_parse_ops` parses `title` and `entities` (`[{"name","type"}]`), coercing entity `type` to one of `person|place|org|project|topic` (default `topic`).
- `extract()` fetches `known = memory.list_entities()` and passes the known-entity names into the prompt so the model reuses hubs.
- `EXTRACTION_SYSTEM` additionally instructs: give each memory a concise `title` (≤ 6 words); list the `entities` (name + type) the fact concerns, **reusing a known entity name** when it matches.
- `_apply`: for each op, `links = [memory.ensure_entity(e.name, e.type) for e in op.entities]`, then `remember(..., title=op.title, links=links)` (add) or `update(id, ..., title=op.title, links=links)` (update).

Updated JSON shape the extractor must emit:
```json
{"operations": [
  {"action": "add", "text": "Dimitris is 32 and lives in Greece.",
   "title": "Dimitris - age and location", "type": "fact", "tags": [],
   "confidence": "high", "stakes": "low",
   "entities": [{"name": "Dimitris", "type": "person"},
                {"name": "Greece", "type": "place"}]}
]}
```

## 9. Explicit `remember` tool

`RememberTool.parameters` gains optional `title` (string) and `entities` (array of `{name, type}`). `run()`:
- resolve `links = [memory.ensure_entity(e["name"], e.get("type","topic")) for e in entities]`;
- `title` falls back to the first ~8 words of `text` when absent;
- `remember(text, type=…, tags=…, status="confirmed", title=title, links=links)`.

## 10. Backward compatibility

- Applies to **new** writes. `read()` of a legacy note without `title`/`Related:` returns `title=""` and `links=[]` (consumers fall back to the filename / text) — no crash, no auto-rewrite.
- The user has **cleared the vault**, so no migration is needed in practice. Bulk migration of old notes is out of scope.

## 11. Files

- Modify: `memory/record.py` (`title`, `links`, protocol), `memory/vault.py` (safe filenames, collision, `_body`/`_split_body`, `read` parsing, `ensure_entity`, `list_entities`, `entities` dir), `memory/facade.py` (pass-through + `ensure_entity`/`list_entities`), `memory/extraction.py` (`EntityRef`, `ExtractOp` fields, parse, prompt, `_apply`, known-entities), `memory/tools.py` (`remember` title/entities).
- Untouched: `protocol/` (frozen); agent loop and server wiring (titles/links flow through the existing facade/extractor with no signature changes there).

## 12. Testing focus

- `_safe_filename` strips illegal chars; collision suffixing; stable filename across `update`.
- `_body`/`_split_body` round-trip (text + links ↔ body), including the no-links case and links-present case; `read` recovers `title` and `links`; recall `text` excludes the `Related:` line.
- `ensure_entity` find-or-create + case-insensitive dedup; hub written to `entities/` with type; `list_entities` returns existing pairs; hubs excluded from `all()`/recall.
- Extraction: `_parse_ops` parses `title`/`entities` and coerces entity type; `_apply` calls `ensure_entity` per entity and writes the fact with title + `[[links]]`; reuse of a known entity does not create a duplicate hub.
- Tool: `remember` with/without `title`/`entities`; fallback title; links created.

## 13. Deferred / future

Maintained hub summaries (LLM-written entity descriptions) · entity merge/alias resolution beyond exact safe-name match · two-way Obsidian editing · migrating legacy notes.
