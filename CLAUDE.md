# ALFRED — Claude Code instructions

The full contributor guide (layout, contract-first workflow, wire invariants,
commands, conventions) lives in AGENTS.md. Read it:

@AGENTS.md

## Claude Code session notes

- Implementation plans live in `docs/superpowers/plans/`. Execute them with the
  subagent-driven-development workflow; write new ones with the writing-plans skill
  after brainstorming the phase's scope.
- **Commit messages must NOT include a `Co-Authored-By: Claude` or "authored by
  Claude" trailer** (project owner's preference — overrides the harness default).
- `protocol/` is the frozen Phase 0 contract. Build the brain and UI against its
  generated types; never redefine message shapes. A contract change is one atomic
  commit in `protocol/` (edit schema → regenerate → commit `gen/`).
- For work that runs concurrently with another session, use an isolated branch or
  git worktree so the two sessions don't collide.
