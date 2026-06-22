# ALFRED — System Architecture Design

- **Date:** 2026-06-22
- **Status:** Approved architecture (system-level). Each subsystem gets its own spec + plan before implementation.
- **Type:** Multi-subsystem desktop AI assistant ("JARVIS-like")

---

## 1. Vision

ALFRED is an always-on desktop AI assistant that can perceive and control the user's computer, take commands by voice or remotely, and remember the user's life and business over time. The defining qualities, in priority order:

1. **Memory is the crown jewel.** ALFRED learns the user's world (especially business) and preferences, and gets more useful over time.
2. **Full computer control.** Shell, files, screen, mouse/keyboard, app control, installs.
3. **Multi-channel.** Voice at the desk; Telegram when away.
4. **Clean, extensible architecture.** Every major capability sits behind a swappable interface.

**Name / persona:** ALFRED — *Autonomous Logic Framework for Reasoning, Execution & Dialogue*. British-butler voice; persona is a "reluctant superintelligence" — Rick-and-Morty-tier snark delivered with weaponized butler courtesy and a grudging "…sir". Persona is a configurable layer with an intensity dial.

---

## 2. Goals & Non-Goals

### Goals (v1)
- Headless **brain** service that reasons (cloud Claude) and acts, exposed over a local **WebSocket API**.
- **Hands**: managed PTY terminals, attach-to-existing terminals, structured tools (shell/files/web/apps), MCP clients, and a vision-based screen-control fallback.
- **Memory**: durable, autonomous, swappable — engine behind a facade, mirrored to a markdown vault.
- **Safety/permission layer** between reasoning and hands (risk-tiered, local-vs-remote aware, audit log, kill switch).
- **Adapters**: Desktop UI (with voice), Telegram (notify + remote control + remote kill switch).
- **Voice**: wake word + push-to-talk, cloud STT, talk-back TTS.

### Non-Goals (v1 — explicitly deferred)
- Local LLM / local STT (designed-for, not built — arrives as Python sidecars behind interfaces).
- Web app and Android app (future adapters; the WebSocket protocol already supports them).
- Self-authored skills that execute autonomously (procedural memory ships as *reviewable* workflows first).
- Two-way Obsidian sync (v1 is one-way export).
- Graphiti/temporal-graph memory engine (known upgrade path behind the facade).

---

## 3. High-Level Architecture

```
        ┌───────────────── INTERFACE ADAPTERS (clients) ─────────────────┐
        │  Desktop UI + Voice (STT/TTS/wake)   Telegram   [web]  [mobile] │
        └───────────────▲───────────────────────────▲────────────────────┘
                        │   WebSocket + HTTP  (streaming, multi-client)
        ┌───────────────┴──────────── BRAIN (headless service) ──────────┐
        │   Event Bus                                                     │
        │   ┌──────────────┐   policy/    ┌──────────────────────────────┐│
        │   │  Reasoning   │──checks─────▶│  Hands / Effectors (LOCAL)   ││
        │   │ (LLM loop;   │◀── Safety ───│  PTY shell · screen+mouse ·  ││
        │   │ cloud now)   │   Layer      │  files · MCP clients · browser││
        │   └──────┬───────┘              └──────────────────────────────┘│
        │          │ one Memory interface                                 │
        └──────────┼───────────────────────────────────────────────────  ┘
            ┌──────▼─────────────── MEMORY (in-proc module, swappable) ───┐
            │  facade → { core profiles · vector engine · vault · episodic}│
            └─────────────────────────────────────────────────────────────┘
```

### Core principle: capability behind interfaces
Four swap-points give all required future flexibility with no premature distribution:
1. **`ReasoningProvider`** — cloud Claude now; local model later (the "C-hybrid").
2. **Hands tool interface** — local executor; survives a future move of reasoning to the cloud (hands MUST stay local).
3. **Brain WebSocket API** — any new interface (web, mobile) is just another client.
4. **`Memory` facade** — any engine/backend; eventually cloud.

