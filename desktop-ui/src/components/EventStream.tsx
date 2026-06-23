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
        <div key={`ac-${i}`} className="flex items-center gap-2 pl-4 text-xs text-hud">
          <RiskBadge risk={a.risk} />
          <span className="text-hud-dim">{a.tool}</span>
          <span>{a.summary}</span>
        </div>
      ))}
      {turn.message.text && (
        <div className="mt-2 pl-4 text-sm text-hud [text-shadow:0_0_8px_var(--color-hud)]">
          {turn.message.text}
        </div>
      )}
    </div>
  );
}

export function EventStream() {
  const turns = useStore((s) => s.turns);
  return (
    <main className="flex-1 space-y-3 overflow-y-auto p-4">
      {turns.length === 0 ? (
        <p className="text-sm text-hud-dim">
          Awaiting instruction. I do hope it&apos;s worth my processing cycles.
        </p>
      ) : (
        turns.map((t) => <TurnCard key={t.corr} turn={t} />)
      )}
    </main>
  );
}
