import { useState } from "react";
import { useStore } from "../store/store";
import { RiskBadge } from "./RiskBadge";
import type { Turn } from "../store/turns";

function TurnCard({
  turn,
  expanded,
  onToggle,
}: {
  turn: Turn;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="rounded border border-hud-dim/20 bg-panel/40 p-3">
      {/* The ❯ doubles as a disclosure toggle: it points right when collapsed,
          rotates down when expanded. Click the header to fold the turn away. */}
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 text-left text-sm text-hud"
      >
        <span className={`text-hud-dim transition-transform ${expanded ? "rotate-90" : ""}`}>❯</span>
        <span className="min-w-0 flex-1 break-words">{turn.commandText}</span>
        {turn.status && (
          <span className="shrink-0 text-[10px] uppercase text-hud-dim">[{turn.status}]</span>
        )}
      </button>
      {expanded && (
        <div className="mt-2">
          {turn.thoughts.map((t, i) => (
            <div key={`th-${i}`} className="pl-4 text-xs italic text-hud-dim">
              ⋯ {t}
            </div>
          ))}
          {turn.actions.map((a, i) => (
            <div key={`ac-${i}`} className="flex items-start gap-2 pl-4 text-xs text-hud">
              <RiskBadge risk={a.risk} />
              <span className="shrink-0 text-hud-dim">{a.tool}</span>
              <span className="min-w-0 break-words">{a.summary}</span>
            </div>
          ))}
          {turn.message.text && (
            <div className="mt-2 pl-4 text-sm whitespace-pre-wrap break-words text-hud [text-shadow:0_0_8px_var(--color-hud)]">
              {turn.message.text}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function EventStream() {
  const turns = useStore((s) => s.turns);
  // Manual overrides only: a corr is present here once the user has clicked its
  // header. Auto rule (for untouched turns): expand only the newest. So a new
  // turn collapses older ones, but anything the user opened/closed by hand stays
  // exactly as they left it.
  const [manual, setManual] = useState<Record<string, boolean>>({});
  // The core carries the idle/current line, so the log shows nothing until
  // there's history — then it's a bounded, scrollable strip beneath the core.
  if (turns.length === 0) return null;
  const newestCorr = turns[turns.length - 1].corr;
  return (
    <section
      aria-label="Event log"
      className="mx-auto w-full max-w-3xl shrink-0 space-y-3 overflow-y-auto border-t border-hud-dim/20 px-4 py-4"
      style={{ maxHeight: "32vh" }}
    >
      {/* Newest first. */}
      {turns
        .slice()
        .reverse()
        .map((t) => {
          const expanded = t.corr in manual ? manual[t.corr] : t.corr === newestCorr;
          return (
            <TurnCard
              key={t.corr}
              turn={t}
              expanded={expanded}
              onToggle={() => setManual((m) => ({ ...m, [t.corr]: !expanded }))}
            />
          );
        })}
    </section>
  );
}