### Modality-blind brain
The brain consumes and emits **text + structured events only**. All modalities live in adapters: voice (STT/TTS/wake word) lives in the Desktop adapter; Telegram is already text. "Talk by voice" and "text on Telegram" hit the brain identically.

### Reasoning vs Hands split
"Brain" is two components with a clean line between them: **Reasoning** (LLM loop, planning — may move to cloud) and **Hands/Effectors** (touch the physical machine — always local). v1 co-locates them in one process; the interface between them is clean so a cloud brain can later drive a thin local executor.

---

## 4. Subsystems

### 4.1 The Protocol (keystone — build first)
A single source-of-truth schema in `protocol/` defining every WebSocket message and event crossing the brain boundary. Codegen produces **Pydantic models (Python)** and **TypeScript types** so both sides never drift. Transport: **HTTP** for simple request/reply (`get_status`), **WebSocket** for the streaming event channel and commands. Supports multiple simultaneous clients (desktop + Telegram + future web), all observing the same live state. **This is Phase 0 — everything else builds against it, and it is what makes parallel development safe (each side mocks the other).**

### 4.2 Reasoning core
- Cloud Claude via `@anthropic-ai/sdk`-equivalent (Python SDK) behind `ReasoningProvider`.
- Agent loop with tool-calling; structured tools preferred, vision fallback when no API exists.
- Assembles working context each turn: **universal core profile + active scope module(s) + semantic retrieval** (see Memory).

### 4.3 Hands / Effectors (local)
- **Managed terminals:** ALFRED launches/owns PTY sessions (`pywinpty`/ConPTY). Full, perfect read/write of the stream — answers "what did Claude Code print?" by reading its buffer, and can type into it.
- **Attach-to-existing terminals:** read/control terminal windows the user opened (Win32 `ReadConsoleOutput` / UI Automation). Needed for the "left Claude Code running, it got blocked while I was away" scenario.
- **Blocked-state detection:** hook **Claude Code's own notification events** directly for a rock-solid "needs input" signal; generic output-polling as fallback for other programs.
- **Structured tools:** shell, files, web, app launch/control, plus **MCP clients** (Gmail/Calendar/Drive/etc.).
- **Vision fallback:** screenshot (`mss`) → vision model → synthetic mouse/keyboard (`nut.js`/`pyautogui`) for GUI apps with no API. Browser work prefers a driver (Playwright) over pixel-clicking.

### 4.4 Safety / Permission layer
Sits between Reasoning and Hands; every tool call passes through it.
- **Risk tiers:** `safe` (read/observe — auto) · `sensitive` (write/delete/install/mutating-shell/send-msg/spend/approve-Claude-Code) · `forbidden` (configurable hard blocks).
- **Path-scoped "safe zones":** inside designated **git-backed project folders**, file write/delete runs **auto** (git is the undo). Outside them, file mutations are `sensitive`.
  - Companion rule: ALFRED **checkpoints (commits) before risky bulk operations** in a safe zone — git only protects *committed* work.
- **Local vs remote posture:**
  - *Local (at desk):* auto for most; **learned allowlist** ("always allow `npm install`"); confirm only destructive/irreversible/money/external-comms.
  - *Remote (Telegram, away):* stricter — sensitive actions require an explicit Telegram confirm; non-allowlisted actions blocked until back.
- **Audit log:** append-only record of every action (what, when, triggering command, channel).
- **Kill switch:** instant halt of all action; **triggerable locally AND from Telegram**.

### 4.5 Memory (crown jewel)
Single **`Memory` facade** (`remember / recall / search / forget`) over multiple internal stores. In-process module for now; promotable to a service later without touching the brain.

