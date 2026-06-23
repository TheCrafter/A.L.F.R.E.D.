import { useStore } from "../store/store";
import { RiskBadge } from "./RiskBadge";
import type { Turn } from "../store/turns";

function TurnCard({ turn }: { turn: Turn }) {
  return (
    <div className="rounded border border-hud-dim/20 bg-panel/40 p-3">
      <div className="mb-2 text-sm text-hud">
        <span className="text-hud-dim">❯ </span>
        {turn.commandText}
        {turn.status && (
          <span className="ml-2 text-[10px] uppercase text-hud-dim">[{turn.status}]</span>
        )}
      </div>
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
  );
}

export function EventStream() {
  const turns = useStore((s) => s.turns);
  // The core carries the idle/current line, so the log shows nothing until
  // there's history — then it's a bounded, scrollable strip beneath the core.
  if (turns.length === 0) return null;
  return (
    <section
      aria-label="Event log"
      className="mx-auto w-full max-w-3xl shrink-0 space-y-3 overflow-y-auto border-t border-hud-dim/20 px-4 py-4"
      style={{ maxHeight: "32vh" }}
    >
      {turns.map((t) => (
        <TurnCard key={t.corr} turn={t} />
      ))}
    </section>
  );
}
