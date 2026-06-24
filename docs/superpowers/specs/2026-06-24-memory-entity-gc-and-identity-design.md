# Memory: Entity GC + Canonical Identity + Sensitive Handling — Design

Status: approved (brainstorm) · 2026-06-24
Builds on: titles/linking + review-panel increments. Brain-only (no protocol/UI change).

## 1. Context

Live testing of the review panel surfaced four refinements:
1. Deleting a memory leaves its entity hubs orphaned (e.g. delete the only Berlin
   fact → a `Berlin` hub nothing references).
2. The extractor invents a generic `[[User]]` entity instead of linking the user's
   facts to their own page, fragmenting the graph.
3. Sensitive facts (IBAN) get **refused** instead of stored.
4. Provisional memories get spuriously **promoted** to confirmed on re-scan (the
   prompt actively tells the model to do this).

This increment fixes all four. It is brain-internal — no `protocol/` change, no new
wire messages, no UI change (entity hubs are Obsidian-only, never shown in the panel).

## 2. Reference-counted entity GC

When a memory is removed, garbage-collect **only orphaned** entity hubs — a hub is
deleted iff **no other memory still links to it**. A shared hub (`[[Dimitris]]`)
survives because other facts reference it; a now-unreferenced hub (`[[Berlin]]`) is
removed. No blanket deletion, no special-casing.

- **`Vault.delete_entity(stem) -> bool`**: unlink `entities/<stem>.md` (missing_ok).
- **Facade GC helper** `_gc_entity(stem)`: delete the hub via the vault iff no record
  in `self._records` still has `stem` in its `links`.
- **`VaultMemory.forget(id)`**: capture the deleted record's `links`, remove the
  memory (vault + index + records), then `_gc_entity` each of those links.
- **`VaultMemory.update(id, …, links=…)`**: when `links` is provided and the update
  drops some (old − new), `_gc_entity` each dropped stem (so a re-linked fact doesn't
  strand an old hub). When `links is None` (unchanged), no GC.

Entities are navigational/Obsidian-only and not part of recall or the panel, so GC is
pure vault cleanup — no wire event, no index change.

## 3. Canonical user identity

A new config value names the user so their facts link to one canonical hub.

- **`Settings.memory_user_name: str = ""`** (env `ALFRED_USER_NAME`, TOML
  `[memory] user_name`). Empty default → no identity instruction (other installs).
- **`Extractor(…, user_name="")`**: when set, the effective extraction system prompt
  appends: *"The user is named {user_name}. Link facts about the user to the
  [[{user_name}]] entity (type person); never use a generic 'User' entity."*
- `create_app` passes `settings.memory_user_name` to the `Extractor`. Startup-applied
  (`[*]`) — the user sets it once.
- **Out of scope:** retro-migrating the existing `[[User]]` hub / notes already linked
  to it (fixed going forward; consolidate in Obsidian or via a future one-time pass).

## 4. Extraction prompt fixes

Edit `EXTRACTION_SYSTEM`:

- **Never refuse:** *"Never refuse to store a durable fact. If a fact is sensitive
  (passwords, credentials, account/IBAN numbers, financial or private identifiers),
  still store it — set stakes 'high' and add the tag `sensitive`."*
- **No auto-promote:** replace the current *"If the transcript confirms a tentative
  existing memory, update it with confidence high"* with *"Do NOT raise an existing
  memory's confidence or change its status unless the user explicitly restates or
  reaffirms that fact in THIS transcript."*

Plus a **deterministic safety net** in `_apply`: if an op's tags contain `sensitive`,
force `status = "provisional"` regardless of the model's confidence/stakes. This
guarantees sensitive facts are held loosely even if the model misjudges.

## 5. Configuration

| TOML (`[memory]`) | Settings field | Env | Default | Reload |
|---|---|---|---|---|
| `user_name` | `memory_user_name` | `ALFRED_USER_NAME` | `""` | `[*]` startup |

Add to `ENV_ALIASES`, `SECTION_MAP`, and the bootstrap template `[memory]` block
(commented, with a one-line explanation).

## 6. Files

- `brain/src/alfred_brain/config/settings.py` (`memory_user_name`),
  `config/toml_source.py` (SECTION_MAP), `config/bootstrap.py` (template).
- `brain/src/alfred_brain/memory/vault.py` (`delete_entity`).
- `brain/src/alfred_brain/memory/facade.py` (`_gc_entity`; GC in `forget`/`update`).
- `brain/src/alfred_brain/memory/extraction.py` (prompt edits, `user_name`,
  per-call system prompt, sensitive→provisional net).
- `brain/src/alfred_brain/server.py` (pass `user_name` to `Extractor`).
- Tests alongside each.

## 7. Testing

- **GC:** delete a memory whose entity is unreferenced → hub file gone; delete one of
  several memories sharing a hub → hub survives; update that drops a link → old hub
  GC'd iff orphaned, kept if still referenced; `delete_entity` unlinks / missing_ok.
- **Identity:** `Extractor(user_name="Dimitris")` includes the identity instruction
  in the system prompt sent to the provider; empty `user_name` omits it.
- **Prompt/net:** an op tagged `sensitive` is stored `provisional` even when the model
  said `confidence:high, stakes:low`; `EXTRACTION_SYSTEM` no longer contains the
  auto-promote instruction and does contain the no-refuse/sensitive guidance.
- **Config:** `memory_user_name` loads from env + TOML; default `""`.
- Full brain suite stays green.

## 8. Deferred

Retro-migration of the existing `[[User]]` hub · GC on the rare extraction-update that
changes links is included, but GC triggered by a *panel retag* is N/A (retag changes
tags, not links) · hot-reload of `user_name`.
