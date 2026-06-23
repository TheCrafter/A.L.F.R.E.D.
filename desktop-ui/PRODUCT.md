# ALFRED Desktop UI — PRODUCT

register: product

## What this is
The "JARVIS dashboard" — a Tauri + React desktop client for ALFRED, an always-on
desktop AI assistant with a snarky "reluctant superintelligence" British-butler persona.
It connects to the brain over a frozen WebSocket/HTTP contract and is the human's
window into what Alfred is thinking, doing, and saying.

## Who uses it, where
A single power user at their desk, lights low, often glancing at it ambiently while
Alfred works in the background (running shell, editing files, driving apps). It must read
at a glance from across the room AND reward a close look. Mood: a quiet command deck — you
are the operator; Alfred is the reluctant genius doing the work.

## Core surfaces
- **AlfredCore** — the centerpiece: a glowing reactor that visualizes Alfred's live state
  (offline / idle / thinking / speaking) and surfaces his current utterance. This is the
  "face" that does the talking.
- **Event stream** — the turn-by-turn log: thoughts, risk-badged actions, streamed replies.
- **Command input** — issue a command (`command.submit`).
- **Status panel** — uptime, version, active scopes, busy (`GET /status`).
- **Kill switch** — always-reachable, confirm-gated halt (`kill_switch.activate`).
- **Wire inspector** — raw protocol traffic + per-message Ajv validation (dev/debug).

## Principles
- **Contract-first.** Types come from `@alfred/protocol`; message shapes are never redefined.
- **Legible spectacle.** Striking HUD aesthetics, but meaning is never obscured — a kill-switch
  confirm is always unambiguous; streamed text is always readable.
- **State you can feel.** Connection, thinking, and speaking are visible at a glance through
  motion and color, not just labels.

## Deferred
Voice (wake word / STT / TTS), the memory review panel, and finalizing in-flight turns on
disconnect/kill (see README → Known limitations).