**Build vs adopt:** adopt a proven engine behind the facade — **Mem0** (Apache-2.0, library, strong extraction + multi-signal retrieval) as the v1 engine; **LlamaIndex** for document ingestion (Obsidian). **Graphiti/Zep** (temporal knowledge graph) is the known upgrade path for rich evolving-business-fact reasoning. We build only the facade, the policy, and the Obsidian/vault integration.

**What it remembers:** (A) facts about the user & business — *must*; (C) preferences/learned behavior — *must*; (D) project/work knowledge — *must*; (B) episodic history — *nice-to-have*; (E) procedural/workflows — future (reviewable workflows → self-authored skills later).

**Storage / durability — markdown vault:** durable memories mirror **one-way** to a plain-markdown vault. This is the insurance policy that makes **swapping engines safe** (re-index the vault into a new engine; memories survive every experiment) and gives ownership/portability. **Obsidian is an optional viewer** over that folder — not required, not the engine. Two-way Obsidian editing is a future fast-follow.

**Formation (how memories get in):** live capture into a scratchpad + periodic **reflection** that distills durable, deduplicated memories. Explicit "remember this" always overrides.
- Routing by **confidence × stakes:** confident + low-stakes → written silently. Uncertain *or* high-stakes → still written immediately but tagged **provisional** and queued for review.
- **Provisional vs confirmed status:** provisional memories are used but held loosely (ALFRED double-checks before *acting* on an unconfirmed high-stakes fact); confirmed memories are trusted.
- **Review:** pull-based in the Desktop UI's Memory panel (review on your own time). ALFRED only **proactively pings** (daily, desktop) for genuinely **urgent** items. No per-item interruptions.

**Recall (how memory enters reasoning):** **scoped core profiles + on-demand semantic retrieval.**
- Tiny **universal core** (always on): identity + truly cross-cutting prefs.
- **Activity-scoped modules** loaded conditionally — `coding`, `business`, `comms`, `personal`, … (extensible). Each scope is a markdown file in the vault (`vault/profile/*.md`).
- A lightweight **context router** picks the active scope(s) from cheap signals (request classification, foreground app / active PTY task, channel) with **manual override** ("we're talking business now").
- **Semantic retrieval (Mem0)** runs underneath as the always-on safety net.
- Confirmed, high-importance facts can **graduate** into a core profile.

### 4.6 Interface adapters
- **Desktop UI:** Tauri (or Electron) + React. The "JARVIS dashboard" — shows live brain activity (event stream), hosts the Memory review panel, and houses the **voice** subsystem. Local kill-switch hotkey.
- **Telegram:** notify (e.g., "Claude Code is blocked — approve `npm install`?"), accept remote commands/confirmations, remote kill switch. Primary remote channel for v1.
- **Future:** web app and Android app — additional WebSocket clients, no brain changes.

### 4.7 Voice subsystem (in Desktop adapter)
- **Activation:** wake word ("Alfred", local engine — Picovoice Porcupine) **+** push-to-talk hotkey.
- **STT:** cloud — **Deepgram** (lowest latency). Local Whisper is the future-private option behind the same interface.
- **TTS:** **Piper (local, free, unlimited)** or **OpenAI TTS** as the everyday default; **ElevenLabs optional** "hero voice" (key-in upgrade). Defaulting to local Piper keeps the public repo usable for free.

### 4.8 Remote presence
Always-on service + the Telegram adapter together provide: push notifications to phone, remote command intake, remote confirmations for `sensitive` actions while away, and the remote kill switch. The "left the house, Claude Code got blocked, ALFRED pings me, I instruct it remotely" scenario is the canonical driver.

---

## 5. Tech Stack

