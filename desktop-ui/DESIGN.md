# ALFRED Desktop UI — DESIGN

Holographic-HUD command deck. Near-black canvas, cyan primary, amber/red alerts,
monospace data readouts, subtle grid + scanlines + vignette texture. Distinctive through
precise sci-fi instrumentation, not generic dashboard cards.

## Tokens (Tailwind v4 `@theme`, in `src/index.css`)
- `--color-void: #04070d`   — page background (near-black)
- `--color-panel: #0a121f`  — raised surfaces (glassmorphic with /opacity)
- `--color-hud: #38e1ff`    — primary cyan (text, lines, glow)
- `--color-hud-dim: #1a6c80`— muted cyan (secondary text, borders)
- `--color-amber: #ffb648`  — sensitive / thinking / warning
- `--color-danger: #ff5470` — error / forbidden / kill
- `--color-safe: #5ef2a0`   — safe / ready / valid
- `--font-mono` — JetBrains Mono stack

Tailwind v4 auto-generates `text-*`/`bg-*`/`border-*` from these; opacity via `/NN`.

## Texture utilities (`@layer utilities`)
`.hud-grid` (28px cyan grid), `.hud-scanlines`, `.hud-vignette`. Applied as a
`pointer-events-none` overlay layer in `App.tsx` so the deck stays interactive.

## State → color language
- offline/disconnected → `hud-dim` (still, dim)
- ready/idle → `hud` cyan (gentle pulse)
- thinking/busy/acting → `amber` (faster, agitated)
- speaking (streaming `agent.message`) → bright `hud` (expanding rings, glow ramps with text)
- error → `danger` red
Risk badges: safe=cyan/green, sensitive=amber, forbidden=red.

## Motion
Ease-out (quart/expo), no bounce. Continuous ambient motion is intentional (a living core),
but respects `prefers-reduced-motion` (rings hold a static glow; pulse becomes a crossfade).
Animate transform/opacity/filter, not layout.

## The AlfredCore centerpiece
A reactor inspired by the JARVIS sphere: a triangulated geodesic core inside concentric
segmented rings with a glow halo. Rotation speed, ring expansion, and glow intensity are
driven by Alfred's live state; his current utterance reads beneath the core as its "voice."
The connection bar carries controls; the core carries presence.

## Layout
`ConnectionBar` (top) · main column [ `AlfredCore` hero → `EventStream` log ] with
`StatusPanel` at right · `CommandInput` · `WireInspector` · `KillSwitch` footer.
