# A.L.F.R.E.D. — Marks

Iteration milestones, Iron-Man style. Each **Mark** is a cohesive iteration of the
assistant. A git **release tag** is cut only when a Mark actually ships — the Mark
label advances during development ahead of any tag.

## MARK I — *in progress*

**Theme: the assistant that remembers.**

- **Desktop HUD (Phase 4 slice):** Tauri + React dashboard — live event stream,
  command input, status panel, kill switch, wire inspector, the AlfredCore reactor,
  and a model picker.
- **Stabilization:** hardened WebSocket lifecycle (survives malformed frames,
  cancels orphaned turns), real error surfacing in the UI, disconnect/reconnect
  finalization.
- **Reasoning:** Gemini + Groq providers behind `ReasoningProvider`, with runtime
  model switching.
- **Config subsystem:** user-owned `~/.alfred/config.toml` (env-wins precedence,
  first-run bootstrap seeded from the environment, validated settings, runtime
  reload, redacted admin endpoints).
- **Memory (crown jewel):** facade + markdown vault + recall wired into the agent
  loop — *in design*.

_Not yet released; no git tag cut._