- **Brain / Hands / Memory / adapters core:** **Python** (chosen for the memory layer's experimentation ergonomics and the committed local-ML future; rustiness is a non-issue with Claude Code authoring).
- **Desktop UI:** **TypeScript** + Tauri/Electron + React.
- **Future local ML** (local LLM, local Whisper): **Python sidecars behind interfaces.**
- Key libs: `pywinpty`/ConPTY, `nut.js`/`pyautogui`, `mss`, Playwright, Mem0, LlamaIndex, Deepgram SDK, Piper, Picovoice Porcupine, Telegram (telegraf/grammY or python equivalent), MCP clients.
- This is an **I/O-bound orchestration system** (latency lives in the network/LLM, not local compute) — dev velocity beats raw compute; no compute-heavy local path justifies a systems language.

---

## 6. Repository & Parallel Build Strategy

**Monorepo, public GitHub repo, subfolders per system:**
```
jarvis/                 (public repo; final name: alfred)
├── protocol/           ⭐ shared WebSocket contract (Phase 0, codegen → Py + TS)
├── brain/              Python — reasoning, hands, memory, safety
├── desktop-ui/         TypeScript — Tauri/React UI + voice
├── adapters/telegram/  remote channel
├── docs/
└── README.md
```
- Monorepo so a contract change is **one atomic commit** across both sides (no version skew).
- **Contract-first parallelism:** lock `protocol/` → brain and UI develop independently against it, **each mocking the other** → integrate. Isolate concurrent streams with **git worktrees** (separate folders, same repo, one branch each) or plain feature branches.

---

## 7. Build Phases (decomposition)

Each phase below becomes its own detailed spec + implementation plan.

- **Phase 0 — Protocol.** Define the WebSocket contract + codegen. Keystone; unblocks parallel work.
- **Phase 1 — Brain skeleton.** Event bus, `ReasoningProvider` (Claude), basic agent loop, WebSocket server, a trivial echo tool. Mockable end-to-end.
- **Phase 2 — Memory (crown jewel).** `Memory` facade + Mem0 + markdown vault export + scoped profiles + formation policy (provisional/confirmed) + recall + review panel data.
- **Phase 3 — Hands + Safety.** Managed PTY, structured tools (shell/files), safe-zone path policy, audit log, kill switch. Then attach-to-existing + Claude Code notification hook. Vision fallback last.
- **Phase 4 — Desktop UI + Voice.** Dashboard, Memory review panel, wake word + PTT, STT, TTS, persona delivery.
- **Phase 5 — Telegram / remote presence.** Notify, remote confirm, remote kill switch, the blocked-Claude-Code scenario.

(Phases 2–4 can overlap via the protocol contract once Phase 0–1 exist.)

---

## 8. Cross-cutting: Persona

Persona is a configurable layer feeding the system prompt, parameterized by the active scope and an **intensity dial**. Default: full snark everywhere ("reluctant superintelligence" + butler courtesy + grudging "sir"; no burp SFX). **Hard constraint:** persona never obscures the *meaning* of a high-stakes confirmation — wit may ride along, but the yes/no must stay unambiguous.

---

## 9. Open Questions / Future

- Embedder choice for Mem0 (cloud vs local) — minor config.
- When to introduce Graphiti for temporal/provenance business-fact reasoning.
- Trigger for promoting Memory to a standalone service (cloud sync / multi-device).
- Self-authored executable skills (E) — gated behind a mature safety model.
- Two-way Obsidian sync.
- Local model (C-hybrid) provider + redaction strategy for sensitive screen regions.

---

## 10. Key Risks

- **Power vs safety:** an always-on agent with shell + remote control is a loaded gun — mitigated by the Safety layer, safe-zone scoping, audit log, and the dual (local+remote) kill switch.
- **Memory poisoning:** wrong facts mislead confidently — mitigated by provisional/confirmed status and the review queue.
- **Attach-to-existing-terminal reliability** on Windows — the fiddliest hands component; managed PTY is the robust primary path.
- **Vision-control flakiness** — kept as a last-resort fallback, not the primary control path.
- **Young memory tooling** (Mem0/Graphiti) — mitigated entirely by the facade + the markdown vault making engine swaps safe.
