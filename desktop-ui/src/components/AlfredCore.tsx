import { useStore } from "../store/store";

type CoreState = "offline" | "idle" | "thinking" | "speaking" | "error";

const LABEL: Record<CoreState, string> = {
  offline: "OFFLINE",
  idle: "ONLINE",
  thinking: "PROCESSING",
  speaking: "SPEAKING",
  error: "FAULT",
};

const IDLE_LINE = "Standing by, sir. Do endeavour to make the next request an interesting one.";
const OFFLINE_LINE = "Disconnected. I shall be here — regrettably — whenever you deign to reconnect.";

// Radial tick ring around the core. Every sixth tick is longer for cadence.
const TICKS = Array.from({ length: 72 }, (_, i) => {
  const a = (i / 72) * Math.PI * 2;
  const major = i % 6 === 0;
  const r1 = 134;
  const r2 = major ? 122 : 129;
  return {
    key: i,
    x1: 150 + Math.cos(a) * r1,
    y1: 150 + Math.sin(a) * r1,
    x2: 150 + Math.cos(a) * r2,
    y2: 150 + Math.sin(a) * r2,
    o: major ? 0.85 : 0.4,
  };
});

// Segmented ring: `count` arcs evenly spaced, leaving gaps between them.
function segments(r: number, count: number, gapDeg: number) {
  const step = 360 / count;
  return Array.from({ length: count }, (_, i) => {
    const start = i * step + gapDeg / 2;
    const end = (i + 1) * step - gapDeg / 2;
    const a0 = (start * Math.PI) / 180;
    const a1 = (end * Math.PI) / 180;
    const large = end - start > 180 ? 1 : 0;
    return {
      key: `${r}-${i}`,
      d: `M ${150 + r * Math.cos(a0)} ${150 + r * Math.sin(a0)} A ${r} ${r} 0 ${large} 1 ${150 + r * Math.cos(a1)} ${150 + r * Math.sin(a1)}`,
    };
  });
}

const OUTER = segments(118, 3, 26);
const MIDDLE = segments(98, 12, 7);

export function AlfredCore() {
  const phase = useStore((s) => s.phase);
  const turns = useStore((s) => s.turns);
  const busy = useStore((s) => s.status?.busy ?? false);
  const lastError = useStore((s) => s.lastError);

  const latest = turns.length ? turns[turns.length - 1] : undefined;
  const active = !!latest && !latest.status;
  const streaming = active && latest.message.text.length > 0 && !latest.message.final;
  const thinking = (active && latest.message.text.length === 0) || busy;

  const state: CoreState =
    phase === "error"
      ? "error"
      : phase !== "ready"
        ? "offline"
        : streaming
          ? "speaking"
          : thinking
            ? "thinking"
            : "idle";

  const voice =
    phase === "error"
      ? (lastError ?? "Something has gone wrong. How novel.")
      : phase !== "ready"
        ? OFFLINE_LINE
        : latest?.message.text
          ? latest.message.text
          : active && latest.thoughts.length
            ? latest.thoughts[latest.thoughts.length - 1]
            : IDLE_LINE;

  return (
    <section className="alfred-core flex min-h-0 min-w-0 flex-1 flex-col items-center justify-center gap-6 overflow-hidden px-4 py-6" data-state={state}>
      <div className="core-stage">
        <div className="core-halo" />
        <svg className="core-svg" viewBox="0 0 300 300" role="img" aria-label={`ALFRED ${LABEL[state]}`}>
          <defs>
            <radialGradient id="coreFill" cx="50%" cy="42%" r="62%">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.35" />
              <stop offset="55%" stopColor="currentColor" stopOpacity="0.07" />
              <stop offset="100%" stopColor="#04070d" stopOpacity="0.9" />
            </radialGradient>
            {/* Triangular geodesic mesh — one up-triangle tile tessellates the plane. */}
            <pattern id="coreMesh" width="20" height="17.32" patternUnits="userSpaceOnUse">
              <path d="M0 17.32 L10 0 L20 17.32 Z" fill="none" stroke="currentColor" strokeWidth="0.5" opacity="0.5" />
            </pattern>
            <clipPath id="coreClip">
              <circle cx="150" cy="150" r="62" />
            </clipPath>
          </defs>

          {/* Radial tick ring */}
          <g className="spin-rev">
            {TICKS.map((t) => (
              <line key={t.key} x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2} stroke="currentColor" strokeWidth="1" opacity={t.o} />
            ))}
          </g>

          {/* Outer segmented ring */}
          <g className="spin">
            {OUTER.map((s) => (
              <path key={s.key} d={s.d} fill="none" stroke="currentColor" strokeWidth="2.5" opacity="0.7" strokeLinecap="round" />
            ))}
          </g>

          {/* Middle segmented ring (counter-rotating) */}
          <g className="spin-fast" style={{ animationDirection: "reverse" }}>
            {MIDDLE.map((s) => (
              <path key={s.key} d={s.d} fill="none" stroke="currentColor" strokeWidth="4" opacity="0.45" />
            ))}
          </g>

          {/* Geodesic core sphere */}
          <g className="core-breathe">
            <circle cx="150" cy="150" r="62" fill="url(#coreFill)" />
            <g clipPath="url(#coreClip)">
              <rect x="88" y="88" width="124" height="124" fill="url(#coreMesh)" />
              {/* meridians + equator imply curvature */}
              <ellipse cx="150" cy="150" rx="34" ry="62" fill="none" stroke="currentColor" strokeWidth="0.6" opacity="0.45" />
              <ellipse cx="150" cy="150" rx="54" ry="62" fill="none" stroke="currentColor" strokeWidth="0.6" opacity="0.3" />
              <ellipse cx="150" cy="150" rx="62" ry="22" fill="none" stroke="currentColor" strokeWidth="0.6" opacity="0.4" />
            </g>
            <circle cx="150" cy="150" r="62" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.95" />
          </g>
        </svg>
      </div>

      <div className="flex items-center gap-2.5 text-xs uppercase tracking-[0.5em]" style={{ color: "var(--core)" }}>
        <span className="text-hud-dim">ALFRED</span>
        <span>{LABEL[state]}</span>
      </div>

      {/* Glanceable caption only — the full reply lives in the event log below,
          so clamp it and never let a long reply blow out the reactor. */}
      <p className="line-clamp-4 max-w-[54ch] overflow-hidden text-center text-base leading-relaxed break-words text-hud">
        {voice}
        {state === "speaking" && <span className="ml-0.5 animate-pulse text-hud">▍</span>}
      </p>
    </section>
  );
}
